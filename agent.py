import torch, random, torch.nn as nn

class DQN(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(12,64), nn.ReLU(),
            nn.Linear(64,64), nn.ReLU(),
            nn.Linear(64,3)
        )

    def forward(self,x): return self.net(x)

class Agent:
    def __init__(self):
        self.model = DQN()
        self.opt = torch.optim.Adam(self.model.parameters(),1e-3)
        self.eps = 1.0

    def act(self,state):
        if random.random() < self.eps:
            return random.randint(0,2)
        return torch.argmax(self.model(torch.tensor(state))).item()

    def train(self,s,a,r,ns):
        s,ns = torch.tensor(s),torch.tensor(ns)
        q = self.model(s)[a]
        t = r + 0.9 * torch.max(self.model(ns))
        loss = (q - t.detach())**2
        self.opt.zero_grad(); loss.backward(); self.opt.step()
