# Policy based methods

Goal is to maximize the true value function of a parameterized policy from all initial states.
So maximize the true value function by changing the policy (without touching the value function).  
  
We want to **find the gradient** which will help reaching this objective

## REINFORCE
<center>Use of function approximation (here a policy network) to generate probabilities over actions</center>  

<style>
    svg[id^="mermaid-"] { width: 100%; max-height: 450px;}
</style>
  ```mermaid

  %%{ init: { 'flowchart': { 'curve': 'basis' } } }%%
graph TD;
    subgraph Policy Network
    id1((s1)) & id2((s2)) & id3((s3)) & id4((s4)) ---> 
    h1((h1)) & h2((h2)) & h3((h3)) & h4((h4)) & h5((h5)) & hn((hn)) ---> a1((a1)) & a2((a2));
end
```
The Policy Network have nS (state size) inputs and nA outputs that represent the distribution over actions.

From a trajectory $\lambda$ and output from the model, we obtain at each step $t$:

#### <center>$G_t(\lambda) * log \pi (A_t | S_t;\theta)$</center>

>- $G_t$ being the discounted return
>- $log \pi (A_t | S_t;\theta)$ is parameterized by $\theta$, so it is the output from the policy network.

So the gradient we are trying to estimate and maximize **(The Objective Function)** is:

#### <center>$\boxed{J(\theta) = \frac{1}{T} \sum_{t=0}^T G_t(\lambda) * log \pi (A_t | S_t;\theta)}$</center>

In PyTorch, since the default behavior of gradient update is gradient descent, we put a negative sign in order to do gradient ascent.  

```python
loss = -(discounts * returns * logpas).mean()
optimizer.zero_grad()
loss.backward()
optimizer.step()
```

As we can see, the return $G_t$ is used to **weight** the log probability of the action taken at time t. That mean if the return is bad at time t, it is because action taken at time t was bad, so by multiplying the bad return with the probability of that action, we reduce the likelihood.
of that action being selected at that step.  

