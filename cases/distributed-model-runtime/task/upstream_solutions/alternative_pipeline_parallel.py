"""Independent all-forward/all-backward pipeline schedule for equivalence."""

from typing import Optional

import torch
import torch.distributed as dist
import torch.nn as nn
import torch.nn.functional as F


def _exchange(*, send_previous=None, receive_previous=None, send_next=None, receive_next=None):
    rank = dist.get_rank()
    world = dist.get_world_size()
    operations = []
    if rank > 0 and send_previous is not None:
        operations.append(dist.P2POp(dist.isend, send_previous, rank - 1))
    if rank > 0 and receive_previous is not None:
        operations.append(dist.P2POp(dist.irecv, receive_previous, rank - 1))
    if rank + 1 < world and send_next is not None:
        operations.append(dist.P2POp(dist.isend, send_next, rank + 1))
    if rank + 1 < world and receive_next is not None:
        operations.append(dist.P2POp(dist.irecv, receive_next, rank + 1))
    for request in dist.batch_isend_irecv(operations) if operations else []:
        request.wait()
    return receive_previous, receive_next


def train_step_pipeline_afab(model, inputs, targets, device, dtype):
    rank = dist.get_rank()
    world = dist.get_world_size()
    base = model.model
    count = len(base.layers)
    per_rank = [count // world + (index < count % world) for index in range(world)]
    start = sum(per_rank[:rank])
    base.layers = nn.ModuleList(base.layers[start:start + per_rank[rank]])
    if rank:
        base.embed_tokens = nn.Identity()
    if rank + 1 < world:
        base.norm = nn.Identity()
        model.lm_head = nn.Identity()

    batch, sequence = inputs[0].shape
    shape = (batch, sequence, model.config.hidden_size)
    saved_inputs = []
    saved_outputs = []
    for input_ids in inputs:
        if rank == 0:
            input_tensor = input_ids.to(device)
        else:
            buffer = torch.empty(shape, requires_grad=True, device=device, dtype=dtype)
            input_tensor = _exchange(receive_previous=buffer)[0]
        output = model(input_tensor)[0]
        _exchange(send_next=output)
        if rank + 1 == world:
            output = F.cross_entropy(
                output.reshape(-1, output.size(-1)),
                targets[len(saved_inputs)].to(device).reshape(-1),
                ignore_index=-100,
            ) / len(inputs)
        saved_inputs.append(input_tensor)
        saved_outputs.append(output)

    for input_tensor, output in zip(saved_inputs, saved_outputs):
        if input_tensor.requires_grad:
            input_tensor.retain_grad()
        if rank + 1 == world:
            torch.autograd.backward(output)
        else:
            buffer = torch.empty(shape, requires_grad=True, device=device, dtype=dtype)
            output_gradient = _exchange(receive_next=buffer)[1]
            torch.autograd.backward(output, grad_tensors=output_gradient)
        _exchange(send_previous=input_tensor.grad)
