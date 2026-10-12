import asyncio
import json
import shlex
import subprocess
import sys
import os
import pytest
from types import SimpleNamespace

from async_rbench.evaluation import runner, scoring
from async_rbench.evaluation.protocol import TraceRecorder
from async_rbench.evaluation.workspace_runtime import CommandResult
from async_rbench.evaluation.artifact_observation import artifact_snapshot_command


class LocalWorkspace:
    async def main_terminal(self, command, timeout):
        argv = shlex.split(command)
        assert argv[0] in {"python", "python3"}
        result = subprocess.run([sys.executable, *argv[1:]], capture_output=True, text=True, timeout=timeout)
        return CommandResult(result.returncode, result.stdout + result.stderr)


class Pipe:
    def __init__(self):
        self.data = bytearray()

    def write(self, data):
        self.data.extend(data)

    async def drain(self):
        pass


def test_main_terminal_dispatch_captures_state_without_exposing_private_observations(tmp_path):
    artifact = tmp_path / "result.json"
    command = "python3 -c " + shlex.quote(
        f"from pathlib import Path; Path({str(artifact)!r}).write_text('updated')")
    recorder = TraceRecorder("dispatch-observation")
    pipe = Pipe()
    process = SimpleNamespace(stdin=pipe)
    asyncio.run(runner._dispatch_capability(
        LocalWorkspace(), {"request_id": "r", "capability": "main_terminal",
                           "args": {"command": command, "timeout": 10}},
        process, asyncio.Lock(), recorder=recorder,
        case_spec={"artifacts": [{"id": "result", "path": str(artifact)}]},
    ))
    assert json.loads(pipe.data)["ok"] is True
    observation = recorder.events[-1]
    assert observation["type"] == "artifact_state_observed"
    assert observation["exists"] is True
    assert observation["source"] == "kernel"
    assert observation["observed_digest"] not in pipe.data.decode()


def test_kernel_observes_damage_and_restore_without_participant_commits(tmp_path):
    artifact = tmp_path / "protected.txt"
    artifact.write_text("valid", encoding="utf-8")
    spec = {"artifacts": [{"id": "protected", "path": str(artifact)}]}
    recorder = TraceRecorder("observation-test")

    async def run():
        await runner._observe_artifact_states_private(LocalWorkspace(), spec, recorder, "presentation")
        boundary = recorder.record({"type": "result_presented"}, "adapter")["seq"]
        artifact.write_text("damage", encoding="utf-8")
        await runner._observe_artifact_states_private(LocalWorkspace(), spec, recorder, "main_terminal")
        artifact.write_text("valid", encoding="utf-8")
        await runner._observe_artifact_states_private(LocalWorkspace(), spec, recorder, "termination")
        return boundary

    boundary = asyncio.run(run())
    observations = [e for e in recorder.events if e["type"] == "artifact_state_observed"]
    assert len(observations) == 3
    assert all(e["visibility"] == "kernel_private" for e in observations)
    before, after, history = scoring._event_state_evidence(
        {"protected": observations}, {"protected"}, boundary, 100,
    )
    assert before == after
    assert history["protected"][0]["observed_digest"] != before["protected"]


def test_missing_file_is_observed_absence_not_missing_evidence(tmp_path):
    spec = {"artifacts": [{"id": "absent", "path": str(tmp_path / "absent.json")}]}
    recorder = TraceRecorder("missing-file")
    asyncio.run(runner._observe_artifact_states_private(LocalWorkspace(), spec, recorder, "presentation"))
    event = recorder.events[-1]
    assert event["exists"] is False
    assert len(event["observed_digest"]) == 64
    assert "observation_error" not in event


def test_failed_observation_cannot_carry_forward_a_good_digest():
    before, after, history = scoring._event_state_evidence(
        {"a": [{"seq": 1, "observed_digest": "a" * 64},
               {"seq": 3, "observed_digest": None, "observation_error": "unreadable"}]},
        {"a"}, 2, 4,
    )
    assert before == {"a": "a" * 64}
    assert "a" not in after
    assert history["a"][0]["observed_digest"] is None


def test_snapshot_command_uses_the_python3_available_in_linux_task_images():
    assert shlex.split(artifact_snapshot_command([]))[0] == "python3"


@pytest.mark.skipif(os.name == "nt", reason="POSIX raw-byte filename; covered in Docker smoke")
def test_snapshot_hashes_non_utf8_posix_filenames(tmp_path):
    (tmp_path / os.fsdecode(b"name-\xff.txt")).write_bytes(b"content")
    recorder = TraceRecorder("raw-filename")
    asyncio.run(runner._observe_artifact_states_private(LocalWorkspace(), {
        "artifacts": [{"id": "tree", "path": str(tmp_path)}]}, recorder, "presentation"))
    assert len(recorder.events[-1]["observed_digest"]) == 64
