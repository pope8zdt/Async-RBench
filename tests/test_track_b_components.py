from __future__ import annotations

from pathlib import Path

import pytest

from async_rbench.track_b.components import load_component
from async_rbench.track_b.config import TrackBConfig
from async_rbench.track_b.contracts import ContextBuilder, FrameworkRequest, PublicEpisodeContext


class _ContextBuilder:
    def build(self, context: PublicEpisodeContext) -> FrameworkRequest:
        return FrameworkRequest(messages=({"role": "user", "content": context.instruction},))


def valid_context_builder() -> _ContextBuilder:
    return _ContextBuilder()


def invalid_context_builder() -> object:
    return object()


def _write_config(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_track_b_config_rejects_track_a(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path / "track-b.yaml",
        "track: A\nframework: langgraph\nmodel: test-model\n",
    )

    with pytest.raises(ValueError, match="track must be B"):
        TrackBConfig.from_file(path)


def test_track_b_config_requires_known_framework(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path / "track-b.yaml",
        "track: B\nframework: unknown\nmodel: test-model\n",
    )

    with pytest.raises(ValueError, match="unknown Track B framework"):
        TrackBConfig.from_file(path)


def test_public_metadata_excludes_credential_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRACK_B_SECRET", "secret-value")
    path = _write_config(
        tmp_path / "track-b.yaml",
        "track: B\nframework: langgraph\nmodel: test-model\ncredential_env: TRACK_B_SECRET\n",
    )

    metadata = TrackBConfig.from_file(path).public_metadata()

    assert metadata["credential_env"] == "TRACK_B_SECRET"
    assert "secret-value" not in str(metadata)
    assert len(metadata["config_sha256"]) == 64


def test_component_loader_builds_a_runtime_checked_component() -> None:
    component = load_component(
        f"{__name__}:valid_context_builder",
        ContextBuilder,
    )

    request = component.build(PublicEpisodeContext(instruction="inspect the task"))
    assert request.messages == ({"role": "user", "content": "inspect the task"},)


def test_component_loader_rejects_an_incompatible_factory() -> None:
    with pytest.raises(ValueError, match="ContextBuilder"):
        load_component(f"{__name__}:invalid_context_builder", ContextBuilder)


@pytest.mark.parametrize("spec", ["relative", ".relative:factory", "module:"])
def test_component_loader_requires_absolute_module_factory(spec: str) -> None:
    with pytest.raises(ValueError, match="absolute module:factory"):
        load_component(spec, ContextBuilder)
