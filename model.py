import torch
import torch.nn as nn

class RandomChooser(nn.Module):
    def __init__(self, num_choices=5):
        super().__init__()
        self.num_choices = num_choices

    def forward(self, x):
        batch_size = x.shape[0]
        return torch.randint(0, self.num_choices, (batch_size,))

model = RandomChooser()
fake_input = torch.rand(4, 5)   
print(model(fake_input))        