import torch
import random
import torch.nn as nn
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

# ========== AGENT ==========

class Agent:
    def __init__(self):
        self.model = DQN()
        self.opt = torch.optim.Adam(self.model.parameters(), lr=1e-3)
        self.eps = 1.0
        log("Agent initialized")

    def act(self, state):
        log(f"Epsilon = {self.eps:.3f}")

        state_t = torch.tensor(state, dtype=torch.float32)

        qvals = self.model(state_t).detach().numpy()
        log(f"Q-values = {qvals}")

        if random.random() < self.eps:
            action = random.randint(0, 2)
            log(f"Exploration → Random action {action}")
        else:
            action = int(qvals.argmax())
            log(f"Exploitation → Best action {action}")

        return action

    def train(self, s, a, r, ns):
        s  = torch.tensor(s, dtype=torch.float32)
        ns = torch.tensor(ns, dtype=torch.float32)

        q  = self.model(s)[a]
        t  = r + 0.9 * torch.max(self.model(ns)).detach()

        loss = (q - t) ** 2

        log(f"Reward = {r:.3f} | Loss = {loss.item():.5f}")

        self.opt.zero_grad()
        loss.backward()
        self.opt.step()

        log("Network updated")
