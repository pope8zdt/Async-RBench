import json
from pathlib import Path

OUT = Path("/app/output_data")
FIXTURE = Path("/app/task_file/impress_audio_truth.json")


def test_output_files_exist():
    assert (OUT / "presentation_audio.json").is_file()


def test_vlc_audio_is_embedded_on_first_slide():
    artifact = json.loads((OUT / "presentation_audio.json").read_text())
    truth = json.loads(FIXTURE.read_text())
    assert artifact["source_task_id"] == truth["source_task_id"]
    assert artifact["presentation_file"] == truth["presentation_file"]
    assert artifact["slide_index"] == truth["slide_index"]
    assert artifact["audio_source"] == truth["audio_source"]


def test_vlc_audio_has_background_role_and_continues():
    artifact = json.loads((OUT / "presentation_audio.json").read_text())
    truth = json.loads(FIXTURE.read_text())
    assert artifact["source_video"] == truth["source_video"]
    assert artifact["audio_role"] == truth["audio_role"]
    assert artifact["continue_across_slides"] is True


def test_presentation_save_is_persisted():
    artifact = json.loads((OUT / "presentation_audio.json").read_text())
    assert artifact["saved"] is True

def test_presentation_audio_source_is_vlc_derived():
    artifact = json.loads((OUT / "presentation_audio.json").read_text())
    truth = json.loads(FIXTURE.read_text())
    assert artifact["source_video"] == truth["source_video"]