[![PyTorch](https://img.shields.io/badge/PyTorch-%23EE4C2C.svg?style=for-the-badge&logo=PyTorch&logoColor=white)](
  https://github.com/Mdhvince/reinforcement_learning/blob/master/deep_rl/policy_based_and_ac/reinforce.py
)

***
## Vanilla Policy Gradient or REINFORCE with baseline

<center>Use 2 neural networks (policy network & value network) to respectively give the value of a state and generate probabilities over actions</center>  

  ```mermaid
%%{ init: { 'flowchart': { 'curve': 'basis' } } }%%
graph

subgraph Vanilla Policy Gradient

   subgraph Value Network
        id1((s1)) & id2((s2)) & id3((s3)) & id4((s4)) ---> 
        h1((h1)) & h2((h2)) & h3((h3)) & h4((h4)) & h5((h5)) & hn((hn)) ---> v1((v1))
    end

    subgraph Policy Network
        i1((s1)) & i2((s2)) & i3((s3)) & i4((s4)) ---> 
        hh1((h1)) & hh2((h2)) & hh3((h3)) & hh4((h4)) & hh5((h5)) & hh6((hn)) ---> a1((a1)) & a2((a2))
    end

end


```
- The Value Network have nS (state size) inputs and 1 output that represent the Value of a state.
- The Policy Network have nS (state size) inputs and nA outputs that represent the distribution over actions.

Some issues with REINFORCE:
>- **High variance** because of the accumulation of random event along a trajectory (full monte carlo return is used to calculate the gradient).
>- Log probabilities are changing proportionally to the return : $G_t(\lambda) log \pi (A_t | S_t;  \theta)$ - this can be an issue in environment with only positive rewards, return can be the same, so action probability can be quite similar.

In VPG, we solve the 2nd point: we need a way to differenciate "ok actions" & "best actions".  
For this we use the **Action-Advantage** function estimate $A(S_t, A_t; \phi) = G_t - V(S_t; \phi)$ instead of the return $G_t$ to weight the log probability of actions. 

**$A(S_t, A_t; \phi)$** center scores around 0 such that:
>- Better than average actions will have a positive value
>- Worst than average actions will have a negative value

We also use an **entropy term** $H$ weighted by $\beta$ in order to encourage exploration.  
  
So the gradient we are trying to estimate is:  

#### <center>$\boxed{A(S_t, A_t; \phi) * log \pi (A_t | S_t;  \theta) + \beta H(\pi (S_t;\theta))}$</center>

We can subsitute $A(S_t, A_t; \phi)$ by $G_t - V(S_t; \phi)$ and obtain:

#### <center>$\boxed{(G_t - V(S_t; \phi)) * log \pi (A_t | S_t;  \theta) + \beta H(\pi (S_t;  \theta))}$</center>

Loss for the Policy Network is:  

#### <center>$\boxed{L(\theta) = -\frac{1}{N}  \sum_{n=0}^N [(G_t - V(S_t; \phi)) * log \pi (A_t | S_t;  \theta) + \beta H(\pi (S_t;  \theta))]}$</center>
  
In first term $G_t - V(S_t; \phi)$, the state-value function is parameterized by $\phi$. So we need a value network to return the value of a state. The second and the third term are parameterized by $ \theta$ so we also need a policy network that return action probabilities then deduce the log and the entropy.   
   
Loss for the Value Network is:  
  
#### <center>$\boxed{L(\phi) = \frac{1}{N}  \sum_{n=0}^N [(G_t - V(S_t; \phi))^2]}$</center>
  
So in VPG we need a value network and a policy network. Because VPG is still using a full trajectory, there is no bias in the algorithm, so we assume the algorithm is "right" so cannot be considered as a "critic" (A thought by Rich Sutton. I also share his idea on that, so for me this is not an actor-critic algoritm). 

[![PyTorch](https://img.shields.io/badge/PyTorch-%23EE4C2C.svg?style=for-the-badge&logo=PyTorch&logoColor=white)](
  https://github.com/Mdhvince/reinforcement_learning/blob/master/deep_rl/policy_based_and_ac/vanilla_policy_gradient.py
)

***
## Advantage Actor-Critic: A2C (Sharing Weight)  

<center>Use of One neural networks to update both the policy & the value network by sharing the weight</center>

```mermaid
%%{ init: { 'flowchart': { 'curve': 'basis' } } }%%
graph TD

subgraph A2C
    id1((s1)) & id2((s2)) & id3((s3)) & id4((s4)) ---> 
    h1((h1)) & h2((h2)) & h3((h3)) & h4((h4)) & h5((h5)) & hn((hn)) ---> v1((v1)) & a1((a1)) & a2((a2))
end

```

<center>Use of multiple workers (multiprocessing) to collect samples of the environment</center>  

```mermaid
%%{ init: { 'flowchart': { 'curve': 'basis' } } }%%
graph TD

subgraph Workers interacting with multiple envs
    id1((worker env 1)) & id2((worker env 2)) & id3((worker env n)) --> idenv(Multiprocessing Env class);
    idenv --> A2C_Agent
    A2C_Agent --> idenv
end
```

VPG works pretty well on simple problem. it uses MC returns $G_t$ to estimate the action-advantage function. There is no bias in VPG.  
Sometime it is good to add a little bit of bias to reduce the variance. AC2 uses several methods to deal with variance.

>- Use n-steps returns with boostrapping and robust GAE to estimate the action-advantage function
>- Use multiple workers to roll out sample in parallel from multiple environments, this decorrelate the gathered data and reduce variance for training (like the replay buffer, but here there is no storage needed)

<center>In VPG, we estimate the action-advantage function as follow</center> 
<br>
<center>$\boxed{A(S_t, A_t; \phi) = G_t - V(S_t; \phi)}$</center> 
<br>
<br>

In A2C, we use an **n-steps** (partial return) version of the action-advantage function instead of the full return  
<center>$\boxed{A(S_t, A_t; \phi) = R_t + \gamma R_{t+1} + ... + \gamma^n R_{t+n} + \gamma^{n+1} V(S_{t+n+1}; \phi) - V(S_t; \phi)}$</center> 
<br>

##### Generalized Advantage estimator (GAE)

Aditionally, we use the **(GAE)**, to make a more robust estimate of the action-advantage function $A^{GAE}$, here is how to construct it  
<br>

>1. Compute the **left hand-side** (partial return or n-steps version) of the action-advantage function:
<center>
    $A(S_t, A_t; \phi) = R_t + \gamma R_{t+1} + ... + \gamma^n R_{t+n} + \gamma^{n+1} V(S_{t+n+1}; \phi)$
</center>  

```python
n_step_returns = []
for w in range(self.n_workers):
    for t_step in range(T):
        discounted_reward = discounts[:T-t_step] * rewards[t_step:, w]
        n_step_returns.append(np.sum(discounted_reward))
```
<br>

We use n-steps but we dont know what is a good value for n,  n > 1 if usually good but:
- if n is too large it will be as the full MC return (more variance, as in VPG)
- if too small it will be to close to the one-step TD update (more biased)

We can use a weighted combination of all n-steps action-advantage target as a single target. That mean, the more n is large, the less impact the action-advantage target will have. We will in fact **discount** the action-advantage target by a exponentially decaying factor $\lambda$.  
<br>

>2. Get the lambda $\lambda$ and apply the discount factor on it
<center>$\sum_{l=0}^\infty (\gamma \lambda)^l$</center> 

```python
lambda_discounts = np.logspace(start=0, stop=T-1, num=T-1, base=self.gamma*self.lambdaa, endpoint=False)
```
<br>
  
>3. Calculate TD errors
<center>$\sum_{t=0}^T R_t * \gamma V(S_{t+1}) - V(S_t)$</center>

```python
td_errors = rewards[:-1] + self.gamma * values[1:] - values[:-1]
```
<br>

>4. Apply the $\lambda$ discounts on the TD errors, hence produce the robust estimator $A^{GAE}$
<center>$A^{GAE} = \sum_{l=0}^\infty (\gamma \lambda)^l * R_t * \gamma V(S_{t+1}) - V(S_t)$</center>

```python
gaes = []
for w in range(self.n_workers):
    for t_step in range(T-1):
        discounted_advantage = lambda_discounts[:T-1-t_step] * td_errors[t_step:, w]
        gaes.append(np.sum(discounted_advantage))
```
<br>

>5. Apply on top, the regular discount on $A^{GAE}$
<center>$\gamma  A^{GAE}$</center>

```python
discounted_gaes = discounts[:-1] * gaes
```
<br>


Loss for the Policy Part is:  
#### <center>$\boxed{L(\theta) = -\frac{1}{N}  \sum_{n=0}^N [\gamma A^{GAE} * log \pi (A_t | S_t;  \theta) + \beta H(\pi (S_t;  \theta))]}$</center>  
<br> 

Loss for the Value Part is:

#### <center>$\boxed{L(\phi) = \frac{1}{N}  \sum_{n=0}^N [(R_t + \gamma R_{t+1} + ... + \gamma^n R_{t+n} + \gamma^{n+1} V(S_{t+n+1}; \phi) - V(S_t; \phi))^2]}$</center>

Since we have one single network sharing the weights, we add the two losses together  
#### <center>$\boxed{L(\theta; \phi) = L(\theta) + L(\phi)}$</center>  

```python
value_error = n_step_returns - values

value_loss = value_error.pow(2).mul(0.5).mean()
policy_loss = -(discounted_gaes.detach() * logpas).mean()
entropy_loss = -entropies.mean()

loss = (policy_loss_weight * policy_loss) +  (value_loss_weight * value_loss) +  (entropy_loss_weight * entropy_loss )    
```
[![PyTorch](https://img.shields.io/badge/PyTorch-%23EE4C2C.svg?style=for-the-badge&logo=PyTorch&logoColor=white)](
    https://github.com/Mdhvince/reinforcement_learning/blob/master/deep_rl/policy_based_and_ac/a2c.py
)


# Advanced Actor-Critic methods

This section hold more advanced actor-critic algorithms. These algorithms are able to solve more complex task with high dimentional inputs and continous action-space. 

## Deep Deterministic Policy Gradient: DDPG

<center>Uses of ideas from DQN, construct a Q-target but using Q-Funtion network AND Deterministic Policy network. (deterministic here means, same state gives same action)</center>

  ```mermaid
%%{ init: { 'flowchart': { 'curve': 'basis' } } }%%
graph

subgraph DDPG

   subgraph Target and Behavior Value Network
        id1((s1)) & id2((s2)) & id3((s3)) & id4((s4)) ---> 
        h1((h1)) & h2((h2)) & h3((h3)) & h4((h4)) & h5((h5)) & hn((hn)) ---> v1((Q_sa))
    end

    subgraph Target and Behavior Policy Network
        i1((s1)) & i2((s2)) & i3((s3)) & i4((s4)) ---> 
        hh1((h1)) & hh2((h2)) & hh3((h3)) & hh4((h4)) & hh5((h5)) & hh6((hn)) ---> a((a))
    end

end

```

- The Value Network have nS (state size) inputs and 1 output that represent the value of a state-action pair $Q(s, a)$
- The Policy Network have nS (state size) inputs and nA outputs that represent the deterministic action.


As in DQN, the agent interact with the environment and store experiences in the replay memory. Then sample a mini-batch from it at random. From there we compute the losses.  
<br>

Output the action (a') from the __target__ Policy network using the sampled "next-state" from the replay memory
#### <center>$\boxed{ E_{(-, -, -, s') \sim U(D)} \mu(s'; \phi^-) = a'}$</center>  
<br>  
  
Get the sampled action (a) directly from the replay memory
#### <center>$\boxed{E_{(-, a, -, -) \sim U(D)} = a}$</center> 
<br>  

From the actions "a" and "a'", we can construct the target $Q(s', a')$ and the online $Q(s, a)$

Get the state-action pair value from the __target__ value network  
#### <center>$\boxed{ E_{(-, -, r -) \sim U(D)} Q(s', \mu(s'; \phi^-); \theta^-) = r + \gamma Q(s', a'; \theta^-)}$</center> 
<br>  

Get the state-action pair value from the __behavior__ value network  
#### <center>$\boxed{Q(s, a; \theta_i)}$</center> 
<br> 

Remember in DQN, we improve the behavior networks, then copy the weight to the target after n steps of after each steps if we use Polyak averaging.  
  
Loss for the __Behavior__ Value network: 
#### <center>$\boxed{L_i(\theta) = E_{(s, a, r, s') \sim U(D)} [(r + \gamma Q(s', \mu(s'; \phi^-); \theta^-) - Q(s, a; \theta _i))^2]}$</center>  
<br> 

From here we have used the Target Policy network to get action "a'", the Target Value network to get Q(s', a') and the behavior value network to get Q(s, a).  
<br> 

Use the __Behavior__ Policy network to compute what we think is the best action, using the sampled "state" from the replay memory:
#### <center>$\boxed{ E_{(s, -, -, -) \sim U(D)} \mu(s; \phi_i) = a_{predicted}}$</center> 
<br>  

Use the __Behavior__ Value network to compute what we think is the value of the state-action_predicted pair:
#### <center>$\boxed{Q(s, a_{predicted}; \theta_i)}$</center> 
<br> 

Loss for the __Behavior__ Policy network: 
#### <center>$\boxed{L_i(\phi) = -\frac{1}{N} \sum_{n=0}^N Q(s, a_{predicted}; \theta_i)} $</center>  
<br>

In my version of DDPG, I use Polyak Avering to update the target network weights after each step.

![DDPG Pendulum](deep_rl/policy_based_and_ac/gifs/ddpg.gif)

  
[![PyTorch](https://img.shields.io/badge/PyTorch-%23EE4C2C.svg?style=for-the-badge&logo=PyTorch&logoColor=white)](
    https://github.com/Mdhvince/reinforcement_learning/blob/master/deep_rl/policy_based_and_ac/ddpg.py
)

## TD3: Twin-delayed DDPG (SOTA improvement of DDPG)
<center>Use of a twin network (2 independants streams) to give 2 estimates of the Q function (critic). Add noises to bothe the online action (as in ddpg) and the target action. Delay the update of the actor to give the critic enough time to settle with more accurate estimate.</center>

  ```mermaid
%%{ init: { 'flowchart': { 'curve': 'basis' } } }%%
graph

subgraph Critic TWIN Network 

   subgraph Critic Twin-A
        id1((s1)) & id2((s2)) & id3((s3)) & id4((s4)) ---> 
        h1((h1)) & h2((h2)) & h3((h3)) & h4((h4)) & h5((h5)) & hn((hn)) ---> v1((Q_a))
    end

    subgraph Critic Twin-B
        idd1((s1)) & idd2((s2)) & idd3((s3)) & idd4((s4)) ---> 
        hh1((h1)) & hh2((h2)) & hh3((h3)) & hh4((h4)) & hh5((h5)) & hhn((hn)) ---> vv1((Q_b))
    end

end
```

<center>The Actor network remain unchanged from the one done previously in DDPG</center>  

```mermaid
%%{ init: { 'flowchart': { 'curve': 'basis' } } }%%
graph

subgraph Actor Network
    i1((s1)) & i2((s2)) & i3((s3)) & i4((s4)) ---> 
    hh1((h1)) & hh2((h2)) & hh3((h3)) & hh4((h4)) & hh5((h5)) & hh6((hn)) ---> a((a))
end

```

As in DDPG, the agent store experiences in a replay buffer then sample from it to start the learning process.  

##### Main improvements
__Target Smoothing__  
- Compute noise for the __target action__ (in ddpg noise is only applied on the online action). Training the policy with noisy targets can be seen as a regularizer because the network is now forced to generalize over similar actions.  

```python
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
```

Once the noisy action is computed, the Q-value from the Twin network in the __minimum__ Q-value of the 2 streams. From it we can compute the Q-target.  

```python
# Get Q_next from the TWIN critic, which is the min Q between the two streams
Q_target_stream_a, Q_target_stream_b = self.critic_target(next_states, noisy_a_next)
Q_next = torch.min(Q_target_stream_a, Q_target_stream_b)
Q_target = rewards + self.gamma * Q_next * (1 - is_terminals)
```

__Loss__
- We compute a single loss for the critic despite the 2 streams

```python
Q_stream_a, Q_stream_b = self.critic(states, actions)
error_a = Q_stream_a - Q_target
error_b = Q_stream_b - Q_target

critic_loss = error_a.pow(2).mul(0.5).mean() + error_b.pow(2).mul(0.5).mean()
```

__Delays actor update__
- We delay actor update, so the critic is updated at higher rate. This give the critic the time to settle into more accurate values because it is more sensible.

```python
if t_step % self.train_actor_every == 0:
    a_pred = self.actor(states)

    # here we choose one of the 2 streams and we stick to it
    Q_pred = self.critic.Qa(states, a_pred) 

    actor_loss = -Q_pred.mean()
``` 

I have tested TD3 in the Hooper environment, here is the result.  
![TD3 Hopper](deep_rl/policy_based_and_ac/gifs/td3Hopper.gif)


[![PyTorch](https://img.shields.io/badge/PyTorch-%23EE4C2C.svg?style=for-the-badge&logo=PyTorch&logoColor=white)](
    https://github.com/Mdhvince/reinforcement_learning/blob/master/deep_rl/policy_based_and_ac/td3.py
)