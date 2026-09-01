"""Create the supported local Python environment for source-native MARBLE."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from async_rbench.marble_runtime import (  # noqa: E402
    MARBLE_NATIVE_RUNTIME_IMPORTS,
    MARBLE_UPSTREAM_DEPENDENCY_COVERAGE,
    MARBLE_UPSTREAM_DEPENDENCY_EXCLUSIONS,
    discover_supported_python,
    stage_marble_runtime,
)


PORTABILITY_DEPENDENCIES = (
    "aiohttp==3.10.10",
    "arxiv==2.1.3",
    "beartype==0.19.0",
    "beautifulsoup4==4.12.3",
    "bs4==0.0.2",
    "flask==3.1.2",
    "keybert==0.8.5",
    "levenshtein==0.26.1",
    "litellm==1.52.1",
    "mypy==1.14.1",
    "names==0.3.0",
    "openai==1.54.4",
    "httpx==0.27.2",
    "psycopg2-binary==2.9.10",
    "PyMySQL==1.1.1",
    "PyPDF2==3.0.1",
    "ruamel.yaml==0.18.6",
    "colorama==0.4.6",
    "colorlog==6.9.0",
    "lxml==5.3.0",
    "semanticscholar==0.8.4",
    "types-pyyaml==6.0.12.20240917",
    "types-requests==2.32.0.20240914",
    "waitress==3.0.2",
)
REQUIREMENTS_LOCK = ROOT / "configs/marble-native-requirements.lock"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", default=None)
    parser.add_argument("--venv", default=".venv-marble-native")
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Replace only the explicitly selected MARBLE virtual environment.",
    )
    return parser.parse_args()


def _run(command: list[str], *, timeout: int = 1800) -> None:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"MARBLE bootstrap command failed ({completed.returncode}): {command}"
        )


def _venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def _base_interpreter(selected: str) -> str:
    completed = subprocess.run(
        [
            selected,
            "-c",
            "import sys; print(getattr(sys, '_base_executable', sys.executable))",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    base = completed.stdout.strip()
    supported, _error = discover_supported_python(base if base else selected)
    if completed.returncode != 0 or supported is None:
        raise RuntimeError("unable to resolve a supported MARBLE base interpreter")
    return supported


def _is_isolated_venv(venv: Path) -> bool:
    config = venv / "pyvenv.cfg"
    if not config.is_file():
        return False
    normalized = config.read_text(encoding="utf-8").lower().replace(" ", "")
    return "include-system-site-packages=false" in normalized


def _python_runtime_metadata(python: Path) -> dict[str, object]:
    completed = subprocess.run(
        [
            str(python),
            "-c",
            (
                "import json,platform,sys; "
                "print(json.dumps({"
                "'version':platform.python_version(),"
                "'version_info':list(sys.version_info[:3]),"
                "'executable':sys.executable,"
                "'prefix':sys.prefix,"
                "'base_prefix':sys.base_prefix},sort_keys=True))"
            ),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise RuntimeError("failed to inspect the MARBLE Python runtime")
    try:
        result = json.loads(completed.stdout.strip())
    except (json.JSONDecodeError, TypeError) as exc:
        raise RuntimeError("invalid MARBLE Python runtime metadata") from exc
    result.update(
        {
            "executable": str(Path(str(result["executable"])).resolve()),
            "prefix": str(Path(str(result["prefix"])).resolve()),
            "base_prefix": str(Path(str(result["base_prefix"])).resolve()),
            "system_site_packages": False,
        }
    )
    if result.get("version_info", [None, None])[:2] not in (
        [3, 9],
        [3, 10],
        [3, 11],
    ):
        raise RuntimeError("MARBLE Python runtime version is unsupported")
    if Path(str(result["prefix"])).resolve() == Path(
        str(result["base_prefix"])
    ).resolve():
        raise RuntimeError("MARBLE Python runtime is not a virtual environment")
    return result


def _install_and_verify(
    uv: str, venv: Path, lock_path: Path, expected_lock: str
) -> str:
    python = _venv_python(venv)
    _run(
        [
            uv,
            "pip",
            "install",
            "--link-mode",
            "copy",
            "--python",
            str(python),
            "--no-deps",
            "--requirement",
            str(lock_path),
        ]
    )
    _run([uv, "pip", "check", "--python", str(python)], timeout=300)
    with tempfile.TemporaryDirectory(prefix="dtbench-marble-bootstrap-") as directory:
        staged = stage_marble_runtime(
            ROOT / "upstream/marble", Path(directory) / "runtime"
        )
        environment = __import__("os").environ.copy()
        environment["PYTHONPATH"] = str(staged)
        completed = subprocess.run(
            [
                str(python),
                "-c",
                (
                    "import importlib,json,sys; from pathlib import Path; "
                    "marble=importlib.import_module('marble'); "
                    "sys.path.insert(0,str(Path(marble.__file__).parent/"
                    "'environments'/'db_env_docker'/'anomaly_trigger')); "
                    "modules=json.loads(sys.argv[1]); "
                    "[importlib.import_module(name) for name in modules]; "
                    "print(json.dumps(modules))"
                ),
                json.dumps(list(MARBLE_NATIVE_RUNTIME_IMPORTS)),
            ],
            cwd=staged,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "MARBLE actual import probe failed: "
                + (completed.stderr or completed.stdout)[-1000:]
            )
    frozen = subprocess.run(
        [uv, "pip", "freeze", "--python", str(python)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if frozen.returncode != 0 or not frozen.stdout.strip():
        raise RuntimeError("failed to freeze MARBLE dependencies")
    actual_lock = frozen.stdout.replace("\r\n", "\n").rstrip() + "\n"
    if actual_lock != expected_lock:
        raise RuntimeError("installed MARBLE environment differs from pinned lock")
    return actual_lock


def main() -> int:
    args = parse_args()
    selected, error = discover_supported_python(args.python)
    if selected is None:
        print(error, file=sys.stderr)
        return 1
    uv = shutil.which("uv")
    if uv is None:
        print("uv is required to create the MARBLE runtime", file=sys.stderr)
        return 1
    if not REQUIREMENTS_LOCK.is_file():
        print(f"MARBLE dependency lock missing: {REQUIREMENTS_LOCK}", file=sys.stderr)
        return 1
    expected_lock = (
        REQUIREMENTS_LOCK.read_text(encoding="utf-8")
        .replace("\r\n", "\n")
        .rstrip()
        + "\n"
    )

    venv = (ROOT / args.venv).resolve()
    try:
        venv.relative_to(ROOT)
    except ValueError:
        print("MARBLE venv must stay inside the workspace", file=sys.stderr)
        return 1
    if venv == ROOT:
        print("workspace root cannot be used as the MARBLE venv", file=sys.stderr)
        return 1

    base = _base_interpreter(selected)
    venv_python = _venv_python(venv)
    try:
        if args.recreate:
            with tempfile.TemporaryDirectory(
                prefix=".marble-venv-rebuild-", dir=venv.parent
            ) as rebuild_parent:
                replacement = Path(rebuild_parent) / "venv"
                _run([uv, "venv", "--python", base, str(replacement)])
                lock_payload = _install_and_verify(
                    uv, replacement, REQUIREMENTS_LOCK, expected_lock
                )
                backup = venv.with_name(venv.name + ".bootstrap-backup")
                if backup.exists():
                    raise RuntimeError(f"refusing to overwrite backup path: {backup}")
                if venv.exists():
                    venv.replace(backup)
                try:
                    replacement.replace(venv)
                except Exception:
                    if backup.exists() and not venv.exists():
                        backup.replace(venv)
                    raise
                if backup.exists():
                    if backup.parent != venv.parent or backup.name != (
                        venv.name + ".bootstrap-backup"
                    ):
                        raise RuntimeError("unsafe MARBLE venv backup path")
                    shutil.rmtree(backup)
        else:
            if not venv_python.is_file():
                _run([uv, "venv", "--python", base, str(venv)])
            if not _is_isolated_venv(venv):
                print(
                    "existing MARBLE venv is not isolated; rerun with --recreate",
                    file=sys.stderr,
                )
                return 1
            lock_payload = _install_and_verify(
                uv, venv, REQUIREMENTS_LOCK, expected_lock
            )
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    venv_python = _venv_python(venv)
    existing_python, existing_error = discover_supported_python(str(venv_python))
    if existing_python is None or not _is_isolated_venv(venv):
        print(existing_error or "MARBLE venv isolation check failed", file=sys.stderr)
        return 1
    lock_path = ROOT / "artifacts/native-runtime-v4/marble_native_dependencies.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(lock_payload, encoding="utf-8", newline="\n")
    lock_sha256 = hashlib.sha256(lock_payload.encode("utf-8")).hexdigest()
    try:
        python_runtime = _python_runtime_metadata(venv_python)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    report = {
        "schema_version": "marble-local-runtime-bootstrap-v2",
        "status": "dependencies_importable",
        "python": str(venv_python.resolve()),
        "python_runtime": python_runtime,
        "system_site_packages": False,
        "upstream": str((ROOT / "upstream/marble").resolve()),
        "portability_dependencies": list(PORTABILITY_DEPENDENCIES),
        "upstream_dependency_coverage": list(
            MARBLE_UPSTREAM_DEPENDENCY_COVERAGE
        ),
        "intentional_exclusions": list(MARBLE_UPSTREAM_DEPENDENCY_EXCLUSIONS),
        "case_scenarios": ["bargaining", "coding", "database", "research"],
        "import_checks": list(MARBLE_NATIVE_RUNTIME_IMPORTS),
        "dependency_lock": str(lock_path.resolve()),
        "dependency_lock_source": str(REQUIREMENTS_LOCK.resolve()),
        "dependency_lock_sha256": lock_sha256,
        "actual_engine_evaluator_import": True,
        "pip_check": True,
    }
    report_path = ROOT / "artifacts/native-runtime-v4/marble_bootstrap_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
