import copy
import io
import stat
import zipfile

import pytest
from private_review_fixtures import full_evidence, archive_files, zip_bytes


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    evidence = full_evidence(tmp_path_factory.mktemp("private-evidence"))
    return evidence, archive_files(evidence)


def test_full_originals_are_checked_and_bytes_preserved(sample, tmp_path):
    from async_rbench.submissions.private_review.bundle import inspect_bundle, pack_bundle
    evidence, files = sample
    raw = pack_bundle(*evidence[:4])
    result = inspect_bundle(raw, tmp_path / "private", evidence[-1])
    assert result["metrics"] == {"drs": 62.5, "success": 50.0, "tasks": 200, "episodes": 600, "repetitions": 3}
    assert (tmp_path / "private/runs/case-000-0-async/event_source.jsonl").read_bytes() == files["runs/case-000-0-async/event_source.jsonl"]


@pytest.mark.parametrize("kind", ["traversal", "extra", "missing", "tamper", "secret", "duplicate", "symlink", "partial-policy"])
def test_invalid_archive_never_becomes_approved_evidence(sample, tmp_path, kind):
    from async_rbench.submissions.private_review.bundle import inspect_bundle
    evidence, source = sample
    files, policy = dict(source), copy.deepcopy(evidence[-1])
    if kind == "traversal": files["../escape.json"] = b"{}"
    if kind == "extra": files["profile.yaml"] = b"secret"
    if kind == "missing": files.pop("runs/case-000-0-async/score.json")
    if kind == "tamper": files["runs/case-000-0-async/event_source.jsonl"] += b" "
    if kind == "secret": files["audit.json"] = files["audit.json"][:-1] + b',"api_key":"should-stay-secret"}'
    if kind == "partial-policy": policy["cases"].popitem()
    raw = zip_bytes(files)
    if kind in {"duplicate", "symlink"}:
        stream = io.BytesIO(raw)
        with zipfile.ZipFile(stream, "a") as archive:
            if kind == "duplicate":
                with pytest.warns(UserWarning): archive.writestr("audit.json", files["audit.json"])
            else:
                info = zipfile.ZipInfo("runs/link/score.json")
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(info, "../../audit.json")
        raw = stream.getvalue()
    with pytest.raises(ValueError): inspect_bundle(raw, tmp_path / "private", policy)
    assert not (tmp_path / "escape.json").exists()


def test_size_limits_and_existing_target_are_not_overwritten(sample, tmp_path, monkeypatch):
    from async_rbench.submissions.private_review import bundle
    evidence, files = sample
    target = tmp_path / "private"
    target.mkdir()
    (target / "keep").write_text("owned")
    with pytest.raises(ValueError): bundle.inspect_bundle(zip_bytes(files), target, evidence[-1])
    assert (target / "keep").read_text() == "owned"
    monkeypatch.setattr(bundle, "MAX_ARCHIVE", 10)
    with pytest.raises(ValueError): bundle.inspect_bundle(zip_bytes(files), tmp_path / "new", evidence[-1])
