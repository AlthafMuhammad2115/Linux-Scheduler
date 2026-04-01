import torch
import random
import torch.nn as nn
import torch.optim as optim
import numpy as np
from collections import deque
from datetime import datetime

# ========== SIMPLE TERMINAL LOGGER ==========

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] AGENT | {msg}", flush=True)

# ========== DQN NETWORK ==========

class DQN(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(12, 64),
            nn.ReLU(),
            nn.Linear(64, 64),
            nn.ReLU(),
            nn.Linear(64, 3)
        )

    def forward(self, x):
        return self.net(x)

# ========== REPLAY BUFFER ==========

class ReplayBuffer:
    def __init__(self, capacity=1000):
        self.buffer = deque(maxlen=capacity)
    
    def push(self, state, action, reward, next_state):
        self.buffer.append((state, action, reward, next_state))
    
    def sample(self, batch_size):
        batch = random.sample(self.buffer, batch_size)
        state, action, reward, next_state = zip(*batch)
        return state, action, reward, next_state
    
    def __len__(self):
        return len(self.buffer)

# ========== AGENT ==========

class Agent:
    def __init__(self):
        self.policy_net = DQN()
        self.target_net = DQN()
        self.target_net.load_state_dict(self.policy_net.state_dict())
        self.target_net.eval()
        
        self.opt = optim.Adam(self.policy_net.parameters(), lr=1e-3)
        self.memory = ReplayBuffer(capacity=2000)
        self.batch_size = 32
        self.gamma = 0.95
        self.eps = 1.0
        
        log("Agent initialized with Replay Buffer & Target Net")

    def act(self, state):
        # log(f"Epsilon = {self.eps:.3f}")

        if random.random() < self.eps:
            action = random.randint(0, 2)
            # log(f"Exploration → Random action {action}")
        else:
            state_t = torch.tensor(state, dtype=torch.float32)
            with torch.no_grad():
                qvals = self.policy_net(state_t).numpy()
            action = int(qvals.argmax())
            # log(f"Exploitation → Best action {action} | Qs: {qvals}")

        return action

    def train(self, s, a, r, ns):
        # Store transition
        self.memory.push(s, a, r, ns)
        
        if len(self.memory) < self.batch_size:
            return

        # Sample batch
        states, actions, rewards, next_states = self.memory.sample(self.batch_size)

        states_t = torch.tensor(np.array(states), dtype=torch.float32)
        actions_t = torch.tensor(actions, dtype=torch.long)
        rewards_t = torch.tensor(rewards, dtype=torch.float32)
        next_states_t = torch.tensor(np.array(next_states), dtype=torch.float32)

        # Compute Q(s, a)
        q_values = self.policy_net(states_t).gather(1, actions_t.unsqueeze(1)).squeeze(1)

        # Compute target Q using Target Network
        with torch.no_grad():
            next_q_values = self.target_net(next_states_t).max(1)[0]
            expected_q_values = rewards_t + self.gamma * next_q_values

        loss = nn.MSELoss()(q_values, expected_q_values)

        self.opt.zero_grad()
        loss.backward()
        self.opt.step()

        # Soft update target network
        tau = 0.01
        for param, target_param in zip(self.policy_net.parameters(), self.target_net.parameters()):
            target_param.data.copy_(tau * param.data + (1.0 - tau) * target_param.data)

        # log(f"Network updated | Loss = {loss.item():.5f}")

    def save(self, filepath="rl_model.pth"):
        torch.save(self.policy_net.state_dict(), filepath)
        log(f"Model saved to {filepath}")

    def load(self, filepath="rl_model.pth"):
        import os
        if os.path.exists(filepath):
            self.policy_net.load_state_dict(torch.load(filepath, weights_only=True))
            self.target_net.load_state_dict(self.policy_net.state_dict())
            self.policy_net.eval()
            log(f"Model loaded from {filepath}")
        else:
            log(f"WARNING: No saved model found at {filepath}!")
