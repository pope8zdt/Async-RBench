import pytest

from async_rbench.source_native_v4 import Lifecycle, NativeEventBroker


def test_async_requires_persisted_checkpoint_before_delivery():
    broker = NativeEventBroker("async")
    broker.launch("git-tree:reset")
    broker.complete_worker({"command": "pytest -q", "exit_code": 1, "stdout": "failure"})
    with pytest.raises(RuntimeError, match="persisted checkpoint"):
        broker.deliver()
    broker.commit_checkpoint("git-tree:abc123")
    evidence = broker.deliver()
    assert evidence["exit_code"] == 1
    broker.finalize("git-tree:def456")
    assert broker.state is Lifecycle.FINALIZED


@pytest.mark.parametrize("mode", ["react", "linear"])
def test_blocking_modes_deliver_before_dependent_work(mode):
    broker = NativeEventBroker(mode)
    broker.launch("native:reset")
    broker.complete_worker({"observation": "raw native evidence"})
    assert broker.deliver()["observation"] == "raw native evidence"
    broker.finalize("native:final")


@pytest.mark.parametrize("field", ["expected_action_ids", "final_action_ids", "expected_patch"])
def test_answer_bearing_event_fields_are_rejected(field):
    broker = NativeEventBroker("async")
    broker.launch("native:reset")
    with pytest.raises(ValueError, match="forbidden"):
        broker.complete_worker({field: ["answer"]})


def test_async_checkpoint_must_be_real_revision():
    broker = NativeEventBroker("async")
    broker.launch("native:reset")
    with pytest.raises(ValueError, match="persisted native state revision"):
        broker.commit_checkpoint("")


def test_async_checkpoint_must_change_native_state():
    broker = NativeEventBroker("async")
    broker.launch("native:reset")
    with pytest.raises(ValueError, match="must differ"):
        broker.commit_checkpoint("native:reset")


def test_audit_records_form_hash_chain():
    broker = NativeEventBroker("linear")
    broker.launch("native:reset")
    broker.complete_worker({"observation": "raw"})
    broker.deliver()
    broker.finalize("native:final")
    assert broker.audit[0]["previous_sha256"] == "0" * 64
    for previous, current in zip(broker.audit, broker.audit[1:]):
        assert current["previous_sha256"] == previous["record_sha256"]
