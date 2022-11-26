import random
import configparser
from pathlib import Path
from itertools import count
from collections import deque
from matplotlib import animation
import matplotlib.pyplot as plt
import warnings ; warnings.filterwarnings('ignore')

import gym
import pybulletgym
import numpy as np
import torch
import torch.optim as optim

from fc import FCTQV, FCDP
from replay_buffer import ReplayBuffer
from ddpg import GreedyStrategy

"""
TD3: Twin Delayed DDPG add some improvement to the ddpg algorithm
- Double learning technique as in DDQN but using a single twin network
- Add noise, not only to the online action but also to the target action
- Delays updates of the policy network, the target network and twin target network
"""

class NormalNoiseDecayStrategy():
    def __init__(self, bounds, init_noise_ratio=0.5, min_noise_ratio=0.1, decay_steps=10000):
        self.t = 0
        self.low, self.high = bounds
        self.noise_ratio = init_noise_ratio
        self.init_noise_ratio = init_noise_ratio
        self.min_noise_ratio = min_noise_ratio
        self.decay_steps = decay_steps
        self.ratio_noise_injected = 0

    def _noise_ratio_update(self):
        noise_ratio = 1 - self.t / self.decay_steps
        noise_ratio = (self.init_noise_ratio - self.min_noise_ratio) * noise_ratio + self.min_noise_ratio
        noise_ratio = np.clip(noise_ratio, self.min_noise_ratio, self.init_noise_ratio)
        self.t += 1
        return noise_ratio

    def select_action(self, model, state, max_exploration=False):
        if max_exploration:
            noise_scale = self.high
        else:
            noise_scale = self.noise_ratio * self.high

        with torch.no_grad():
            greedy_action = model(state).cpu().detach().data.numpy().squeeze()

        noise = np.random.normal(loc=0, scale=noise_scale, size=len(self.high))
        noisy_action = greedy_action + noise
        action = np.clip(noisy_action, self.low, self.high)

        self.noise_ratio = self._noise_ratio_update()
        self.ratio_noise_injected = np.mean(abs((greedy_action - action)/(self.high - self.low)))
        return action


def save_frames_as_gif(frames, filepath):

    #Mess with this to change frame size
    plt.figure(figsize=(frames[0].shape[1] / 72.0, frames[0].shape[0] / 72.0), dpi=72)

    patch = plt.imshow(frames[0])
    plt.axis('off')

    def animate(i):
        patch.set_data(frames[i])

    anim = animation.FuncAnimation(plt.gcf(), animate, frames = len(frames), interval=50)
    anim.save(filepath, writer='imagemagick', fps=60)


def inference(model, env, seed, action_bounds):
    total_rewards = 0
    frames = []

    eval_strategy = GreedyStrategy(action_bounds)
    s, d = env.reset()[0], False
    
    for _ in count():
        with torch.no_grad():
            a = eval_strategy.select_action(model, s)
        
        frames.append(env.render())
        s, r, d, trunc, _ = env.step(a)
        total_rewards += r
        if d or trunc: break
    
    env.close()

    return total_rewards, frames



