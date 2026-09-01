from __future__ import annotations

from pathlib import Path

from async_rbench.evaluation.contract import validate_kernel_adapter_contract


ROOT = Path(__file__).resolve().parents[1]


def _scaffold_docs(root: Path) -> None:
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "kernel-contract.md").write_text("# kernel contract", encoding="utf-8")
    (root / "docs" / "adapter-contract.md").write_text("# adapter contract", encoding="utf-8")


def test_kernel_adapter_boundary_is_clean():
    # The real repository must not violate the boundary: the two contract
    # documents exist, no kernel module imports the profile layer, and no
    # profile invokes docker directly.
    assert validate_kernel_adapter_contract(ROOT) == []


def test_kernel_profile_import_is_flagged(tmp_path: Path):
    _scaffold_docs(tmp_path)
    evaluation_dir = tmp_path / "async_rbench" / "evaluation"
    evaluation_dir.mkdir(parents=True)
    (evaluation_dir / "bad.py").write_text(
        "from async_rbench.profiles import load_profile\n", encoding="utf-8"
    )
    errors = validate_kernel_adapter_contract(tmp_path)
    assert any("imports the profile layer" in error and "bad.py" in error for error in errors)


def test_profile_docker_call_is_flagged(tmp_path: Path):
    _scaffold_docs(tmp_path)
    profiles_dir = tmp_path / "async_rbench" / "profiles"
    profiles_dir.mkdir(parents=True)
    (profiles_dir / "bad.py").write_text(
        'import subprocess\nsubprocess.run(["docker", "ps"])\n', encoding="utf-8"
    )
    errors = validate_kernel_adapter_contract(tmp_path)
    assert any("docker" in error and "bad.py" in error for error in errors)


def test_profile_mention_of_docker_is_not_flagged(tmp_path: Path):
    # A profile that merely *mentions* docker (in a comment or docstring) is
    # not a contract violation — only a direct container primitive call is.
    _scaffold_docs(tmp_path)
    profiles_dir = tmp_path / "async_rbench" / "profiles"
    profiles_dir.mkdir(parents=True)
    (profiles_dir / "ok.py").write_text(
        "# docker isolation is provided by the kernel, not this profile\n", encoding="utf-8"
    )
    assert validate_kernel_adapter_contract(tmp_path) == []


def test_profiles_source_does_not_construct_the_workspace_runtime_directly():
    # The capability RPC moved workspace execution back into the kernel: profiles
    # must request capabilities over stdio via CapabilityRuntimeProxy, never
    # import the kernel's Docker runtime or build it in-process.
    profiles_dir = ROOT / "async_rbench" / "profiles"
    offenders = []
    for path in profiles_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for needle in ("build_workspace_runtime(", "DockerWorkspaceRuntime"):
            if needle in text:
                offenders.append(f"{path.relative_to(ROOT)}: {needle}")
    assert offenders == []
