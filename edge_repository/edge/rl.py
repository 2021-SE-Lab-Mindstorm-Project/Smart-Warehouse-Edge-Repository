import torch
from torch import nn


class DQN(nn.Module):
    def __init__(self, input_size, path=''):
        super(DQN, self).__init__()
        self.input_size = input_size

        self.model = nn.Sequential(
            nn.Linear(self.input_size, 512),
            nn.ReLU(),
            nn.Linear(512, 512),
            nn.ReLU(),
            nn.Linear(512, 4)
        )

        if path != '':
            self.load_state_dict(torch.load(path, map_location=torch.device("cpu")))
            self.eval()


    def select_tactic(self, state, available=None):
        if available is None:
            available = [True] * self.output_size

        sorted_result = self.model(state).sort()
        i = 0
        while i < self.output_size:
            if available[sorted_result.indices[0][i]]:
                return sorted_result.indices[0][i]
            i += 1