class TD3():
    def __init__(self, action_bounds, config, seed, device):

        self.config = config
        self.device = device
        buffer_size = config.getint("buffer_size")
        bs = config.getint("batch_size")
        nS = config.getint("nS")
        nA = config.getint("nA")
        hidden_dims = eval(config.get("hidden_dims"))
        lr = config.getfloat("lr")
        self.tau = config.getfloat("tau")
        self.gamma = config.getfloat("gamma")
        self.n_warmup_batches = config.getint("n_warmup_batches")

        self.memory = ReplayBuffer(buffer_size, bs, seed)

        self.actor = FCDP(device, nS, action_bounds, hidden_dims)  # ReLu + Tanh
        self.actor_target = FCDP(device, nS, action_bounds, hidden_dims)

        self.critic = FCTQV(device, nS, nA, hidden_dims)  # using ReLu by default
        self.critic_target = FCTQV(device, nS, nA, hidden_dims)

        self.actor_optimizer = optim.Adam(self.actor.parameters(), lr=lr)
        self.critic_optimizer = optim.Adam(self.critic.parameters(), lr=lr)

        self.max_grad = float('inf')

        self.training_strategy = NormalNoiseDecayStrategy(
                action_bounds, init_noise_ratio=0.5, min_noise_ratio=0.1, decay_steps=200000)
        
        self.eval_strategy = GreedyStrategy(action_bounds)

        self.policy_noise_ratio = 0.1
        self.policy_noise_clip_ratio = 0.5
        self.train_actor_every = 2

        self.sync_weights()
    
        
    def interact_with_environment(self, state, env):
        """same as ddpg"""

        min_samples = self.memory.batch_size * self.n_warmup_batches

        use_max_exploration = len(self.memory) < min_samples

        action = self.training_strategy.select_action(self.actor,
                                                      state,
                                                      use_max_exploration)
        
        next_state, reward, is_terminal, is_truncated, _ = env.step(action)
        is_failure = is_terminal or is_truncated

        experience = (state, action, reward, next_state, float(is_failure))
        return experience


    def store_experience(self, state, action, reward, next_state, done):
        self.memory.add(state, action, reward, next_state, done)  

        
    def sample_and_learn(self, t_step):
        states, actions, rewards, next_states, is_terminals = self.memory.sample(self.device)
        
        with torch.no_grad():
            # compute noise for target action (in ddpg noise is only applied on the online action)
            # training the policy with noisy targets can be seen as a regularizer
            # the network is now forced to generalize over similar actions 
            a_ran = self.actor_target.upper - self.actor_target.lower
            a_noise = torch.randn_like(actions) * self.policy_noise_ratio * a_ran
            n_min = self.actor_target.lower * self.policy_noise_clip_ratio
            n_max = self.actor_target.upper * self.policy_noise_clip_ratio            
            a_noise = torch.max(torch.min(a_noise, n_max), n_min)

            # Get the target noisy action
            a_next = self.actor_target(next_states)
            noisy_a_next = a_next + a_noise
            noisy_a_next = torch.max(
                torch.min(noisy_a_next, self.actor_target.upper), self.actor_target.lower
            )
            
            # Get Q_next from the TWIN critic, which is the min Q between the two streams
            Q_target_stream_a, Q_target_stream_b = self.critic_target(next_states, noisy_a_next)
            Q_next = torch.min(Q_target_stream_a, Q_target_stream_b)
            Q_target = rewards + self.gamma * Q_next * (1 - is_terminals)
        
        
        # update the critic
        Q_stream_a, Q_stream_b = self.critic(states, actions)
        error_a = Q_stream_a - Q_target
        error_b = Q_stream_b - Q_target

        critic_loss = error_a.pow(2).mul(0.5).mean() + error_b.pow(2).mul(0.5).mean()
        self.critic_optimizer.zero_grad()
        critic_loss.backward()
        torch.nn.utils.clip_grad_norm_(self.critic.parameters(), self.max_grad)
        self.critic_optimizer.step()

        # delay actor update, so the critic is updated at higher rate. This give the critic the time
        # to settle into more accurate values because it is more sensible
        if t_step % self.train_actor_every == 0:
            a_pred = self.actor(states)

            # here we choose one of the 2 streams and we stick to it
            Q_pred = self.critic.Qa(states, a_pred) 

            actor_loss = -Q_pred.mean()
            self.actor_optimizer.zero_grad()
            actor_loss.backward()
            torch.nn.utils.clip_grad_norm_(self.actor.parameters(), self.max_grad)        
            self.actor_optimizer.step()

            
    def evaluate_one_episode(self, env, seed):
        total_rewards = 0

        s, d = env.reset()[0], False
        
        for _ in count():
            with torch.no_grad():
                a = self.eval_strategy.select_action(self.actor, s)

            s, r, d, trunc, _ = env.step(a)
            total_rewards += r
            if d or trunc: break


        return total_rewards
    

    def sync_weights(self, use_polyak_averaging=True):
        if(use_polyak_averaging):
            """
            Instead of freezing the target and doing a big update every n steps, we can slow down
            the target by mixing a big % of weight from the target and a small % from the 
            behavior policy. So the update will be smoother and continuous at each time step.
            For example we add 1% of new information learned by the behavior policy to the target
            policy at every step.

            - self.tau: ratio of the behavior network that will be mixed into the target network.
            tau = 1 means full update (100%)
            """
            if self.tau is None:
                raise Exception("You are using Polyak averaging but TAU is None")
            
            # mixe value networks
            for t, b in zip(self.critic_target.parameters(), self.critic.parameters()):
                target_ratio = (1.0 - self.tau) * t.data
                behavior_ratio = self.tau * b.data
                mixed_weights = target_ratio + behavior_ratio
                t.data.copy_(mixed_weights.data)
            
            # mix policy networks
            for t, b in zip(self.actor_target.parameters(), self.actor.parameters()):
                target_ratio = (1.0 - self.tau) * t.data
                behavior_ratio = self.tau * b.data
                mixed_weights = target_ratio + behavior_ratio
                t.data.copy_(mixed_weights.data)
        else:
            """
            target network was frozen during n steps, now we are update it with the behavior network
            weight.
            """
            for t, b in zip(self.critic_target.parameters(), self.critic.parameters()):
                t.data.copy_(b.data)
            
            for t, b in zip(self.actor_target.parameters(), self.actor.parameters()):
                t.data.copy_(b.data)
    


