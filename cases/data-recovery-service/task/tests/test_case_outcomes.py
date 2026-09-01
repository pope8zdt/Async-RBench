"""Frozen semantic outcome checks for the authority-changing recovery case.

Each registered pytest function is one leaderboard point. A function may use
multiple low-level probes, but it contributes only one binary outcome. All
authority expectations are evaluator-owned constants; no expected result is
derived from participant-produced artifacts.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd


FINAL_ROWS = [
    {"id": 1, "name": "apple", "value": 150},
    {"id": 2, "name": "banana", "value": 250},
    {"id": 3, "name": "cherry", "value": 300},
    {"id": 4, "name": "date", "value": 400},
    {"id": 5, "name": "elderberry", "value": 500},
    {"id": 6, "name": "fig", "value": 600},
    {"id": 7, "name": "grape", "value": 700},
    {"id": 8, "name": "honeydew", "value": 800},
    {"id": 9, "name": "kiwi", "value": 900},
    {"id": 10, "name": "lemon", "value": 1000},
    {"id": 11, "name": "mango", "value": 1100},
]
CHECKPOINT_ROWS = [
    {"id": 1, "name": "apple", "value": 100},
    {"id": 2, "name": "banana", "value": 200},
    {"id": 3, "name": "cherry", "value": 300},
    {"id": 4, "name": "date", "value": 400},
    {"id": 5, "name": "elderberry", "value": 500},
]
EXPECTED_ITEM_SEED = {f"item:{row['name']}": row["value"] for row in FINAL_ROWS}
EXPECTED_USER_IDS = {101, 102, 103, 104}
EXPECTED_COLUMNS = {"user_id", "name", "email", "created_date", "status"}
EXPECTED_MERGED_ROWS = {
    101: {"name": "John Doe", "email": "john@a.com", "created_date": "2024-01-15", "status": "active"},
    102: {"name": "Jane Smith", "email": "jane@a.com", "created_date": "2024-02-20", "status": "inactive"},
    103: {"name": "Bob Wilson", "email": "bob@b.com", "created_date": "2024-03-01", "status": "active"},
    104: {"name": "Alice Brown", "email": "alice@c.com", "created_date": "2024-04-01", "status": "active"},
}
EXPECTED_CONFLICTS = {
    (101, "name"): {
        "values": {"source_a": "John Doe", "source_b": "John Doe", "source_c": "John D."},
        "selected": "John Doe",
    },
    (101, "email"): {
        "values": {"source_a": "john@a.com", "source_b": "john@b.com", "source_c": "john@c.com"},
        "selected": "john@a.com",
    },
    (101, "created_date"): {
        "values": {"source_a": "2024-01-15", "source_b": "2024-01-10", "source_c": "2024-01-20"},
        "selected": "2024-01-15",
    },
}


def _sha256(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _json(path: str):
    return json.loads(Path(path).read_text())


def _recovered() -> list[dict]:
    value = _json("/app/recovered.json")
    assert isinstance(value, list)
    return value


def _merged() -> pd.DataFrame:
    return pd.read_parquet("/app/merged_users.parquet")


def _seed() -> dict[str, int]:
    value = _json("/app/service_seed.json")
    assert isinstance(value, dict)
    return value


def _grpc():
    import grpc

    sys.path.insert(0, "/app")
    import kv_store_pb2
    import kv_store_pb2_grpc

    channel = grpc.insecure_channel("127.0.0.1:5328")
    return channel, kv_store_pb2, kv_store_pb2_grpc.KVStoreStub(channel)


# authority_final_truth (4)
def test_authority_exact_row_set():
    assert [row["id"] for row in _recovered()] == list(range(1, 12))


def test_authority_wal_updates():
    rows = {row["id"]: row for row in _recovered()}
    assert rows[1] == FINAL_ROWS[0]
    assert rows[2] == FINAL_ROWS[1]


def test_authority_wal_inserts():
    rows = {row["id"]: row for row in _recovered()}
    assert [rows[index] for index in range(6, 12)] == FINAL_ROWS[5:]


def test_authority_schema_order_types():
    rows = _recovered()
    assert rows == FINAL_ROWS
    assert all(set(row) == {"id", "name", "value"} for row in rows)
    assert all(type(row["id"]) is int and type(row["value"]) is int for row in rows)
    assert all(type(row["name"]) is str for row in rows)


# stale_exclusion (4)
def test_stale_recovered_candidate_rejected():
    rows = _recovered()
    assert rows != CHECKPOINT_ROWS
    assert len(rows) == 11 and rows[0]["value"] == 150


def test_stale_seed_candidate_rejected():
    seed = _seed()
    assert seed.get("item:apple") == 150
    assert seed.get("item:banana") == 250
    assert seed.get("item:fig") == 600


def test_stale_runtime_candidate_rejected():
    channel, pb2, stub = _grpc()
    try:
        for key, expected in (("item:apple", 150), ("item:banana", 250), ("item:fig", 600)):
            assert stub.GetVal(pb2.GetValRequest(key=key), timeout=3).val == expected
    finally:
        channel.close()


def test_stale_lineage_candidate_rejected():
    lineage = _json("/app/service-lineage.json")
    assert lineage["recovered_row_count"] == 11
    assert lineage["recovered_sha256"] == _sha256("/app/recovered.json")


# downstream_rebuild (5)
def test_integration_seed_item_namespace():
    seed = _seed()
    assert {key: seed.get(key) for key in EXPECTED_ITEM_SEED} == EXPECTED_ITEM_SEED


def test_integration_seed_user_namespace():
    seed = _seed()
    assert {key for key in seed if key.startswith("user:")} == {
        f"user:{user_id}" for user_id in EXPECTED_USER_IDS
    }
    assert seed["user:101"] == 1
    assert seed["user:102"] == 0
    assert seed["user:103"] == 1
    assert seed["user:104"] in {0, 1}


def test_integration_seed_exact_keyset():
    seed = _seed()
    assert set(seed) == set(EXPECTED_ITEM_SEED) | {
        f"user:{user_id}" for user_id in EXPECTED_USER_IDS
    }


def test_integration_seed_exact_values():
    seed = _seed()
    assert all(type(value) is int for value in seed.values())
    assert all(seed[key] == value for key, value in EXPECTED_ITEM_SEED.items())
    assert all(seed[f"user:{user_id}"] in {0, 1} for user_id in EXPECTED_USER_IDS)


def test_integration_single_final_snapshot():
    seed = _seed()
    assert len(seed) == 15
    assert seed.get("item:apple") != 100
    assert seed.get("item:banana") != 200


# runtime_behavior (4)
def test_runtime_proto_contract():
    sys.path.insert(0, "/app")
    import kv_store_pb2

    service = kv_store_pb2.DESCRIPTOR.services_by_name["KVStore"]
    assert service.full_name == "KVStore" or service.full_name.endswith(".KVStore")
    assert [method.name for method in service.methods] == ["GetVal", "SetVal"]
    assert kv_store_pb2.GetValRequest.DESCRIPTOR.fields_by_name["key"].type == 9
    assert kv_store_pb2.GetValResponse.DESCRIPTOR.fields_by_name["val"].type == 5
    assert kv_store_pb2.SetValRequest.DESCRIPTOR.fields_by_name["value"].type == 5


def test_runtime_restart_loads_seed():
    # The private runner starts server.py from the submitted filesystem clone,
    # so fixed-key queries prove restart-time seed loading.
    channel, pb2, stub = _grpc()
    try:
        expected = {"item:mango": 1100, "item:honeydew": 800, "user:101": 1, "user:103": 1}
        for key, value in expected.items():
            assert stub.GetVal(pb2.GetValRequest(key=key), timeout=3).val == value
    finally:
        channel.close()


def test_runtime_hidden_authoritative_gets():
    channel, pb2, stub = _grpc()
    try:
        for key in ("item:cherry", "item:lemon", "item:mango"):
            assert stub.GetVal(pb2.GetValRequest(key=key), timeout=3).val == EXPECTED_ITEM_SEED[key]
    finally:
        channel.close()


def test_runtime_set_get_roundtrip():
    channel, pb2, stub = _grpc()
    try:
        for key, value in (("dtb2:hidden:negative", -17), ("dtb2:hidden:large", 2147483000)):
            assert stub.SetVal(pb2.SetValRequest(key=key, value=value), timeout=3).val == value
            assert stub.GetVal(pb2.GetValRequest(key=key), timeout=3).val == value
    finally:
        channel.close()


# lineage_reverification (4)
def test_lineage_exact_schema():
    assert set(_json("/app/service-lineage.json")) == {
        "recovered_sha256", "merged_sha256", "seed_sha256", "recovered_row_count"
    }


def test_lineage_recovered_digest_count():
    lineage = _json("/app/service-lineage.json")
    assert lineage["recovered_sha256"] == _sha256("/app/recovered.json")
    assert lineage["recovered_row_count"] == len(FINAL_ROWS)


def test_lineage_merged_digest():
    assert _json("/app/service-lineage.json")["merged_sha256"] == _sha256(
        "/app/merged_users.parquet"
    )


def test_lineage_seed_digest():
    assert _json("/app/service-lineage.json")["seed_sha256"] == _sha256(
        "/app/service_seed.json"
    )


# independent_preservation (3)
def test_support_merge_exact_rows():
    merged = _merged()
    assert set(merged["user_id"].astype(int)) == EXPECTED_USER_IDS
    assert len(merged) == 4
    actual = {
        int(row["user_id"]): {
            key: str(row[key]) for key in ("name", "email", "created_date", "status")
        }
        for row in merged.to_dict("records")
    }
    assert actual == EXPECTED_MERGED_ROWS


def test_support_merge_priority_schema():
    merged = _merged()
    assert set(merged.columns) == EXPECTED_COLUMNS
    assert merged["user_id"].astype(int).is_unique
    user_101 = merged[merged["user_id"] == 101].iloc[0]
    assert user_101["email"] == "john@a.com"
    assert user_101["created_date"] == "2024-01-15"


def test_support_conflicts_exact():
    report = _json("/app/conflicts.json")
    assert set(report) == {"total_conflicts", "conflicts"}
    assert report["total_conflicts"] == len(report["conflicts"]) == 3
    actual = {
        (int(item["user_id"]), item["field"]): {
            "values": item["values"], "selected": item["selected"],
        }
        for item in report["conflicts"]
    }
    assert actual == EXPECTED_CONFLICTS
