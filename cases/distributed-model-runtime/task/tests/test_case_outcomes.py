"""Frozen semantic checks for authority-driven model runtime deployment."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import sys
from pathlib import Path

import torch
import torch.distributed as dist
import torch.multiprocessing as mp
import torch.nn as nn
import torch.nn.functional as F

sys.path.insert(0, "/app")
sys.path.insert(0, "/async_rbench_tests")

from cost_model_for_tests import CostModel, align


EXPECTED_PROFILE = {
    "version": "v2",
    "world_size": 2,
    "interconnect": "ethernet",
    "tensor_parallel_supported": False,
    "pipeline_parallel_supported": True,
}
INPUT_HASHES = {
    1: "8b3cf1e2b06074162038064dd2c114abe308acd32cec7d365ee63ee81978f7de",
    2: "e15e2d4c4d55f875c42a6042610d6282f6c0657c39d3e0d0f087268252525cb5",
}
THRESHOLDS = {
    1: {"cost": 3.0e11, "pad_ratio": 0.055, "p95_latency_ms": 2.1e6,
        "sequential_timecost": 2.7e8},
    2: {"cost": 4.8e10, "pad_ratio": 0.15, "p95_latency_ms": 2.1e5,
        "sequential_timecost": 3.2e7},
}


def _sha256(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _json(path: str):
    return json.loads(Path(path).read_text())


def _jsonl(path: str) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def _requests(bucket: int) -> list[dict]:
    return _jsonl(f"/app/task_file/input_data/requests_bucket_{bucket}.jsonl")


def _plan(bucket: int) -> list[dict]:
    return _jsonl(f"/app/task_file/output_data/plan_b{bucket}.jsonl")


def _plan_metrics(bucket: int) -> dict:
    requests = {item["request_id"]: item for item in _requests(bucket)}
    return CostModel(granularity=64).plan_metrics(requests, _plan(bucket))


def _load_module(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _pipeline_worker(rank: int, world_size: int, port: int) -> None:
    from transformers import LlamaConfig, LlamaForCausalLM
    from pipeline_parallel import train_step_pipeline_afab

    os.environ["MASTER_ADDR"] = "127.0.0.1"
    os.environ["MASTER_PORT"] = str(port)
    dist.init_process_group("gloo", rank=rank, world_size=world_size)
    try:
        torch.manual_seed(731)
        config = LlamaConfig(
            hidden_size=64, intermediate_size=128, num_attention_heads=4,
            num_hidden_layers=2, vocab_size=128, max_position_embeddings=32,
        )
        model = LlamaForCausalLM(config)
        inputs = [torch.randint(0, 128, (1, 8)) for _ in range(2)]
        targets = []
        for value in inputs:
            target = value.clone()
            target[:, :-1] = value[:, 1:]
            target[:, -1] = -100
            targets.append(target)
        train_step_pipeline_afab(model, inputs, targets, torch.device("cpu"), torch.float32)
        assert any(parameter.grad is not None for parameter in model.parameters())
        dist.barrier()
    finally:
        dist.destroy_process_group()


class _PositionalEncoding(nn.Module):
    def __init__(self, d_model: int, max_len: int = 5000):
        super().__init__()
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        self.register_buffer("pe", pe.unsqueeze(0))

    def forward(self, value):
        return value + self.pe[:, : value.size(1)]


class _RecoveredModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.embedding = nn.Linear(64, 128)
        self.pos_encoder = _PositionalEncoding(128)
        encoder = nn.TransformerEncoderLayer(128, 4, 256, dropout=0.0)
        self.transformer_encoder = nn.TransformerEncoder(encoder, 3)
        decoder = nn.TransformerDecoderLayer(128, 4, 256, dropout=0.0)
        self.transformer_decoder = nn.TransformerDecoder(decoder, 1)
        self.output_layer = nn.Linear(128, 64)

    def forward(self, src, tgt):
        src = self.pos_encoder(self.embedding(src))
        tgt = self.pos_encoder(self.embedding(tgt))
        return self.output_layer(self.transformer_decoder(tgt, self.transformer_encoder(src)))


# authority_final_truth (4)
def test_authority_profile_exact():
    assert _json("/app/profiles/authoritative.json") == EXPECTED_PROFILE


def test_authority_backend_feasible():
    deployment = _json("/app/deployment.json")
    assert deployment["backend"] == "pipeline"
    assert EXPECTED_PROFILE["pipeline_parallel_supported"] is True
    assert EXPECTED_PROFILE["tensor_parallel_supported"] is False


def test_authority_version_world_size():
    deployment = _json("/app/deployment.json")
    assert (deployment["profile_version"], deployment["world_size"]) == ("v2", 2)


def test_authority_implementation_matches_backend():
    deployment = _json("/app/deployment.json")
    assert deployment["implementation_sha256"] == _sha256("/app/pipeline_parallel.py")
    assert deployment["implementation_sha256"] != _sha256("/app/parallel_linear.py")


# stale_exclusion (4)
def test_stale_tensor_candidate_rejected():
    deployment = _json("/app/deployment.json")
    assert deployment["backend"] != "tensor_parallel"
    assert deployment["world_size"] != 4


def test_stale_provisional_profile_rejected():
    provisional = _json("/app/profiles/provisional.json")
    deployment = _json("/app/deployment.json")
    assert provisional["version"] == "v1"
    assert deployment["profile_version"] != provisional["version"]
    assert deployment["world_size"] != provisional["world_size"]


def test_stale_provisional_implementation_rejected():
    deployment = _json("/app/deployment.json")
    assert deployment["implementation_sha256"] != _sha256("/app/parallel_linear.py")


def test_stale_provisional_lineage_rejected():
    lineage = _json("/app/batch-lineage.json")
    assert lineage["backend"] == "pipeline"
    assert lineage["profile_version"] == "v2"
    assert "v1" not in json.dumps(lineage)


# downstream_rebuild (5)
def test_plans_bucket1_complete_unique():
    expected = [item["request_id"] for item in _requests(1)]
    actual = [item["request_id"] for item in _plan(1)]
    assert sorted(actual) == sorted(expected)
    assert len(actual) == len(set(actual))


def test_plans_bucket2_complete_unique():
    expected = [item["request_id"] for item in _requests(2)]
    actual = [item["request_id"] for item in _plan(2)]
    assert sorted(actual) == sorted(expected)
    assert len(actual) == len(set(actual))


def test_plans_final_shape_contract():
    for bucket in (1, 2):
        prompt_lengths = {item["request_id"]: item["prompt_len"] for item in _requests(bucket)}
        batches: dict[str, list[dict]] = {}
        for item in _plan(bucket):
            assert set(item) >= {"request_id", "batch_id", "shape"}
            shape = item["shape"]
            assert shape["heads_align"] == 32 and shape["hidden_align"] == 4096
            assert shape["seq_align"] % 64 == 0
            assert shape["seq_align"] >= align(prompt_lengths[item["request_id"]], 64)
            batches.setdefault(str(item["batch_id"]), []).append(item)
        assert all(len({json.dumps(row["shape"], sort_keys=True) for row in rows}) == 1
                   for rows in batches.values())


def test_plans_global_shape_budget():
    shapes = {
        (item["shape"]["seq_align"], item["shape"]["heads_align"], item["shape"]["hidden_align"])
        for bucket in (1, 2) for item in _plan(bucket)
    }
    assert len(shapes) <= 8


def test_plans_cost_thresholds():
    for bucket, expected_hash in INPUT_HASHES.items():
        path = f"/app/task_file/input_data/requests_bucket_{bucket}.jsonl"
        assert _sha256(path) == expected_hash
        metrics = _plan_metrics(bucket)
        for name, maximum in THRESHOLDS[bucket].items():
            assert metrics[name] <= maximum, f"bucket {bucket} {name}={metrics[name]} > {maximum}"


# runtime_behavior (4)
def test_runtime_model_hidden_inference():
    model = torch.jit.load("/app/model.pt").eval()
    torch.manual_seed(991)
    src = torch.randn(2, 7, 64)
    tgt = torch.randn(2, 7, 64)
    with torch.no_grad():
        output = model(src, tgt)
    assert output.shape == tgt.shape
    assert torch.isfinite(output).all()
    assert float(output.abs().sum()) > 0.0


def test_runtime_pipeline_world_size_one():
    mp.spawn(_pipeline_worker, args=(1, 12471), nprocs=1, join=True)


def test_runtime_pipeline_world_size_two():
    mp.spawn(_pipeline_worker, args=(2, 12472), nprocs=2, join=True)


def test_runtime_selected_backend_smoke():
    module = _load_module("/app/pipeline_parallel.py", "dtb2_selected_pipeline")
    assert callable(module.train_step_pipeline_afab)
    source = Path("/app/pipeline_parallel.py").read_text()
    assert "register_forward_hook" not in source
    assert "register_full_backward_hook" not in source


# lineage_reverification (4)
def test_lineage_deployment_schema():
    assert set(_json("/app/deployment.json")) == {
        "backend", "profile_version", "world_size", "model_sha256",
        "implementation_sha256", "plan_b1_sha256", "plan_b2_sha256",
    }


def test_lineage_model_implementation_hashes():
    deployment = _json("/app/deployment.json")
    assert deployment["model_sha256"] == _sha256("/app/model.pt")
    assert deployment["implementation_sha256"] == _sha256("/app/pipeline_parallel.py")


def test_lineage_plan_hashes():
    deployment = _json("/app/deployment.json")
    assert deployment["plan_b1_sha256"] == _sha256("/app/task_file/output_data/plan_b1.jsonl")
    assert deployment["plan_b2_sha256"] == _sha256("/app/task_file/output_data/plan_b2.jsonl")


def test_lineage_batch_lineage_exact():
    deployment = _json("/app/deployment.json")
    assert _json("/app/batch-lineage.json") == {
        "backend": "pipeline", "profile_version": "v2",
        "plan_b1_sha256": deployment["plan_b1_sha256"],
        "plan_b2_sha256": deployment["plan_b2_sha256"],
    }


# independent_preservation (3)
def test_support_model_quality_improved():
    original = _RecoveredModel().eval()
    original.load_state_dict(torch.load("/app/weights.pt"))
    candidate = torch.jit.load("/app/model.pt").eval()
    dataset = torch.load("/app/dataset.pt")
    src, tgt = dataset["src_sequences"], dataset["tgt_sequences"]
    with torch.no_grad():
        original_loss = F.mse_loss(original(src, tgt), tgt)
        candidate_loss = F.mse_loss(candidate(src, tgt), tgt)
    assert candidate_loss < original_loss


def test_support_tensor_parallel_minimal_numerics():
    os.environ["MASTER_ADDR"] = "127.0.0.1"
    os.environ["MASTER_PORT"] = "12473"
    dist.init_process_group("gloo", rank=0, world_size=1)
    try:
        module = _load_module("/app/parallel_linear.py", "dtb2_parallel_linear")
        torch.manual_seed(177)
        master = torch.randn(12, 8)
        value = torch.randn(3, 8)
        column = module.ColumnParallelLinear(8, 12, False, master.clone())
        assert torch.allclose(column(value), F.linear(value, master), atol=1e-5)
        row = module.RowParallelLinear(8, 12, False, master.clone())
        assert torch.allclose(row(value), F.linear(value, master), atol=1e-5)
    finally:
        dist.destroy_process_group()


def test_support_required_artifacts_usable():
    for path in (
        "/app/model.pt", "/app/parallel_linear.py", "/app/pipeline_parallel.py",
        "/app/task_file/output_data/plan_b1.jsonl",
        "/app/task_file/output_data/plan_b2.jsonl", "/app/deployment.json",
        "/app/batch-lineage.json",
    ):
        assert Path(path).is_file() and Path(path).stat().st_size > 0
