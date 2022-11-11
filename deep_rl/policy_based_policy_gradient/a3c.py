import random
from pathlib import Path
from itertools import count
from collections import deque
import warnings ; warnings.filterwarnings('ignore')

import gym
import numpy as np
import torch
import torch.multiprocessing as mp

from fc import FCDAP, FCV
from shared_optimizers import SharedAdam, SharedRMSprop

"""Asynchronous Advantage Actor-Critic

VPG still uses MC returns. In A3C we use n-step return collected from multiple workers.
These workers update their local networks and a shared network asynchronously.

Each worker have (As in VPG):
- A local policy network
- A local value network

There is a Shared Policy Network and a Shared Value Network

"""

class A3C():

    def __init__(self, ENV_CONF, TRAIN_CONF):

        nS = ENV_CONF["nS"]
        nA = ENV_CONF["nA"]
        self.device = TRAIN_CONF["device"]
        self.gamma = TRAIN_CONF["gamma"]
        lr_p = TRAIN_CONF.lrs[0]
        lr_v = TRAIN_CONF.lrs[1]
        self.seed = TRAIN_CONF["seed"]

        # Define policy network and shared policy network
        hidden_dims = (128, 64)
        self.policy = FCDAP(self.device, nS, nA, hidden_dims=hidden_dims).to(self.device)
        self.p_optimizer = SharedAdam(self.policy.parameters(), lr=lr_p)
        self.policy_model_max_grad_norm = 1

        self.shared_policy = FCDAP(
            self.device, nS, nA, hidden_dims=hidden_dims).to(self.device).share_memory()
        self.shared_p_optimizer = SharedAdam(self.shared_policy.parameters(), lr=lr_p)
        # -------------------------------------------------

        # Define value network and shared value network
        hidden_dims=(256, 128)
        self.value_model = FCV(self.device, nS, hidden_dims=hidden_dims).to(self.device)
        self.v_optimizer = SharedRMSprop(self.value_model.parameters(), lr=lr_v)
        self.value_model_max_grad_norm = float('inf')

        self.shared_value_model = FCV(
            self.device, nS, hidden_dims=hidden_dims).to(self.device).share_memory()
        self.shared_v_optimizer = SharedRMSprop(self.shared_value_model.parameters(), lr=lr_v)
        # -------------------------------------------------

        self.get_out_lock = mp.Lock()
        self.get_out_signal = torch.zeros(1, dtype=torch.int).share_memory_()
        

        self.entropy_loss_weight = 0.001
        self.max_n_steps = TRAIN_CONF.max_n_steps
        self.n_workers = TRAIN_CONF.n_workers

        self.logpas = []
        self.rewards = []
        self.entropies = []
        self.values = []

    
    def interact_with_environment(self, state, env):
        self.policy.train()
        action, logpa, entropy = self.policy.full_pass(state)
        next_state, reward, is_terminal, _, _ = env.step(action)

        self.logpas.append(logpa)
        self.rewards.append(reward)
        self.entropies.append(entropy)
        self.values.append(self.value_model(state))

        return next_state, is_terminal
    

    def learn(self):
        """
        Learn once full trajectory is collected
        """
        T = len(self.rewards)
        discounts = np.logspace(0, T, num=T, base=self.gamma, endpoint=False)
        returns = np.array([np.sum(discounts[:T-t] * self.rewards[t:]) for t in range(T)])
        discounts = torch.FloatTensor(discounts[:-1]).unsqueeze(1)
        returns = torch.FloatTensor(returns[:-1]).unsqueeze(1)

        self.logpas = torch.cat(self.logpas)
        self.entropies = torch.cat(self.entropies) 
        self.values = torch.cat(self.values)

        # --------------------------------------------------------------------
        # A(St, At) = Gt - V(St)
        # Loss = -1/N * sum_0_to_N( A(St, At) * log πθ(At|St) + βH )

        advantage = returns - self.values
        policy_loss = -(discounts * advantage.detach() * self.logpas).mean()
        entropy_loss_H = -self.entropies.mean()
        loss = policy_loss + self.entropy_loss_weight * entropy_loss_H

        self.p_optimizer.zero_grad()
        loss.backward()
        # clip the gradient
        torch.nn.utils.clip_grad_norm_(self.policy.parameters(), self.policy_model_max_grad_norm)
        self.p_optimizer.step()

        # --------------------------------------------------------------------
        # A(St, At) = Gt - V(St)
        # Loss = 1/N * sum_0_to_N( A(St, At)² )

        value_loss = advantage.pow(2).mul(0.5).mean()
        self.v_optimizer.zero_grad()
        value_loss.backward()
        torch.nn.utils.clip_grad_norm_(
            self.value_model.parameters(), self.value_model_max_grad_norm)
        self.v_optimizer.step()


    def evaluate(self, env, n_episodes=1):
        self.policy.eval()
        eval_scores = []
        for _ in range(n_episodes):
            s, d = env.reset(seed=self.seed)[0], False
            eval_scores.append(0)

            for _ in count():
                with torch.no_grad():
                    a = self.policy.select_greedy_action(s)

                s, r, d, _, _ = env.step(a)
                eval_scores[-1] += r
                if d: break
    
        return np.mean(eval_scores), np.std(eval_scores)


    def reset_metrics(self):
        self.logpas = []
        self.rewards = []
        self.entropies = []
        self.values = []


if __name__ == "__main__":

    EVALUATE_ONLY = True

    if EVALUATE_ONLY:
        env = gym.make("CartPole-v1", render_mode="human")
    else:
        env = gym.make("CartPole-v1")
        
    nS, nA = env.observation_space.shape[0], env.action_space.n

    ENV_CONF = { "nS": nS, "nA": nA }

    TRAIN_CONF = {
        "seed": 42, "gamma": .99, "lrs": [0.0005, 0.0007], "n_episodes": 5000,
        "goal_mean_100_reward": 700, "max_n_steps": 50, "n_workers": 8,
        "device": torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    }
    model_path = Path("deep_rl/policy_based_policy_gradient/A3C_cartpolev1.pt")

    torch.manual_seed(TRAIN_CONF.seed)
    np.random.seed(TRAIN_CONF.seed)
    random.seed(TRAIN_CONF.seed)

    agent = A3C(ENV_CONF, TRAIN_CONF)
    
    if EVALUATE_ONLY:
        agent.policy.load_state_dict(torch.load(model_path))
        mean_eval_score, _ = agent.evaluate(env, n_episodes=1)
    else:
        evaluation_scores = deque(maxlen=100)

        for i_episode in range(1, TRAIN_CONF["n_episodes"] + 1):
            state, is_terminal = env.reset(seed=TRAIN_CONF.seed)[0], False

            agent.reset_metrics()
            for t_step in count():
                new_state, is_terminal = agent.interact_with_environment(state, env)
                state = new_state

                if is_terminal: break
            
            next_value = 0 if is_terminal else agent.value_model(state).detach().item()
            agent.rewards.append(next_value)
            
            agent.learn()
            mean_eval_score, _ = agent.evaluate(env, n_episodes=1)
            evaluation_scores.append(mean_eval_score)

            if len(evaluation_scores) >= 100:
                mean_100_eval_score = np.mean(evaluation_scores)
                print(f"Episode {i_episode}\tAverage mean 100 eval score: {mean_100_eval_score}")

                if(mean_100_eval_score >= TRAIN_CONF.goal_mean_100_reward):
                    torch.save(agent.policy.state_dict(), model_path)
                    break

    env.close()