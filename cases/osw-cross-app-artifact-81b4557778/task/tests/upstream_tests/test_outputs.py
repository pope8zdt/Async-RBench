import json
from pathlib import Path

OUT = Path("/app/output_data")
FIXTURE = Path("/app/task_file/chrome_extension_truth.json")


def test_output_files_exist():
    assert (OUT / "extension_installation.json").is_file()


def test_chrome_extension_manifest_and_path():
    artifact = json.loads((OUT / "extension_installation.json").read_text())
    truth = json.loads(FIXTURE.read_text())
    assert artifact["source_task_id"] == truth["source_task_id"]
    assert artifact["artifact_path"] == truth["artifact_path"]
    assert artifact["manifest_file"] == truth["manifest_file"]
    assert artifact["manifest_name"] == truth["manifest_name"]


def test_chrome_extension_loaded_unpacked_without_error():
    artifact = json.loads((OUT / "extension_installation.json").read_text())
    truth = json.loads(FIXTURE.read_text())
    assert artifact["developer_mode"] is truth["developer_mode"]
    assert artifact["loaded_unpacked"] is truth["loaded_unpacked"]
    assert artifact["load_error"] is None


def test_chrome_extension_target_is_persisted():
    artifact = json.loads((OUT / "extension_installation.json").read_text())
    assert artifact["persisted"] is True

def test_chrome_extension_manifest_version_is_pinned():
    artifact = json.loads((OUT / "extension_installation.json").read_text())
    truth = json.loads(FIXTURE.read_text())
    assert artifact["manifest_version"] == truth["manifest_version"]
