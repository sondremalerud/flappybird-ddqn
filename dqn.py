import numpy as np
import signal
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from collections import namedtuple, deque
import random
import matplotlib.pyplot as plt
import flappy_bird_gymnasium
import gymnasium

env = gymnasium.make("FlappyBird-v0", render_mode="human")
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

Transition = namedtuple('Transition', ('state', 'action', 'next_state', 'reward', 'done'))
class ReplayBuffer(object):
# https://pytorch.org/tutorials/intermediate/reinforcement_q_learning.html

    def __init__(self, capacity):
        self.memory = deque([], maxlen=capacity)

    def push(self, *args):
        """Save a transition"""
        self.memory.append(Transition(*args))

    def sample(self, batch_size):
        return random.sample(self.memory, batch_size)

    def __len__(self):
        return len(self.memory)
    
class Model(nn.Module):
    def __init__(self,observation_num, num_action ):
        super(Model, self).__init__()
        self.observation_num = observation_num
        self.num_action = num_action

        self.layer1 = nn.Linear(self.observation_num, 128)
        self.layer2 = nn.Linear(128, 64)
        self.layer3 = nn.Linear(64, self.num_action)


    def forward(self,x):
        x = F.relu(self.layer1(x))
        x = F.relu(self.layer2(x))
        x = self.layer3(x)
        return x


class Agent:
    def __init__(self,
                 env,
                 observation_space_n,
                 action_space_n,
                 memory_capacity=50_000,
                 discount=0.99,
                 learning_rate=0.0001,
                 exp_rate=0.1,
                 min_exp_rate=0.001,
                 exp_decay=0.995,
                 ):
        
        self.device = device
        self.env = env

        self.action_space_n = action_space_n
        self.observation_space_n = observation_space_n

        # parameters
        self.memory_capacity = memory_capacity
        self.discount = discount
        self.learning_rate = learning_rate
        self.exp_rate = exp_rate
        self.min_exp_rate = min_exp_rate
        self.exp_decay = exp_decay

        # networks
        self.model = Model(self.observation_space_n, self.action_space_n).to(device)
        self.target_model = Model(self.observation_space_n, self.action_space_n).to(device)

        # agent memory
        self.replay_memory = ReplayBuffer(self.memory_capacity)

        # rewards
        self.rewards = []

        # optimizer
        self.optimizer = optim.Adam(self.model.parameters(), lr=self.learning_rate)

        # self.target_model.eval()
        self.target_model.load_state_dict(self.model.state_dict())


    def update_target_model(self):
        self.target_model.load_state_dict(self.model.state_dict())

    def get_exploration_rate(self):
        """ returns exploration rate """

        return max(self.exp_rate, self.min_exp_rate)

    def update_exploration_rate(self):
        """ Updates exploration rate """

        self.exp_rate = self.exp_rate * self.exp_decay
        return self.exp_rate

    def save_model(self):
        """ Saves model to the .pth file format """

        torch.save(self.model.state_dict(), "dqn.pth")
        print("saved model to 'dqn.pth'")

    def load_model(self):
        """ Loads network from .pth file """

        self.model.load_state_dict(torch.load("dqn.pth"))
        self.model.eval()

    def action(self, state):
        """ Selects an action using the epsilon-greedy strategy """

        #FIXME state = state.reshape(1, 4, 30, 30) # needs extra dim for batch of size 1
        exploration_rate_threshold = np.random.random()  # random float between 0-1
        exploration_rate = self.get_exploration_rate()
        

        if exploration_rate_threshold <= exploration_rate:  # do random action
            action = random.randrange(0, self.action_space_n)
            action_t = torch.tensor([[action]], device=device, dtype=torch.int64)
        else:
            action_argmax = self.model(torch.tensor(state, device=device, dtype=torch.float32)).argmax() 
            action = action_argmax
            action_t = action.reshape(1, 1)
        return action_t
    

    def optimize(self, batch_size):
        """" Samples from replay_memory.
             Does optimizer step and updates model """

        if len(self.replay_memory) < batch_size:
            return

        transitions = self.replay_memory.sample(batch_size)
        batch = Transition(*zip(*transitions))

        state_b = torch.cat(batch.state) 
        next_state_b = torch.cat(batch.next_state) 
        action_b = torch.cat(batch.action)
        done_t = torch.cat(batch.done).unsqueeze(1) 
   
        target_q = self.target_model(next_state_b) 
   
        max_target_q = torch.max(target_q, dim=1, keepdim=True)[0] 
       
        r = torch.cat(batch.reward)  
        r.unsqueeze_(1) 

        # Q(s, a) = r + γ * max(Q(s', a')) ||
        # Q(s, a) = r                      || if state is done
        Q_sa = r + self.discount * max_target_q * (1 - done_t)  # if done = 1 => Q_result = r
        Q_sa = Q_sa.reshape(-1, 1)
      
        predicted = torch.gather(input=self.model(state_b), dim=1, index=action_b) 
        loss = nn.functional.mse_loss(predicted, Q_sa)
        self.optimizer.zero_grad()
        loss.backward()

        # Graident clipping
        CLIP_NORM = 0.6
        torch.nn.utils.clip_grad_norm_(self.model.parameters(),CLIP_NORM)

        self.optimizer.step()


    def plot_rewards(self):
        """ Plots mean rewards in a line diagram """
        mean_rewards = []

        for t in range(len(self.rewards)):
            mean_rewards.append(np.mean(self.rewards[max(0, t-100):(t+1)]))
        plt.plot(mean_rewards)
        plt.xlabel('Episode')
        plt.ylabel('Mean Reward')
        plt.savefig('rewards.png')

    def train(self, episodes=100, steps=10_000):
        """ Trains model for n episodes (does not save the model) """
        self.rewards = []
        initial_state, _ = env.reset()
        total_steps = 0

        for episode in range(episodes):
            ep_reward = 0
            state, _ = env.reset()

            for s in range(steps):
                action = agent.action(state)
                next_state, reward, terminated, truncated, _ = env.step(action.item())

                ep_reward += reward
                reward = torch.tensor([reward], device=device)

                done = terminated or truncated
                done_t = torch.tensor(done, dtype=torch.float32, device=device).unsqueeze(0)

                state_t = torch.tensor(state,dtype=torch.float32, device=device).unsqueeze(0)
                next_state_t = torch.tensor(next_state, dtype=torch.float32,device=device).unsqueeze(0)

                # store
                agent.replay_memory.push(state_t, action, next_state_t, reward, done_t)

                # optimize
                agent.optimize(batch_size)

                state = next_state
        
                if total_steps % update_frequency == 0:
                    agent.update_target_model()

                total_steps+=1

                if done:
                    break

            self.rewards.append(ep_reward)
            print("episode: " + str(episode) + " reward: " + str(round(ep_reward, 3)))
            if episode % 100 == 0:
                print(f'exp_rate: {agent.get_exploration_rate()}')
            self.update_exploration_rate()


    def custom_interrupt_handler(self,signum, frame):
        """ This function will be called when Ctrl+C is pressed """

        print("\nCustom interrupt handler activated.")
        self.save_model()
        print("Q_values saved")
        self.plot_rewards()

        exit()


batch_size = 128 # For memory buffer batch
update_frequency = 1000

obs, _ = env.reset()
input_size = obs.shape[0] 
output_size = 2 # 2 possible actions

agent = Agent(env, input_size, output_size)

# Register the custom interrupt handler for Ctrl+C (SIGINT)
signal.signal(signal.SIGINT, agent.custom_interrupt_handler)

agent.train(episodes=50_000)

env.close()