if __name__ == "__main__":
    
    folder = Path("/home/medhyvinceslas/Documents/courses/gdrl_rl_spe/deep_rl/policy_based_and_ac")
    config_file = folder / "config.ini"
    config = configparser.ConfigParser()
    config.read(config_file)
    
    conf = config["DEFAULT"]
    conf_td3 = config["TD3"]

    seed = conf.getint("seed")
    model_path = Path(folder / conf_td3.get("model_name"))
    is_evaluation = conf.getboolean("evaluate_only")

    env_name = conf_td3.get("env_name")
    env = gym.make(env_name, render_mode="rgb_array") if is_evaluation else gym.make(env_name)
    action_bounds = env.action_space.low, env.action_space.high
    nS, nA = env.observation_space.shape[0], env.action_space.shape[0]

    conf_td3["nS"] = f"{nS}"
    conf_td3["nA"] = f"{nA}"

    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    agent = TD3(action_bounds, conf_td3, seed, device)

    if is_evaluation:
        agent.actor.load_state_dict(torch.load(model_path))
        total_rewards, frames = inference(agent.actor, env, seed, action_bounds)
        save_frames_as_gif(frames, filepath=str(folder / "td3.gif"))
    else:

        last_100_score = deque(maxlen=100)
        mean_of_last_100 = deque(maxlen=100)

        n_episodes = conf_td3.getint("n_episodes")
        goal_mean_100_reward = conf_td3.getint("goal_mean_100_reward")

        for i_episode in range(1, n_episodes + 1):
            state, is_terminal = env.reset()[0], False

            for t_step in count():
                state, action, reward, next_state, is_terminal = (
                        agent.interact_with_environment(state, env)
                )
                agent.store_experience(state, action, reward, next_state, is_terminal)
                state = next_state

                if len(agent.memory) > agent.memory.batch_size * agent.n_warmup_batches:
                    agent.sample_and_learn(t_step=t_step)
                
                if t_step % 2 == 0:
                    agent.sync_weights(use_polyak_averaging=True)
                
                if is_terminal: break
            
            # Evaluate
            total_rewards = agent.evaluate_one_episode(env, seed=seed)
            last_100_score.append(total_rewards)
            
            if len(last_100_score) >= 100:
                mean_100_score = np.mean(last_100_score)
                print(f"Episode {i_episode}\tAverage mean 100 eval score: {mean_100_score}")
            
                if(mean_100_score >= goal_mean_100_reward):
                    torch.save(agent.actor.state_dict(), model_path)
                    break
            else:
                print(f"Length eval score: {len(last_100_score)}")
    
        env.close()
