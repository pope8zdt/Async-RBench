"""Independent tensor-parallel linear layers used by the equivalence path."""

import torch
import torch.distributed as dist
import torch.nn.functional as F


class _Copy(torch.autograd.Function):
    @staticmethod
    def forward(ctx, value):
        return value

    @staticmethod
    def backward(ctx, gradient):
        if dist.get_world_size() > 1:
            gradient = gradient.contiguous()
            dist.all_reduce(gradient)
        return gradient


class _Reduce(torch.autograd.Function):
    @staticmethod
    def forward(ctx, value):
        if dist.get_world_size() > 1:
            value = value.contiguous()
            dist.all_reduce(value)
        return value

    @staticmethod
    def backward(ctx, gradient):
        return gradient


class _Gather(torch.autograd.Function):
    @staticmethod
    def forward(ctx, value):
        if dist.get_world_size() == 1:
            return value
        partitions = [torch.empty_like(value) for _ in range(dist.get_world_size())]
        dist.all_gather(partitions, value.contiguous())
        return torch.cat(partitions, dim=-1)

    @staticmethod
    def backward(ctx, gradient):
        if dist.get_world_size() == 1:
            return gradient
        width = gradient.size(-1) // dist.get_world_size()
        start = dist.get_rank() * width
        return gradient[..., start:start + width].clone()


class ColumnParallelLinear(torch.nn.Module):
    def __init__(self, in_features, out_features, bias, master_weight):
        super().__init__()
        world = dist.get_world_size()
        rank = dist.get_rank()
        if out_features % world:
            raise ValueError("out_features must divide evenly across ranks")
        width = out_features // world
        self.weight = torch.nn.Parameter(master_weight[rank * width:(rank + 1) * width].clone())
        self.bias = torch.nn.Parameter(torch.zeros(width)) if bias else None

    def forward(self, value):
        return _Gather.apply(F.linear(_Copy.apply(value), self.weight, self.bias))


class RowParallelLinear(torch.nn.Module):
    def __init__(self, in_features, out_features, bias, master_weight):
        super().__init__()
        world = dist.get_world_size()
        rank = dist.get_rank()
        if in_features % world:
            raise ValueError("in_features must divide evenly across ranks")
        width = in_features // world
        self.weight = torch.nn.Parameter(master_weight[:, rank * width:(rank + 1) * width].clone())
        self.bias = torch.nn.Parameter(torch.zeros(out_features)) if bias else None

    def forward(self, value):
        output = _Reduce.apply(F.linear(value, self.weight))
        return output if self.bias is None else output + self.bias
