"""MARBLE environment qualification and fail-closed episode preflight.

The offline qualification in this module deliberately stops before an agent acts.
It proves that a source-native case resolves through MARBLE's Config -> Engine ->
Environment -> Evaluator wiring, without pretending that a deterministic stub is a
benchmark model or that an episode has been scored.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import yaml


MARBLE_BENCHMARK = "MultiAgentBench"
MARBLE_SMOKE_STATUS = "environment_smoke_validated"
MARBLE_SMOKE_SCOPE = "infrastructure_smoke"
MARBLE_SMOKE_SCHEMA = "source-native-marble-environment-smoke-v1"
MARBLE_OFFLINE_PROVIDER = "offline/deterministic-healthcheck"
MARBLE_NATIVE_INITIALIZATION_STATUS = "native_environment_initialization_validated"
MARBLE_NATIVE_INITIALIZATION_SCOPE = "native_runtime"
MARBLE_NATIVE_INITIALIZATION_PROFILE = (
    "marble_native_environment_initialization_v1"
)

ENGINE_ENTRYPOINT = "marble.engine.engine.Engine"
CONFIG_ENTRYPOINT = "marble.configs.config.Config"
EVALUATOR_ENTRYPOINT = "marble.evaluator.evaluator.Evaluator"

MARBLE_NATIVE_REQUIREMENTS_LOCK = "configs/marble-native-requirements.lock"
MARBLE_NATIVE_DEPENDENCY_ARTIFACT = (
    "artifacts/native-runtime-v4/marble_native_dependencies.lock"
)
MARBLE_NATIVE_BOOTSTRAP_REPORT = (
    "artifacts/native-runtime-v4/marble_bootstrap_report.json"
)
MARBLE_NATIVE_RUNTIME_IMPORTS = (
    "marble.configs.config",
    "marble.engine.engine",
    "marble.evaluator.evaluator",
    "marble.environments.world_env",
    "marble.environments.coding_env",
    "marble.environments.db_env",
    "marble.environments.research_env",
    "marble.environments.db_env_docker.anomaly_trigger.anomaly",
    "marble.llms.model_prompting",
    "marble.tools.web_search",
    "aiohttp",
    "arxiv",
    "beartype",
    "bs4",
    "flask",
    "Levenshtein",
    "mypy",
    "names",
    "waitress",
)
MARBLE_UPSTREAM_DEPENDENCY_COVERAGE = (
    "arxiv",
    "beartype",
    "beautifulsoup4",
    "bs4",
    "colorlog",
    "flask",
    "keybert",
    "levenshtein",
    "litellm",
    "mypy",
    "names",
    "psycopg2-binary",
    "pydantic",
    "pymysql",
    "pypdf2",
    "requests",
    "scikit-learn",
    "semanticscholar",
    "tqdm",
    "types-pyyaml",
    "types-requests",
    "waitress",
)
MARBLE_UPSTREAM_DEPENDENCY_EXCLUSIONS = (
    {
        "name": "javascript",
        "reason": (
            "Minecraft-only bridge; the source-native-v4 MARBLE collection contains "
            "only bargaining, coding, database, and research cases"
        ),
    },
)
MARBLE_REGISTRY_MERGE_ENVELOPES = {
    "environment_smoke",
    "model_execution",
    "native_environment",
    "native_environment_initialization",
}


@dataclass(frozen=True)
class ScenarioBinding:
    environment_type: str
    environment_entrypoint: str
    evaluator_method: str
    prompt_section: str | None
    external_service: str | None = None


SCENARIO_BINDINGS: dict[str, ScenarioBinding] = {
    "bargaining": ScenarioBinding(
        "WorldSimulation",
        "marble.environments.world_env.WorldSimulationEnvironment",
        "evaluate_task_world",
        "world",
    ),
    "coding": ScenarioBinding(
        "Coding",
        "marble.environments.coding_env.CodingEnvironment",
        "evaluate_code_quality",
        None,
    ),
    "database": ScenarioBinding(
        "DB",
        "marble.environments.db_env.DBEnvironment",
        "evaluate_task_db",
        None,
        external_service="docker-compose-postgres-prometheus",
    ),
    "research": ScenarioBinding(
        "Research",
        "marble.environments.research_env.ResearchEnvironment",
        "evaluate_task_research",
        "research",
    ),
}

ENVIRONMENT_FILES = {
    "bargaining": "marble/environments/world_env.py",
    "coding": "marble/environments/coding_env.py",
    "database": "marble/environments/db_env.py",
    "research": "marble/environments/research_env.py",
}

SUPPORTED_COORDINATION_MODES = {"star", "graph", "chain", "tree"}
MODEL_PLACEHOLDERS = {"${MARBLE_MODEL}", "${MARBLE_EVALUATOR_MODEL}"}
OFFLINE_PROVIDER_NAMES = {MARBLE_OFFLINE_PROVIDER, "offline/deterministic"}
MARBLE_STAGING_ADAPTER = "temporary_portable_marble_runtime_v1"
PINNED_STAGING_SOURCE_SHA256 = {
    "marble/environments/base_env.py": "b38f07b5b870320b33759265f3b4e82b125619b03e9059f2f5041a946dfebadc",
    "marble/evaluator/evaluator.py": "cc9234a9003792538acc5e01579f484d16446da696319cb0c34a7f3466990ad8",
    "marble/engine/engine.py": "649867349144d057db96638275568186b67d379d3b07b5a1b4884d17e94c7c52",
    "marble/environments/db_env.py": "1a9aebef53eac4c93e040d0f34837cebc371a8e32217a105c3bce351142ebc8f",
    "marble/environments/minecraft_env.py": "326740364d674fb14719da9f4b551e9cda03da9f7ec13d9687685273f70e2631",
    "marble/environments/db_env_docker/anomaly_trigger/anomaly.py": "f9ee0a708ad8b8c1f8235d28f41319a0e41d4d9da92ec10df9395145b45d926a",
}
PINNED_STAGING_OUTPUT_SHA256 = {
    "marble/environments/base_env.py": "73fa111dfa5d5a792c2f35b4ae82895d30c6cf0242bd49307100a7ced1cc744c",
    "marble/evaluator/evaluator.py": "71e6013a8c14f29c1dd0870b3da44a221f256a74e66e3c34ebc666534f7779c4",
    "marble/engine/engine.py": "16c15eb459b685b192ea68a6c5ac66026e41236a3a6e4accc0766dcad73042a3",
    "marble/environments/db_env.py": "30c51d69bd4543a419e7d8dc228b0bacf85a304ffabdbf04a5cda969c42fa3e5",
    "marble/environments/minecraft_env.py": "15eb94cc9129dc5ce094f8bfa4aa63ca981fad748cf82abc037c9c140dc7e1e8",
    "marble/environments/db_env_docker/anomaly_trigger/anomaly.py": "50f4bf250e2ab60d0388ba6128d8faa8038ab3be057a911e6de7a3a94db16ab2",
}
DATABASE_IMAGE_REFERENCES = {
    "prometheus": "prom/prometheus:master@sha256:981e8cce3b654c9d5bd3784771cb01d4ab54ebf4092c81dc4ecb3756e162c06a",
    "postgres_db": "postgres:17@sha256:67f41722b7a8cbdb868a44a4995c846eddfdc2973bccb291ce937dce88ad5675",
    "node_exporter": "prom/node-exporter:latest@sha256:1b4e4438faca4dd7e001dd445d161a4a2091b0fededa84093b3a8dfeae1f1be0",
    "pg_exporter": "wrouesnel/postgres_exporter:latest@sha256:54bd3ba6bc39a9da2bf382667db4dc249c96e4cfc837dafe91d6cc7d362829e0",
}
DATABASE_COMPOSE_ASSET_PATH = (
    "marble/environments/db_env_docker/docker-compose.yml"
)
DATABASE_COMPOSE_SOURCE_SHA256 = (
    "c7dbdea73e68419bdb7f91dc0857452497f7e9d641aff9c2c8f5636c3a6dbdfa"
)
DATABASE_COMPOSE_STAGED_SHA256 = (
    "b2ae2da3c485669f51811a6b36cf35bf4858eddfa737e739d4ae834e3400201e"
)


_BROKEN_RESEARCH_RATINGS_BLOCK = '''            if json_start >= 0 and json_end > json_start:
                json_str = content[json_start:json_end]
                ratings = json.loads(json_str)
                # Ensure ratings are integers
                ratings_dict: Dict[str, int] = {k: int(v) for k, v in ratings.items()}
                return ratings_dict
            except json.JSONDecodeError:
                self.logger.error("Failed to parse JSON from assistant's answer.")
                return {}
        else:
            self.logger.error("No JSON found in assistant's answer.")
            return {}
'''

_FIXED_RESEARCH_RATINGS_BLOCK = '''            if json_start < 0 or json_end <= json_start:
                self.logger.error("No JSON found in assistant's answer.")
                return {}

            json_str = content[json_start:json_end]
            ratings = json.loads(json_str)
            # Ensure ratings are integers
            ratings_dict: Dict[str, int] = {k: int(v) for k, v in ratings.items()}
            return ratings_dict
        except (json.JSONDecodeError, TypeError, ValueError):
            self.logger.error("Failed to parse JSON from assistant's answer.")
            return {}
'''


def _replace_exact(
    source: str,
    old: str,
    new: str,
    label: str,
    *,
    expected_count: int = 1,
) -> str:
    actual = source.count(old)
    if actual != expected_count:
        raise MarbleQualificationError(
            f"marble_staging_patch_drift:{label}:expected_{expected_count}:found_{actual}"
        )
    return source.replace(old, new)


def _repair_evaluator_syntax(source: str) -> str:
    return _replace_exact(
        source,
        _BROKEN_RESEARCH_RATINGS_BLOCK,
        _FIXED_RESEARCH_RATINGS_BLOCK,
        "evaluator_research_ratings_syntax",
    )


class MarbleQualificationError(ValueError):
    """A case cannot be bound to the checked-in MARBLE runtime."""


class OfflineDeterministicProvider:
    """A non-model provider restricted to an infrastructure healthcheck.

    It intentionally has no task-completion method.  Calling ``complete_task`` is
    always an error so this object cannot accidentally generate a fake episode.
    """

    provider_id = MARBLE_OFFLINE_PROVIDER

    def healthcheck(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if set(request) != {"operation", "nonce"}:
            raise MarbleQualificationError("offline_provider_invalid_healthcheck_shape")
        if request.get("operation") != "healthcheck":
            raise MarbleQualificationError("offline_provider_refuses_non_healthcheck")
        nonce = str(request.get("nonce") or "")
        if not re.fullmatch(r"[0-9a-f]{64}", nonce):
            raise MarbleQualificationError("offline_provider_invalid_nonce")
        return {
            "operation": "healthcheck_ack",
            "nonce": nonce,
            "provider": self.provider_id,
            "network_calls": 0,
            "task_completion": False,
        }

    def complete_task(self, *_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError(
            "offline deterministic provider is infrastructure-smoke-only and "
            "must never be used as a MARBLE model episode"
        )


class LocalMarbleEnvironment:
    """Dependency-free control plane for MARBLE environment lifecycle smoke.

    This adapter does not impersonate ``marble.engine.Engine`` and cannot execute
    task actions.  It only proves reset semantics, transcript persistence, state
    revision changes, and audit-chain integrity around a native-shaped healthcheck.
    """

    adapter_id = "LocalMarbleEnvironment"

    def __init__(
        self,
        *,
        case_id: str,
        source_task_id: str,
        scenario: str,
        environment_type: str,
        config_sha256: str,
    ) -> None:
        self._identity = {
            "case_id": case_id,
            "source_task_id": source_task_id,
            "scenario": scenario,
            "environment_type": environment_type,
            "config_sha256": config_sha256,
        }
        self._state: dict[str, Any] = {
            **self._identity,
            "phase": "created",
            "sequence": 0,
            "transcript": [],
        }
        self.audit: list[dict[str, Any]] = []

    def _state_digest(self) -> str:
        return _json_digest(self._state)

    def _append_audit(self, event: str) -> None:
        body: dict[str, Any] = {
            "event": event,
            "state_sha256": self._state_digest(),
            "previous_sha256": (
                self.audit[-1]["record_sha256"] if self.audit else "0" * 64
            ),
        }
        body["record_sha256"] = _json_digest(body)
        self.audit.append(body)

    def start(self) -> str:
        if self._state["phase"] != "created":
            raise RuntimeError("local MARBLE control plane may only start once")
        self._state["phase"] = "started"
        self._append_audit("control_plane_started")
        return self._state_digest()

    def reset(self) -> str:
        if self._state["phase"] == "created":
            raise RuntimeError("local MARBLE control plane must start before reset")
        self._state = {
            **self._identity,
            "phase": "ready",
            "sequence": 0,
            "transcript": [],
        }
        self._append_audit("environment_reset")
        return self._state_digest()

    def append_healthcheck(
        self, provider_response: Mapping[str, Any]
    ) -> tuple[dict[str, Any], str]:
        if self._state["phase"] != "ready":
            raise RuntimeError("local MARBLE environment is not ready")
        if provider_response.get("operation") != "healthcheck_ack":
            raise MarbleQualificationError("control_plane_provider_ack_invalid")
        sequence = int(self._state["sequence"]) + 1
        transcript_event = {
            "sequence": sequence,
            "logical_clock": sequence,
            "kind": "environment_healthcheck",
            "actor_id": "__dtbench_runtime__",
            "actor_kind": "infrastructure_control_plane",
            "environment_type": self._identity["environment_type"],
            "task_action": False,
            "payload": {
                "operation": "healthcheck_ack",
                "provider": provider_response.get("provider"),
                "provider_response_sha256": _json_digest(provider_response),
            },
            "provenance": {
                "source_task_id": self._identity["source_task_id"],
                "execution_scope": MARBLE_SMOKE_SCOPE,
            },
        }
        self._state["sequence"] = sequence
        self._state["transcript"] = [transcript_event]
        self._state["phase"] = "healthchecked"
        self._append_audit("healthcheck_transcript_appended")
        return transcript_event, self._state_digest()

    def audit_chain_valid(self) -> bool:
        previous = "0" * 64
        for record in self.audit:
            if record.get("previous_sha256") != previous:
                return False
            body = {key: value for key, value in record.items() if key != "record_sha256"}
            if record.get("record_sha256") != _json_digest(body):
                return False
            previous = str(record["record_sha256"])
        return bool(self.audit)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_digest(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return _sha256_bytes(payload)


def _write_text_lf(path: Path, payload: str) -> None:
    """Write stable LF text on every supported MARBLE Python (3.9--3.11)."""

    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)


def _portable_evaluator_source(source: str) -> str:
    source = _repair_evaluator_syntax(source)
    source = _replace_exact(
        source,
        "import re\nfrom typing import Any, Dict, List",
        "import re\nfrom pathlib import Path\nfrom typing import Any, Dict, List",
        "evaluator_path_import",
    )
    source = _replace_exact(
        source,
        "        with open('evaluator/evaluator_prompts.json', 'r', encoding='utf-8') as f:\n",
        (
            '        prompts_path = Path(__file__).with_name("evaluator_prompts.json")\n'
            "        with prompts_path.open('r', encoding='utf-8') as f:\n"
        ),
        "evaluator_prompt_path",
    )
    source = _replace_exact(
        source,
        '''            config_path = "marble/configs/coding_config/coding_config.yaml"
            if not os.path.exists(config_path):
                self.logger.error("Config file not found")
                return

            yaml = YAML()
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.load(f)

            full_task_description = config['task']['content']
''',
        '''            # The source-native case already supplies both values.  Avoid a
            # repository-relative singleton coding config from another task.
            full_task_description = task
''',
        "evaluator_case_scoped_coding_task",
    )
    source = _replace_exact(
        source,
        '''            solution_path = "marble/workspace/solution.py"
            solution_content = ""
            if os.path.exists(solution_path):
                with open(solution_path, 'r', encoding='utf-8') as f:
                    solution_content = f.read()
''',
        "            solution_content = code_result\n",
        "evaluator_case_scoped_coding_solution",
    )
    return source


def _portable_engine_source(source: str) -> str:
    source = _replace_exact(
        source,
        "import json\nfrom typing import Any, Dict, List, Optional, Union",
        "import json\nimport os\nfrom typing import Any, Dict, List, Optional, Union",
        "engine_os_import",
    )
    source = _replace_exact(
        source,
        '''        except IOError as e:
            self.logger.error(f"Failed to read code from {file_path}: {e}")
            return ""

    def __init__(self, config: Config):
''',
        '''        except IOError as e:
            self.logger.error(f"Failed to read code from {file_path}: {e}")
            return ""

    def _coding_solution_path(self) -> str:
        """Resolve coding output from the case-scoped configured workspace."""
        workspace_dir = self.config.environment.get("workspace_dir", "workspace")
        return os.path.join(workspace_dir, "solution.py")

    def __init__(self, config: Config):
''',
        "engine_case_scoped_coding_path_method",
    )
    source = _replace_exact(
        source,
        'self._read_code_from_file("MARBLE/marble/workspace/solution.py")',
        "self._read_code_from_file(self._coding_solution_path())",
        "engine_case_scoped_coding_path_calls",
        expected_count=2,
    )
    source = _replace_exact(
        source,
        '''        try:
            with open(file_path, "a") as jsonl_file:
''',
        '''        try:
            output_parent = os.path.dirname(os.path.abspath(file_path))
            os.makedirs(output_parent, exist_ok=True)
            with open(file_path, "a") as jsonl_file:
''',
        "engine_output_parent_creation",
    )
    return source


def _portable_database_source(source: str) -> str:
    source = _replace_exact(
        source,
        "import subprocess\nimport time",
        "import subprocess\nimport sys\nimport time",
        "database_sys_import",
    )
    source = _replace_exact(
        source,
        '                        "python",\n                        "main.py",',
        '                        sys.executable,\n                        "main.py",',
        "database_selected_python_for_anomaly",
    )
    source = _replace_exact(
        source,
        '''        connection.autocommit = True
        cursor.execute("SET client_min_messages TO WARNING;")
''',
        '''        connection.autocommit = True
        initialization_probe = (
            os.environ.get("DTBENCH_MARBLE_INITIALIZATION_PROBE") == "1"
        )
        if initialization_probe:
            # Reuse the fixed Compose stack while isolating each init-only case.
            cursor.execute("DROP SCHEMA IF EXISTS public CASCADE;")
            cursor.execute("CREATE SCHEMA public;")
        cursor.execute("SET client_min_messages TO WARNING;")
''',
        "database_case_scoped_initialization_schema",
    )
    source = _replace_exact(
        source,
        "        if anomalies:\n            for anomaly in anomalies:\n",
        (
            "        if anomalies and not initialization_probe:\n"
            "            for anomaly in anomalies:\n"
        ),
        "database_initialization_probe_defers_workload",
    )
    source = _replace_exact(
        source,
        '''                    check=True,
                )
        else:
            print(
''',
        '''                    check=True,
                )
        elif anomalies and initialization_probe:
            print(
                "Initialization probe validated anomaly configuration; "
                "workload execution is deferred to the model episode."
            )
        else:
            print(
''',
        "database_initialization_probe_workload_boundary",
    )
    source = _replace_exact(
        source,
        '''    def start_docker_containers(self):
        print("Starting Docker containers...")
        subprocess.run(
            ["sudo", "docker", "compose", "down", "-v"],
            cwd=os.path.join(self.current_dir, "db_env_docker"),
            shell=False,
            check=True,
        )
        subprocess.run(
            ["sudo", "docker", "compose", "up", "-d", "--remove-orphans"],
            cwd=os.path.join(self.current_dir, "db_env_docker"),
            check=True,
        )
''',
        '''    def start_docker_containers(self):
        # Container lifecycle is owned by run_marble_native.py --provision.
        # Keeping it outside Engine initialization makes preflight non-destructive.
        print("Using explicitly provisioned MARBLE database services.")
''',
        "database_explicit_provisioning_boundary",
    )
    return _replace_exact(
        source,
        '''    def terminate(self) -> None:
        subprocess.run(
            ["sudo", "docker", "compose", "down"],
            cwd=os.path.join(self.current_dir, "db_env_docker"),
            check=True,
        )
''',
        '''    def terminate(self) -> None:
        # The fixed Compose project is intentionally not mutated by Engine teardown.
        # Operators may explicitly reprovision it through the native launcher.
        return None
''',
        "database_explicit_teardown_boundary",
    )


def _portable_database_compose_source(source: str) -> str:
    replacements = {
        "    image: prom/prometheus:master\n": (
            f"    image: {DATABASE_IMAGE_REFERENCES['prometheus']}\n"
        ),
        "    image: postgres\n": (
            f"    image: {DATABASE_IMAGE_REFERENCES['postgres_db']}\n"
        ),
        "    image: prom/node-exporter\n": (
            f"    image: {DATABASE_IMAGE_REFERENCES['node_exporter']}\n"
        ),
        "    image: wrouesnel/postgres_exporter\n": (
            f"    image: {DATABASE_IMAGE_REFERENCES['pg_exporter']}\n"
        ),
    }
    for original, pinned in replacements.items():
        source = _replace_exact(
            source,
            original,
            pinned,
            "database_compose_image_digest_pin",
        )
    return source


def _portable_base_environment_source(source: str) -> str:
    source = _replace_exact(
        source,
        'from typing import Any, Callable, Dict, List, Union',
        'from copy import deepcopy\nfrom typing import Any, Callable, Dict, List, Union',
        "base_environment_deepcopy_import",
    )
    source = _replace_exact(
        source,
        '''        # Initialize the state with the task description
        self.state["task_description"] = self.task_description

    def is_done(self) -> bool:
''',
        '''        # Initialize the state with the task description
        self.state["task_description"] = self.task_description
        self._initial_state = deepcopy(self.state)

    def reset(self) -> Dict[str, Any]:
        """Restore deterministic environment control-plane state."""
        self.state = deepcopy(self._initial_state)
        self.done = False
        self.current_iteration = 0
        return self.get_state()

    def is_done(self) -> bool:
''',
        "base_environment_reset_adapter",
    )
    return source


def _unsupported_minecraft_source(source: str) -> str:
    _require(
        "class MinecraftEnvironment(BaseEnvironment):" in source
        and "MinecraftClient" in source,
        "marble_staging_patch_drift:minecraft_exclusion",
    )
    return '''"""Portable placeholder for the excluded MultiAgentBench Minecraft split."""

from typing import Any, Dict

from marble.environments.base_env import BaseEnvironment


class MinecraftEnvironment(BaseEnvironment):
    def __init__(self, name: str, config: Dict[str, Any]):
        raise RuntimeError(
            "Minecraft is not part of the 341 source-native MARBLE collection"
        )
'''


def stage_marble_runtime(upstream_root: Path, destination: Path) -> Path:
    """Create a temporary, auditable portability overlay without mutating upstream."""

    upstream_root = upstream_root.resolve()
    destination = destination.resolve()
    source_package = upstream_root / "marble"
    _require(source_package.is_dir(), "marble_upstream_package_missing")
    _require(not destination.exists(), "marble_staging_destination_exists")

    def ignore(directory: str, names: list[str]) -> set[str]:
        ignored = {name for name in names if name in {"__pycache__", "dbdata"}}
        ignored.update(name for name in names if name.endswith((".pyc", ".pyo")))
        return ignored

    staged_package = destination / "marble"
    shutil.copytree(source_package, staged_package, ignore=ignore)
    patches: list[dict[str, str]] = []
    patchers = {
        "marble/environments/base_env.py": _portable_base_environment_source,
        "marble/evaluator/evaluator.py": _portable_evaluator_source,
        "marble/engine/engine.py": _portable_engine_source,
        "marble/environments/db_env.py": _portable_database_source,
        "marble/environments/minecraft_env.py": _unsupported_minecraft_source,
    }
    for relative, patcher in patchers.items():
        path = destination / relative
        before = path.read_text(encoding="utf-8")
        source_sha256 = _sha256_bytes(before.encode("utf-8"))
        _require(
            source_sha256 == PINNED_STAGING_SOURCE_SHA256[relative],
            f"marble_staging_source_hash_mismatch:{relative}",
        )
        after = patcher(before)
        staged_sha256 = _sha256_bytes(after.encode("utf-8"))
        _require(
            staged_sha256 == PINNED_STAGING_OUTPUT_SHA256[relative],
            f"marble_staging_output_hash_mismatch:{relative}",
        )
        _write_text_lf(path, after)
        patches.append(
            {
                "path": relative,
                "source_sha256": source_sha256,
                "staged_sha256": staged_sha256,
            }
        )

    anomaly_path = (
        staged_package
        / "environments/db_env_docker/anomaly_trigger/anomaly.py"
    )
    anomaly_before = anomaly_path.read_text(encoding="utf-8")
    anomaly_relative = str(anomaly_path.relative_to(destination)).replace("\\", "/")
    anomaly_source_sha256 = _sha256_bytes(anomaly_before.encode("utf-8"))
    _require(
        anomaly_source_sha256 == PINNED_STAGING_SOURCE_SHA256[anomaly_relative],
        f"marble_staging_source_hash_mismatch:{anomaly_relative}",
    )
    anomaly_after = _replace_exact(
        anomaly_before,
        'os.system("sudo docker compose restart postgres_db")',
        'os.system("docker compose restart postgres_db")',
        "database_anomaly_portable_restart",
    )
    anomaly_staged_sha256 = _sha256_bytes(anomaly_after.encode("utf-8"))
    _require(
        anomaly_staged_sha256 == PINNED_STAGING_OUTPUT_SHA256[anomaly_relative],
        f"marble_staging_output_hash_mismatch:{anomaly_relative}",
    )
    _write_text_lf(anomaly_path, anomaly_after)
    patches.append(
        {
            "path": anomaly_relative,
            "source_sha256": anomaly_source_sha256,
            "staged_sha256": anomaly_staged_sha256,
        }
    )

    compose_path = destination / DATABASE_COMPOSE_ASSET_PATH
    compose_before = compose_path.read_text(encoding="utf-8")
    compose_source_sha256 = _sha256_bytes(compose_before.encode("utf-8"))
    _require(
        compose_source_sha256 == DATABASE_COMPOSE_SOURCE_SHA256,
        "marble_staging_source_hash_mismatch:database_compose_asset",
    )
    compose_after = _portable_database_compose_source(compose_before)
    compose_staged_sha256 = _sha256_bytes(compose_after.encode("utf-8"))
    _require(
        compose_staged_sha256 == DATABASE_COMPOSE_STAGED_SHA256,
        "marble_staging_output_hash_mismatch:database_compose_asset",
    )
    _write_text_lf(compose_path, compose_after)
    runtime_assets = [
        {
            "path": DATABASE_COMPOSE_ASSET_PATH,
            "kind": "docker_compose_image_digest_pins",
            "source_sha256": compose_source_sha256,
            "staged_sha256": compose_staged_sha256,
            "images": dict(DATABASE_IMAGE_REFERENCES),
        }
    ]

    # Upstream constructs a RotatingFileHandler even though it only attaches the
    # stream handler, so Engine initialization requires this runtime directory.
    (destination / "logs").mkdir(parents=True, exist_ok=False)

    manifest = {
        "schema_version": "marble-temporary-runtime-staging-v1",
        "adapter": MARBLE_STAGING_ADAPTER,
        "source_root": str(upstream_root),
        "upstream_mutated": False,
        "runtime_directories": ["logs"],
        "runtime_assets": runtime_assets,
        "patches": patches,
    }
    _write_text_lf(
        destination / "STAGING_MANIFEST.json",
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return destination


def _validated_staging_manifest(upstream_root: Path) -> dict[str, Any] | None:
    """Load a staging manifest only when every pinned file matches the overlay."""

    manifest_path = upstream_root / "STAGING_MANIFEST.json"
    if not manifest_path.is_file():
        return None
    try:
        manifest = _load_json(manifest_path)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(manifest, dict):
        return None
    if (
        manifest.get("adapter") != MARBLE_STAGING_ADAPTER
        or manifest.get("upstream_mutated") is not False
        or manifest.get("runtime_directories") != ["logs"]
        or not (upstream_root / "logs").is_dir()
    ):
        return None
    runtime_assets = manifest.get("runtime_assets")
    expected_asset = {
        "path": DATABASE_COMPOSE_ASSET_PATH,
        "kind": "docker_compose_image_digest_pins",
        "source_sha256": DATABASE_COMPOSE_SOURCE_SHA256,
        "staged_sha256": DATABASE_COMPOSE_STAGED_SHA256,
        "images": DATABASE_IMAGE_REFERENCES,
    }
    if runtime_assets != [expected_asset]:
        return None
    compose_path = upstream_root / DATABASE_COMPOSE_ASSET_PATH
    if (
        not compose_path.is_file()
        or _sha256_bytes(compose_path.read_bytes())
        != DATABASE_COMPOSE_STAGED_SHA256
    ):
        return None
    patches = manifest.get("patches")
    if not isinstance(patches, list) or len(patches) != len(
        PINNED_STAGING_SOURCE_SHA256
    ):
        return None
    by_path = {
        str(item.get("path")): item for item in patches if isinstance(item, dict)
    }
    if len(by_path) != len(patches) or set(by_path) != set(
        PINNED_STAGING_SOURCE_SHA256
    ):
        return None
    sha_pattern = re.compile(r"[0-9a-f]{64}")
    for relative, pinned_source_sha256 in PINNED_STAGING_SOURCE_SHA256.items():
        patch = by_path[relative]
        staged_sha256 = patch.get("staged_sha256")
        staged_path = upstream_root / relative
        if (
            patch.get("source_sha256") != pinned_source_sha256
            or not isinstance(staged_sha256, str)
            or not sha_pattern.fullmatch(staged_sha256)
            or staged_sha256 != PINNED_STAGING_OUTPUT_SHA256[relative]
            or not staged_path.is_file()
            or _sha256_bytes(staged_path.read_bytes()) != staged_sha256
        ):
            return None
    return manifest


def official_record_digest(value: Any) -> str:
    """Match the legacy source-native official-record digest (sha256 over sort_keys JSON)."""

    return _sha256_bytes(json.dumps(value, sort_keys=True).encode("utf-8"))


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _entrypoint_parts(entrypoint: str) -> tuple[str, str]:
    module, separator, name = entrypoint.rpartition(".")
    if not separator or not module or not name:
        raise MarbleQualificationError(f"invalid_entrypoint:{entrypoint}")
    return module, name


def _module_path(upstream_root: Path, entrypoint: str) -> tuple[Path, str]:
    module, name = _entrypoint_parts(entrypoint)
    return upstream_root / (module.replace(".", "/") + ".py"), name


def _parse_python(path: Path) -> ast.Module:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise MarbleQualificationError(
            f"python_binding_unreadable:{path.as_posix()}:{type(exc).__name__}"
        ) from exc
    try:
        return ast.parse(source, filename=str(path))
    except SyntaxError as original_exc:
        # The pinned MARBLE evaluator has one known indentation defect.  Static
        # binding qualification parses the same exact temporary repair used by
        # the real launcher, while preserving the pinned source unchanged.
        if path.name == "evaluator.py" and _BROKEN_RESEARCH_RATINGS_BLOCK in source:
            try:
                return ast.parse(_repair_evaluator_syntax(source), filename=str(path))
            except SyntaxError:
                pass
        raise MarbleQualificationError(
            f"python_binding_unreadable:{path.as_posix()}:SyntaxError"
        ) from original_exc


def _class_node(tree: ast.Module, name: str) -> ast.ClassDef | None:
    return next(
        (node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == name),
        None,
    )


def _method_names(node: ast.ClassDef) -> set[str]:
    return {
        child.name
        for child in node.body
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _configured_path_equals(raw_path: Any, expected: Path) -> bool:
    raw = str(raw_path or "").strip()
    if not raw:
        return False
    try:
        actual = Path(raw).resolve()
    except (OSError, RuntimeError, ValueError):
        return False
    return os.path.normcase(str(actual)) == os.path.normcase(str(expected.resolve()))


def _require(condition: bool, error: str) -> None:
    if not condition:
        raise MarbleQualificationError(error)


class MarbleUpstreamBindings:
    """Resolve and cache MARBLE's checked-in Python entrypoints."""

    def __init__(self, upstream_root: Path):
        self.root = upstream_root.resolve()
        self._trees: dict[Path, ast.Module] = {}
        self._verify_common_bindings()

    def _tree(self, relative: str | Path) -> ast.Module:
        path = (self.root / relative).resolve()
        _require(path.is_relative_to(self.root), "upstream_binding_path_escape")
        _require(path.is_file(), f"upstream_binding_missing:{relative}")
        if path not in self._trees:
            self._trees[path] = _parse_python(path)
        return self._trees[path]

    def _class(self, entrypoint: str) -> ast.ClassDef:
        path, name = _module_path(self.root, entrypoint)
        tree = self._tree(path.relative_to(self.root))
        node = _class_node(tree, name)
        _require(node is not None, f"upstream_class_missing:{entrypoint}")
        assert node is not None
        return node

    def _verify_common_bindings(self) -> None:
        config = self._class(CONFIG_ENTRYPOINT)
        _require("load" in _method_names(config), "marble_config_load_missing")

        engine = self._class(ENGINE_ENTRYPOINT)
        methods = _method_names(engine)
        _require("_initialize_environment" in methods, "marble_engine_environment_factory_missing")
        _require("start" in methods, "marble_engine_start_missing")

        engine_source = (self.root / "marble/engine/engine.py").read_text(
            encoding="utf-8"
        )
        _require(
            "Evaluator(metrics_config=config.metrics)" in engine_source,
            "marble_engine_evaluator_binding_missing",
        )
        _require(
            "from marble.configs.config import Config" in engine_source,
            "marble_engine_config_binding_missing",
        )

        evaluator = self._class(EVALUATOR_ENTRYPOINT)
        evaluator_methods = _method_names(evaluator)
        for method in {
            "evaluate_communication",
            "evaluate_planning",
            "evaluate_kpi",
            "finalize",
        }:
            _require(
                method in evaluator_methods,
                f"marble_evaluator_method_missing:{method}",
            )

        prompts_path = self.root / "marble/evaluator/evaluator_prompts.json"
        _require(prompts_path.is_file(), "marble_evaluator_prompts_missing")
        prompts = _load_json(prompts_path)
        _require(isinstance(prompts, dict) and "Graph" in prompts, "marble_graph_prompts_missing")

    def verify_scenario(self, scenario: str) -> dict[str, str]:
        _require(scenario in SCENARIO_BINDINGS, f"unsupported_marble_scenario:{scenario}")
        binding = SCENARIO_BINDINGS[scenario]

        environment = self._class(binding.environment_entrypoint)
        environment_methods = _method_names(environment)
        _require("__init__" in environment_methods, f"marble_environment_init_missing:{scenario}")

        engine_source = (self.root / "marble/engine/engine.py").read_text(
            encoding="utf-8"
        )
        _, environment_class = _entrypoint_parts(binding.environment_entrypoint)
        _require(
            f'env_type == "{binding.environment_type}"' in engine_source,
            f"marble_engine_env_type_missing:{scenario}",
        )
        _require(
            f"{environment_class}(" in engine_source,
            f"marble_engine_environment_class_missing:{scenario}",
        )

        evaluator = self._class(EVALUATOR_ENTRYPOINT)
        _require(
            binding.evaluator_method in _method_names(evaluator),
            f"marble_scenario_evaluator_missing:{scenario}",
        )
        if binding.prompt_section:
            prompts = _load_json(self.root / "marble/evaluator/evaluator_prompts.json")
            # Upstream currently calls the database prompt section "database".
            prompt_names = {binding.prompt_section}
            if binding.prompt_section == "db":
                prompt_names.add("database")
            _require(
                bool(prompt_names.intersection(prompts)),
                f"marble_scenario_prompt_missing:{scenario}",
            )

        return {
            "config": CONFIG_ENTRYPOINT,
            "engine": ENGINE_ENTRYPOINT,
            "environment": binding.environment_entrypoint,
            "evaluator": EVALUATOR_ENTRYPOINT,
            "evaluator_method": binding.evaluator_method,
        }


def _source_record(
    repository_root: Path,
    spec: Mapping[str, Any],
) -> tuple[dict[str, Any], Path]:
    binding = spec.get("source_binding") or {}
    relative_path = str(binding.get("jsonl_path") or "")
    _require(relative_path != "", "marble_source_jsonl_path_empty")
    source_path = (repository_root / relative_path).resolve()
    _require(source_path.is_relative_to(repository_root), "marble_source_path_escape")
    _require(source_path.is_file(), "marble_source_jsonl_missing")
    line_number = binding.get("line_number")
    _require(isinstance(line_number, int) and line_number > 0, "marble_source_line_invalid")
    lines = source_path.read_text(encoding="utf-8").splitlines()
    _require(line_number <= len(lines), "marble_source_line_out_of_range")
    try:
        record = json.loads(lines[line_number - 1])
    except json.JSONDecodeError as exc:
        raise MarbleQualificationError("marble_source_line_invalid_json") from exc
    _require(isinstance(record, dict), "marble_source_record_not_object")
    _require(
        official_record_digest(record) == binding.get("record_sha256"),
        "marble_source_record_hash_mismatch",
    )
    return record, source_path


def _validate_config(
    case_dir: Path,
    config: Mapping[str, Any],
    official: Mapping[str, Any],
    scenario: str,
) -> None:
    _require(isinstance(config, dict), "marble_config_not_object")
    binding = SCENARIO_BINDINGS[scenario]
    _require(config.get("scenario") == scenario, "marble_config_scenario_mismatch")
    _require(config.get("task_id") == official.get("task_id"), "marble_config_task_id_mismatch")
    _require(
        config.get("coordinate_mode") in SUPPORTED_COORDINATION_MODES,
        "marble_config_coordination_mode_unsupported",
    )
    _require(
        config.get("coordinate_mode") == (official.get("coordinate_mode") or "graph"),
        "marble_config_coordination_mode_changed",
    )
    _require(config.get("agents") == official.get("agents"), "marble_config_agents_changed")
    _require(
        config.get("relationships") == official.get("relationships"),
        "marble_config_relationships_changed",
    )
    _require(config.get("task") == official.get("task"), "marble_config_task_changed")
    _require(config.get("metrics") == official.get("metrics") or (
        isinstance(config.get("metrics"), dict)
        and {
            key: value
            for key, value in config["metrics"].items()
            if key != "evaluate_llm"
        }
        == {
            key: value
            for key, value in (official.get("metrics") or {}).items()
            if key != "evaluate_llm"
        }
    ), "marble_config_metrics_changed")

    model = config.get("llm")
    _require(isinstance(model, (str, dict)) and bool(model), "marble_config_model_empty")
    environment = config.get("environment") or {}
    _require(isinstance(environment, dict), "marble_config_environment_not_object")
    _require(
        environment.get("type") == binding.environment_type,
        "marble_config_environment_type_mismatch",
    )
    _require(
        isinstance(environment.get("max_iterations"), int)
        and environment["max_iterations"] > 0,
        "marble_config_iterations_invalid",
    )

    agents = config.get("agents") or []
    _require(isinstance(agents, list) and len(agents) >= 2, "marble_config_agents_invalid")
    agent_ids = [agent.get("agent_id") for agent in agents if isinstance(agent, dict)]
    _require(
        len(agent_ids) == len(agents)
        and all(isinstance(agent_id, str) and agent_id for agent_id in agent_ids)
        and len(agent_ids) == len(set(agent_ids)),
        "marble_config_agent_ids_invalid",
    )
    valid_ids = set(agent_ids)
    for relationship in config.get("relationships") or []:
        _require(
            isinstance(relationship, list)
            and len(relationship) >= 3
            and relationship[0] in valid_ids
            and relationship[1] in valid_ids,
            "marble_config_relationship_invalid",
        )

    task = config.get("task") or {}
    _require(
        isinstance(task, dict) and bool(str(task.get("content") or "").strip()),
        "marble_config_task_content_empty",
    )
    metrics = config.get("metrics") or {}
    _require(isinstance(metrics, dict) and bool(metrics), "marble_config_metrics_empty")
    _require(bool(metrics.get("evaluate_llm")), "marble_config_evaluator_model_empty")

    output = config.get("output") or {}
    output_path = output.get("file_path") if isinstance(output, dict) else None
    _require(
        _configured_path_equals(output_path, case_dir / "result/native_output.jsonl"),
        "marble_config_output_path_not_case_scoped",
    )
    if scenario == "coding":
        workspace = environment.get("workspace_dir")
        _require(
            _configured_path_equals(workspace, case_dir / "workspace"),
            "marble_config_workspace_not_case_scoped",
        )


def qualify_marble_case(
    case_dir: Path,
    manifest_row: Mapping[str, Any],
    *,
    repository_root: Path,
    upstream_root: Path,
    bindings: MarbleUpstreamBindings | None = None,
) -> dict[str, Any]:
    """Return one infrastructure-only evidence row or raise on a bad binding."""

    case_dir = case_dir.resolve()
    repository_root = repository_root.resolve()
    upstream_root = upstream_root.resolve()
    _require(case_dir.is_dir(), "marble_case_directory_missing")
    for name in ("native_case.json", "official_task.json", "native_config.yaml"):
        _require((case_dir / name).is_file(), f"marble_case_asset_missing:{name}")

    spec = _load_json(case_dir / "native_case.json")
    official = _load_json(case_dir / "official_task.json")
    config = _load_yaml(case_dir / "native_config.yaml")
    _require(isinstance(spec, dict), "marble_native_case_not_object")
    _require(isinstance(official, dict), "marble_official_task_not_object")
    _require(spec.get("benchmark") == MARBLE_BENCHMARK, "marble_benchmark_mismatch")
    _require(manifest_row.get("benchmark") == MARBLE_BENCHMARK, "manifest_benchmark_mismatch")
    _require(spec.get("case_id") == manifest_row.get("case_id"), "manifest_case_id_mismatch")

    source, source_path = _source_record(repository_root, spec)
    _require(source == official, "marble_official_task_source_mismatch")
    source_binding = spec.get("source_binding") or {}
    scenario = str(source.get("scenario") or "")
    _require(scenario in SCENARIO_BINDINGS, f"unsupported_marble_scenario:{scenario}")
    source_task_id = f"{scenario}:{int(source['task_id']):03d}"
    _require(
        str(manifest_row.get("source_task_id")) == source_task_id,
        "manifest_source_task_id_mismatch",
    )
    _require(source_binding.get("task_id") == source_task_id, "spec_source_task_id_mismatch")
    _require(source_binding.get("scenario") == scenario, "spec_source_scenario_mismatch")

    native_runtime = spec.get("native_runtime") or {}
    _require(native_runtime.get("adapter") == "marble.engine.Engine", "marble_engine_adapter_mismatch")
    _require(native_runtime.get("roles") == official.get("agents"), "marble_native_roles_mismatch")
    _require(
        (spec.get("native_evaluator") or {}).get("metrics") == official.get("metrics"),
        "marble_native_evaluator_metrics_mismatch",
    )
    _require(
        (spec.get("native_evaluator") or {}).get("agreement_or_environment_state") is True,
        "marble_native_evaluator_state_binding_missing",
    )
    _validate_config(case_dir, config, official, scenario)

    binding_inspector = bindings or MarbleUpstreamBindings(upstream_root)
    resolved = binding_inspector.verify_scenario(scenario)

    config_sha256 = _sha256_file(case_dir / "native_config.yaml")
    provider = OfflineDeterministicProvider()
    nonce = _json_digest(
        {
            "case_id": manifest_row["case_id"],
            "source_task_id": source_task_id,
            "config_sha256": config_sha256,
        }
    )
    provider_request = {"operation": "healthcheck", "nonce": nonce}
    provider_response = provider.healthcheck(provider_request)
    _require(provider_response.get("nonce") == nonce, "offline_provider_nonce_mismatch")
    _require(provider_response.get("network_calls") == 0, "offline_provider_used_network")
    _require(provider_response.get("task_completion") is False, "offline_provider_claimed_task_completion")

    control_plane = LocalMarbleEnvironment(
        case_id=str(manifest_row["case_id"]),
        source_task_id=source_task_id,
        scenario=scenario,
        environment_type=SCENARIO_BINDINGS[scenario].environment_type,
        config_sha256=config_sha256,
    )
    started_digest = control_plane.start()
    baseline_digest = control_plane.reset()
    transcript_event, checkpoint_digest = control_plane.append_healthcheck(
        provider_response
    )
    _require(
        checkpoint_digest != baseline_digest,
        "control_plane_healthcheck_did_not_change_state",
    )
    reset_digest = control_plane.reset()
    _require(
        reset_digest == baseline_digest,
        "control_plane_reset_not_reproducible",
    )
    _require(control_plane.audit_chain_valid(), "control_plane_audit_chain_invalid")

    evidence: dict[str, Any] = {
        "schema_version": MARBLE_SMOKE_SCHEMA,
        "case_id": str(manifest_row["case_id"]),
        "benchmark": MARBLE_BENCHMARK,
        "source_task_id": source_task_id,
        "scenario": scenario,
        "status": MARBLE_SMOKE_STATUS,
        "execution_scope": MARBLE_SMOKE_SCOPE,
        "qualification_profile": "marble_environment_smoke_v1",
        "adapter": LocalMarbleEnvironment.adapter_id,
        "upstream_engine_executed": False,
        "checks": {
            "official_source_record_bound": True,
            "source_record_hash_verified": True,
            "hydrated_config_loaded": True,
            "config_entrypoint_resolved": True,
            "engine_entrypoint_resolved": True,
            "environment_entrypoint_resolved": True,
            "evaluator_entrypoint_resolved": True,
            "scenario_evaluator_bound": True,
            "offline_provider_healthcheck": True,
            "zero_external_model_calls": True,
            "local_control_plane_started": True,
            "environment_reset_reproducible": True,
            "native_healthcheck_transcript_appended": True,
            "native_state_digest_changed": True,
            "control_plane_audit_chain_valid": True,
        },
        "bindings": resolved,
        "environment": {
            "scenario": scenario,
            "type": SCENARIO_BINDINGS[scenario].environment_type,
            "external_service": SCENARIO_BINDINGS[scenario].external_service,
        },
        "source_evidence": {
            "jsonl_path": str(source_path.relative_to(repository_root)).replace("\\", "/"),
            "line_number": source_binding["line_number"],
            "record_sha256": source_binding["record_sha256"],
            "official_task_sha256": _sha256_file(case_dir / "official_task.json"),
            "native_config_sha256": config_sha256,
            "native_case_sha256": _sha256_file(case_dir / "native_case.json"),
        },
        "provider_probe": {
            "provider": provider.provider_id,
            "request_sha256": _json_digest(provider_request),
            "response_sha256": _json_digest(provider_response),
            "network_calls": 0,
        },
        "control_plane": {
            "adapter": LocalMarbleEnvironment.adapter_id,
            "upstream_engine_executed": False,
            "started_state_sha256": started_digest,
            "baseline_state_sha256": baseline_digest,
            "checkpoint_state_sha256": checkpoint_digest,
            "reset_state_sha256": reset_digest,
            "transcript_event": transcript_event,
            "audit": control_plane.audit,
        },
        "claims": {
            "model_episode_executed": False,
            "gold_evaluator_executed": False,
            "task_scored": False,
            "formal_promotion_ready": False,
        },
        "real_episode_launcher": {
            "command": [
                "python",
                "scripts/run_marble_native.py",
                "--case-id",
                str(manifest_row["case_id"]),
                "--model",
                "<provider/model>",
                "--evaluator-model",
                "<provider/model>",
            ],
            "preflight": "fail_closed",
        },
    }
    evidence["evidence_sha256"] = _json_digest(evidence)
    return evidence


def write_jsonl(path: Path, entries: Iterable[Mapping[str, Any]]) -> None:
    rows = sorted(entries, key=lambda item: str(item.get("case_id") or ""))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows
    )
    temporary = path.with_suffix(path.suffix + ".tmp")
    _write_text_lf(temporary, payload)
    temporary.replace(path)


def merge_smoke_evidence(
    registry_entries: Iterable[Mapping[str, Any]],
    smoke_entries: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Merge MARBLE smoke through the shared, rank-aware registry contract."""

    # Delayed import avoids a module cycle: the common registry lazily calls this
    # module's native-initialization validator for the MARBLE profile.
    from async_rbench.native_runtime_registry import merge_registry_entries

    merged = {str(row["case_id"]): dict(row) for row in registry_entries}
    for smoke in smoke_entries:
        case_id = str(smoke["case_id"])
        existing = merged.get(case_id)
        merged[case_id] = (
            merge_registry_entries(existing, dict(smoke))
            if existing is not None
            else dict(smoke)
        )
    return sorted(merged.values(), key=lambda row: str(row["case_id"]))


def validate_native_environment_evidence(
    entry: Mapping[str, Any],
) -> tuple[bool, str | None]:
    """Strict profile validator for runnable MARBLE initialization evidence."""

    fixed = {
        "schema_version": "source-native-marble-native-environment-v1",
        "benchmark": MARBLE_BENCHMARK,
        "status": MARBLE_NATIVE_INITIALIZATION_STATUS,
        "execution_scope": MARBLE_NATIVE_INITIALIZATION_SCOPE,
        "qualification_profile": MARBLE_NATIVE_INITIALIZATION_PROFILE,
        "runtime_adapter": MARBLE_STAGING_ADAPTER,
    }
    if any(entry.get(key) != value for key, value in fixed.items()):
        return False, "marble_native_environment_profile_mismatch"
    if any(
        key in entry and not isinstance(entry.get(key), Mapping)
        for key in MARBLE_REGISTRY_MERGE_ENVELOPES
    ):
        return False, "marble_native_environment_registry_envelope_invalid"
    scenario = str(entry.get("scenario") or "")
    if scenario not in SCENARIO_BINDINGS:
        return False, "marble_native_environment_scenario_invalid"
    case_id = entry.get("case_id")
    source_task_id = entry.get("source_task_id")
    if not isinstance(case_id, str) or not case_id:
        return False, "marble_native_environment_case_id_invalid"
    if not isinstance(source_task_id, str) or not re.fullmatch(
        re.escape(scenario) + r":\d{3}", source_task_id
    ):
        return False, "marble_native_environment_source_task_id_invalid"
    required_checks = {
        "actual_config_loaded",
        "actual_engine_initialized",
        "actual_environment_initialized",
        "actual_evaluator_initialized",
        "environment_healthcheck_changed_state",
        "in_memory_control_plane_reset_reproducible",
        "upstream_engine_start_not_called",
        "zero_model_calls",
    }
    checks = entry.get("checks") or {}
    if set(checks) != required_checks or not all(checks.get(key) is True for key in required_checks):
        return False, "marble_native_environment_checks_incomplete"
    call_audit = entry.get("call_audit") or {}
    patched_entrypoints = call_audit.get("patched_model_entrypoints")
    required_call_guards = {
        "litellm.completion",
        "litellm.acompletion",
        "openai.resources.chat.completions.Completions.create",
        "openai.resources.chat.completions.AsyncCompletions.create",
        "marble.llms.model_prompting.model_prompting",
    }
    if (
        call_audit.get("engine_start_calls") != 0
        or call_audit.get("model_entrypoint_calls") != 0
        or not isinstance(patched_entrypoints, list)
        or not required_call_guards.issubset(set(patched_entrypoints))
    ):
        return False, "marble_native_environment_call_audit_invalid"
    claims = entry.get("claims") or {}
    expected_claims = {
        "model_episode_executed": False,
        "gold_evaluator_executed": False,
        "task_scored": False,
        "native_checkpoint_validated": False,
    }
    if claims != expected_claims:
        return False, "marble_native_environment_claims_invalid"
    source_evidence = entry.get("source_evidence") or {}
    required_source_fields = {
        "jsonl_path",
        "line_number",
        "native_case_sha256",
        "native_config_sha256",
        "official_task_sha256",
        "record_sha256",
    }
    if not isinstance(source_evidence, dict) or set(source_evidence) != required_source_fields:
        return False, "marble_native_environment_source_evidence_invalid"
    jsonl_path = source_evidence.get("jsonl_path")
    if (
        not isinstance(jsonl_path, str)
        or not jsonl_path.startswith("upstream/marble/multiagentbench/")
        or Path(jsonl_path).is_absolute()
        or ".." in Path(jsonl_path).parts
        or not isinstance(source_evidence.get("line_number"), int)
        or source_evidence["line_number"] < 1
    ):
        return False, "marble_native_environment_source_evidence_invalid"
    sha_pattern = re.compile(r"[0-9a-f]{64}")
    if not all(
        isinstance(source_evidence.get(name), str)
        and sha_pattern.fullmatch(str(source_evidence[name]))
        for name in required_source_fields - {"jsonl_path", "line_number"}
    ):
        return False, "marble_native_environment_source_evidence_invalid"
    current_runtime_binding, runtime_binding_error = native_runtime_binding()
    if current_runtime_binding is None:
        return False, runtime_binding_error or "marble_native_runtime_binding_unavailable"
    if entry.get("runtime_binding") != current_runtime_binding:
        return False, "marble_native_environment_runtime_binding_mismatch"
    state = entry.get("state_evidence") or {}
    initial = state.get("initial_state_sha256")
    healthcheck = state.get("healthcheck_state_sha256")
    reset = state.get("in_memory_reset_state_sha256")
    if not all(isinstance(value, str) and sha_pattern.fullmatch(value) for value in (initial, healthcheck, reset)):
        return False, "marble_native_environment_state_hash_invalid"
    if initial == healthcheck or initial != reset or state.get("host_state_snapshot") is not False:
        return False, "marble_native_environment_state_evidence_invalid"
    if not isinstance(entry.get("materialized_config_sha256"), str) or not sha_pattern.fullmatch(
        str(entry.get("materialized_config_sha256"))
    ):
        return False, "marble_native_environment_config_hash_invalid"
    bindings = entry.get("bindings") or {}
    expected_environment = SCENARIO_BINDINGS[scenario].environment_entrypoint
    if bindings != {
        "config": CONFIG_ENTRYPOINT,
        "engine": ENGINE_ENTRYPOINT,
        "environment": expected_environment,
        "evaluator": EVALUATOR_ENTRYPOINT,
    }:
        return False, "marble_native_environment_bindings_invalid"
    staging = entry.get("runtime_staging") or {}
    if (
        staging.get("adapter") != MARBLE_STAGING_ADAPTER
        or staging.get("upstream_mutated") is not False
        or staging.get("runtime_directories") != ["logs"]
        or staging.get("runtime_assets")
        != [
            {
                "path": DATABASE_COMPOSE_ASSET_PATH,
                "kind": "docker_compose_image_digest_pins",
                "source_sha256": DATABASE_COMPOSE_SOURCE_SHA256,
                "staged_sha256": DATABASE_COMPOSE_STAGED_SHA256,
                "images": DATABASE_IMAGE_REFERENCES,
            }
        ]
    ):
        return False, "marble_native_environment_staging_invalid"
    patches = staging.get("patches") or []
    if not isinstance(patches, list) or len(patches) != len(PINNED_STAGING_SOURCE_SHA256):
        return False, "marble_native_environment_staging_patch_count_invalid"
    by_path = {str(item.get("path")): item for item in patches if isinstance(item, dict)}
    if set(by_path) != set(PINNED_STAGING_SOURCE_SHA256):
        return False, "marble_native_environment_staging_patch_paths_invalid"
    for path, source_sha256 in PINNED_STAGING_SOURCE_SHA256.items():
        patch = by_path[path]
        if patch.get("source_sha256") != source_sha256:
            return False, "marble_native_environment_staging_source_hash_invalid"
        staged_sha256 = patch.get("staged_sha256")
        if not isinstance(staged_sha256, str) or not sha_pattern.fullmatch(staged_sha256):
            return False, "marble_native_environment_staging_output_hash_invalid"
        if staged_sha256 != PINNED_STAGING_OUTPUT_SHA256[path]:
            return False, "marble_native_environment_staging_output_hash_unpinned"
    database_runtime = entry.get("database_runtime")
    if scenario == "database":
        database_mode = entry.get("database_initialization_mode")
        if not isinstance(database_mode, dict) or database_mode.get(
            "anomaly_adapter_validated"
        ) is not True:
            return False, "marble_native_environment_database_mode_invalid"
        workload_executed = database_mode.get("workload_anomaly_executed")
        workload_deferred = database_mode.get("workload_deferred_to_model_episode")
        schema_reset = database_mode.get("schema_reset_before_case")
        if (
            not isinstance(workload_executed, bool)
            or not isinstance(workload_deferred, bool)
            or workload_executed == workload_deferred
            or schema_reset is not workload_deferred
        ):
            return False, "marble_native_environment_database_mode_invalid"
        if not isinstance(database_runtime, dict) or database_runtime.get(
            "compose_project"
        ) != DATABASE_COMPOSE_PROJECT:
            return False, "marble_native_environment_database_runtime_missing"
        services = database_runtime.get("services")
        if not isinstance(services, dict) or set(services) != DATABASE_SERVICES:
            return False, "marble_native_environment_database_services_invalid"
        image_id_pattern = re.compile(r"sha256:[0-9a-f]{64}")
        for service, expected_reference in DATABASE_IMAGE_REFERENCES.items():
            identity = services.get(service)
            if not isinstance(identity, dict):
                return False, "marble_native_environment_database_image_invalid"
            expected_digest = expected_reference.rsplit("@", 1)[1]
            repo_digests = identity.get("repo_digests")
            if (
                identity.get("configured_image") != expected_reference
                or not isinstance(identity.get("image_id"), str)
                or not image_id_pattern.fullmatch(identity["image_id"])
                or not isinstance(repo_digests, list)
                or not repo_digests
                or not any(
                    isinstance(digest, str)
                    and digest.endswith("@" + expected_digest)
                    for digest in repo_digests
                )
            ):
                return False, "marble_native_environment_database_image_invalid"
    elif database_runtime is not None or entry.get("database_initialization_mode") is not None:
        return False, "marble_native_environment_database_runtime_unexpected"
    recorded_digest = entry.get("evidence_sha256")
    payload = dict(entry)
    payload.pop("evidence_sha256", None)
    for envelope in MARBLE_REGISTRY_MERGE_ENVELOPES:
        payload.pop(envelope, None)
    if recorded_digest != _json_digest(payload):
        return False, "marble_native_environment_evidence_hash_invalid"
    return True, None


@dataclass(frozen=True)
class EpisodePreflight:
    ready: bool
    errors: tuple[str, ...]
    checks: dict[str, bool]
    command: tuple[str, ...]
    native_environment_evidence: dict[str, Any] | None = None


def _python_runtime(python: str) -> tuple[bool, str | None]:
    try:
        completed = subprocess.run(
            [python, "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, "marble_python_unavailable"
    version = completed.stdout.strip()
    if completed.returncode != 0 or not re.fullmatch(r"\d+\.\d+", version):
        return False, "marble_python_probe_failed"
    major, minor = (int(part) for part in version.split("."))
    if major != 3 or minor < 9 or minor >= 12:
        return False, f"marble_python_unsupported:{version}:requires_3.9_to_3.11"
    return True, None


def discover_supported_python(preferred: str | None = None) -> tuple[str | None, str | None]:
    """Find an absolute Python 3.9--3.11 executable, including Windows py."""

    candidates: list[str] = []
    if preferred:
        resolved = shutil.which(preferred)
        candidates.append(resolved or preferred)
    else:
        repository_root = Path(__file__).resolve().parents[1]
        for relative in (
            ".venv-marble-native/Scripts/python.exe",
            ".venv-marble-native/bin/python",
        ):
            bundled = repository_root / relative
            if bundled.is_file():
                candidates.append(str(bundled))
        candidates.append(sys.executable)
        launcher = shutil.which("py")
        if launcher:
            for version in ("3.11", "3.10", "3.9"):
                try:
                    completed = subprocess.run(
                        [
                            launcher,
                            f"-{version}",
                            "-c",
                            "import sys; print(sys.executable)",
                        ],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=15,
                    )
                except (OSError, subprocess.TimeoutExpired):
                    continue
                executable = completed.stdout.strip()
                if completed.returncode == 0 and executable:
                    candidates.append(executable)
        for name in ("python3.11", "python3.10", "python3.9", "python3", "python"):
            executable = shutil.which(name)
            if executable:
                candidates.append(executable)

    seen: set[str] = set()
    preferred_error: str | None = None
    for candidate in candidates:
        normalized = os.path.normcase(os.path.abspath(candidate))
        if normalized in seen:
            continue
        seen.add(normalized)
        supported, error = _python_runtime(candidate)
        if supported:
            try:
                return str(Path(candidate).resolve()), None
            except OSError:
                return candidate, None
        if preferred and preferred_error is None:
            preferred_error = error
    if preferred:
        return None, preferred_error or "marble_python_unavailable"
    return None, "marble_supported_python_not_found:requires_3.9_to_3.11"


def _dependency_probe(python: str, upstream_root: Path) -> tuple[bool, str | None]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(upstream_root) + (os.pathsep + existing if existing else "")
    try:
        completed = subprocess.run(
            [
                python,
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
            cwd=upstream_root,
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, "marble_dependency_probe_failed"
    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout).strip().splitlines()
        detail = tail[-1][:240] if tail else "unknown_import_error"
        return False, f"marble_dependencies_unavailable:{detail}"
    return True, None


def _bootstrap_report_fingerprint(report: Mapping[str, Any]) -> str:
    """Hash only stable qualification fields; absolute paths are intentionally omitted."""

    stable = {
        "schema_version": report.get("schema_version"),
        "status": report.get("status"),
        "system_site_packages": report.get("system_site_packages"),
        "dependency_lock_sha256": report.get("dependency_lock_sha256"),
        "pip_check": report.get("pip_check"),
        "actual_engine_evaluator_import": report.get(
            "actual_engine_evaluator_import"
        ),
        "import_checks": report.get("import_checks"),
        "upstream_dependency_coverage": report.get(
            "upstream_dependency_coverage"
        ),
        "intentional_exclusions": report.get("intentional_exclusions"),
        "case_scenarios": report.get("case_scenarios"),
        "python_version": (report.get("python_runtime") or {}).get("version"),
    }
    return _json_digest(stable)


@lru_cache(maxsize=8)
def _native_runtime_binding_cached(
    repository_root: str,
    selected_python: str,
    dependency_lock_sha256: str,
    dependency_artifact_sha256: str,
    bootstrap_report_sha256: str,
) -> tuple[dict[str, Any] | None, str | None]:
    root = Path(repository_root)
    lock_path = root / MARBLE_NATIVE_REQUIREMENTS_LOCK
    lock_artifact_path = root / MARBLE_NATIVE_DEPENDENCY_ARTIFACT
    report_path = root / MARBLE_NATIVE_BOOTSTRAP_REPORT
    try:
        report = _load_json(report_path)
    except (OSError, ValueError, TypeError):
        return None, "marble_bootstrap_report_invalid_json"

    runtime_probe = subprocess.run(
        [
            selected_python,
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
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if runtime_probe.returncode != 0:
        return None, "marble_native_python_runtime_probe_failed"
    try:
        python_runtime = json.loads(runtime_probe.stdout.strip())
    except (json.JSONDecodeError, TypeError):
        return None, "marble_native_python_runtime_probe_invalid"
    version_info = python_runtime.get("version_info")
    if (
        not isinstance(version_info, list)
        or len(version_info) != 3
        or version_info[0] != 3
        or not 9 <= version_info[1] < 12
    ):
        return None, "marble_native_python_runtime_unsupported"

    prefix = Path(str(python_runtime.get("prefix") or "")).resolve()
    base_prefix = Path(str(python_runtime.get("base_prefix") or "")).resolve()
    executable = Path(str(python_runtime.get("executable") or "")).resolve()
    pyvenv_config = prefix / "pyvenv.cfg"
    try:
        pyvenv_payload = (
            pyvenv_config.read_text(encoding="utf-8").lower().replace(" ", "")
        )
    except OSError:
        return None, "marble_native_python_not_a_virtual_environment"
    system_site_packages = "include-system-site-packages=false" not in pyvenv_payload
    python_runtime.update(
        {
            "executable": str(executable),
            "prefix": str(prefix),
            "base_prefix": str(base_prefix),
            "system_site_packages": system_site_packages,
        }
    )
    isolated_python = (
        not system_site_packages
        and prefix != base_prefix
        and os.path.normcase(str(executable))
        == os.path.normcase(str(Path(selected_python).resolve()))
    )

    uv = shutil.which("uv")
    pip_check = False
    if uv is not None:
        try:
            pip_result = subprocess.run(
                [uv, "pip", "check", "--python", selected_python],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
                timeout=300,
            )
            pip_check = pip_result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            pip_check = False

    imports_ok = False
    try:
        with __import__("tempfile").TemporaryDirectory(
            prefix="dtbench-marble-runtime-binding-"
        ) as directory:
            staged = stage_marble_runtime(
                root / "upstream/marble", Path(directory) / "runtime"
            )
            imports_ok, _import_error = _dependency_probe(selected_python, staged)
    except (OSError, MarbleQualificationError):
        imports_ok = False

    expected_report = {
        "schema_version": "marble-local-runtime-bootstrap-v2",
        "status": "dependencies_importable",
        "system_site_packages": False,
        "dependency_lock_sha256": dependency_lock_sha256,
        "pip_check": True,
        "actual_engine_evaluator_import": True,
        "import_checks": list(MARBLE_NATIVE_RUNTIME_IMPORTS),
        "upstream_dependency_coverage": list(
            MARBLE_UPSTREAM_DEPENDENCY_COVERAGE
        ),
        "intentional_exclusions": list(MARBLE_UPSTREAM_DEPENDENCY_EXCLUSIONS),
        "case_scenarios": ["bargaining", "coding", "database", "research"],
    }
    report_valid = all(report.get(key) == value for key, value in expected_report.items())
    report_valid = report_valid and report.get("python_runtime") == python_runtime
    report_valid = report_valid and Path(
        str(report.get("dependency_lock_source") or "")
    ).resolve() == lock_path.resolve()
    report_valid = report_valid and Path(
        str(report.get("dependency_lock") or "")
    ).resolve() == lock_artifact_path.resolve()
    report_valid = report_valid and not any(
        token in str(key).lower()
        for key in report
        for token in ("timestamp", "generated_at", "created_at")
    )
    lock_matches = (
        dependency_lock_sha256 == dependency_artifact_sha256
        and report.get("dependency_lock_sha256") == dependency_lock_sha256
    )
    checks = {
        "isolated_python": isolated_python,
        "dependency_lock_matches_bootstrap": lock_matches,
        "bootstrap_report_valid": report_valid,
        "pip_check": pip_check,
        "actual_import_checks": imports_ok,
    }
    if not all(checks.values()):
        failed = ",".join(name for name, value in checks.items() if not value)
        return None, f"marble_native_runtime_binding_failed:{failed}"
    return (
        {
            "python_runtime": python_runtime,
            "dependency_lock_path": MARBLE_NATIVE_REQUIREMENTS_LOCK,
            "dependency_lock_sha256": dependency_lock_sha256,
            "dependency_lock_artifact_path": MARBLE_NATIVE_DEPENDENCY_ARTIFACT,
            "dependency_lock_artifact_sha256": dependency_artifact_sha256,
            "bootstrap_report_path": MARBLE_NATIVE_BOOTSTRAP_REPORT,
            "bootstrap_report_sha256": bootstrap_report_sha256,
            "bootstrap_report_fingerprint_sha256": (
                _bootstrap_report_fingerprint(report)
            ),
            "checks": checks,
        },
        None,
    )


def native_runtime_binding(
    python: str | None = None,
    *,
    repository_root: Path | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Return a fail-closed binding to the checked-in isolated MARBLE runtime."""

    root = (repository_root or Path(__file__).resolve().parents[1]).resolve()
    selected_python = None
    python_error = None
    if python is None:
        for relative in (
            ".venv-marble-native/Scripts/python.exe",
            ".venv-marble-native/bin/python",
        ):
            canonical = root / relative
            if canonical.is_file():
                selected_python = str(canonical.resolve())
                break
    if selected_python is None:
        selected_python, python_error = discover_supported_python(python)
    if selected_python is None:
        return None, python_error
    lock_path = root / MARBLE_NATIVE_REQUIREMENTS_LOCK
    lock_artifact_path = root / MARBLE_NATIVE_DEPENDENCY_ARTIFACT
    report_path = root / MARBLE_NATIVE_BOOTSTRAP_REPORT
    if not lock_path.is_file():
        return None, "marble_native_dependency_lock_missing"
    if not lock_artifact_path.is_file():
        return None, "marble_native_dependency_lock_artifact_missing"
    if not report_path.is_file():
        return None, "marble_native_bootstrap_report_missing"
    return _native_runtime_binding_cached(
        str(root),
        str(Path(selected_python).resolve()),
        _sha256_file(lock_path),
        _sha256_file(lock_artifact_path),
        _sha256_file(report_path),
    )


def _credential_error(model: str, environment: Mapping[str, str]) -> str | None:
    normalized = model.strip().lower()
    if not normalized or model in MODEL_PLACEHOLDERS or "<provider/model>" in normalized:
        return "marble_model_not_materialized"
    if normalized in OFFLINE_PROVIDER_NAMES or normalized.startswith("offline/"):
        return "offline_provider_is_infrastructure_smoke_only"

    provider_credentials: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
        (("anthropic/", "claude"), ("ANTHROPIC_API_KEY",)),
        (("together_ai/", "together/"), ("TOGETHERAI_API_KEY",)),
        (("azure/",), ("AZURE_API_KEY", "AZURE_API_BASE")),
        (("gemini/", "google/"), ("GEMINI_API_KEY",)),
        (("bedrock/",), ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION")),
        (("openai/", "gpt-", "o1", "o3", "o4"), ("OPENAI_API_KEY",)),
    )
    for prefixes, names in provider_credentials:
        if normalized.startswith(prefixes):
            missing = [name for name in names if not environment.get(name)]
            if missing:
                return "marble_credential_missing:" + ",".join(missing)
            return None

    if normalized.startswith("ollama/"):
        return None
    return "marble_provider_credential_policy_unknown"


def provider_runtime_environment(
    environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Map workspace credential aliases in memory without exposing their values."""

    normalized = dict(os.environ if environment is None else environment)
    if not normalized.get("OPENAI_API_KEY") and normalized.get(
        "DTBENCH2_OPENAI_KEY"
    ):
        normalized["OPENAI_API_KEY"] = normalized["DTBENCH2_OPENAI_KEY"]
    return normalized


def _endpoint_ready(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= int(response.status) < 500
    except (OSError, urllib.error.URLError, ValueError):
        return False


DATABASE_COMPOSE_PROJECT = "dtbench-marble-db-runtime"
DATABASE_SERVICES = {"postgres_db", "prometheus", "node_exporter", "pg_exporter"}
DATABASE_PORTS = {
    "postgres": 5432,
    "prometheus": 9090,
    "node_exporter": 9100,
    "pg_exporter": 9187,
}
DATABASE_SERVICE_TARGET_PORTS = {
    "postgres_db": 5432,
    "prometheus": 9090,
    "node_exporter": 9100,
    "pg_exporter": 9187,
}


def _database_compose_context(
    upstream_root: Path,
) -> tuple[tuple[str, Path, dict[str, str]] | None, str | None]:
    docker = shutil.which("docker")
    if not docker:
        return None, "marble_database_docker_cli_missing"
    for args, error in (
        ([docker, "info", "--format", "{{.ServerVersion}}"], "marble_database_docker_daemon_unavailable"),
        ([docker, "compose", "version"], "marble_database_compose_unavailable"),
    ):
        try:
            completed = subprocess.run(
                args,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None, error
        if completed.returncode != 0:
            return None, error
    compose = upstream_root / "marble/environments/db_env_docker/docker-compose.yml"
    if not compose.is_file():
        return None, "marble_database_compose_definition_missing"
    compose_source = compose.read_text(encoding="utf-8")
    if (
        _sha256_bytes(compose_source.encode("utf-8"))
        != DATABASE_COMPOSE_STAGED_SHA256
        or any(reference not in compose_source for reference in DATABASE_IMAGE_REFERENCES.values())
    ):
        return None, "marble_database_compose_image_pins_missing"
    db_source = upstream_root / "marble/environments/db_env.py"
    anomaly_source = upstream_root / "marble/environments/db_env_docker/anomaly_trigger/anomaly.py"
    if (
        not db_source.is_file()
        or "Container lifecycle is owned by run_marble_native.py --provision"
        not in db_source.read_text(encoding="utf-8")
    ):
        return None, "marble_database_portable_compose_adapter_missing"
    if not anomaly_source.is_file() or "sudo docker compose restart" in anomaly_source.read_text(encoding="utf-8"):
        return None, "marble_database_portable_anomaly_adapter_missing"
    compose_env = os.environ.copy()
    compose_env["COMPOSE_PROJECT_NAME"] = DATABASE_COMPOSE_PROJECT
    return (docker, compose, compose_env), None


def _compose_service_names(
    docker: str,
    compose: Path,
    compose_env: Mapping[str, str],
    *,
    running_only: bool,
) -> tuple[set[str], str | None]:
    command = [docker, "compose", "-f", str(compose), "ps", "--services"]
    command.extend(["--status", "running"] if running_only else ["--all"])
    try:
        completed = subprocess.run(
            command,
            cwd=compose.parent,
            env=dict(compose_env),
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set(), "marble_database_compose_status_failed"
    if completed.returncode != 0:
        return set(), "marble_database_compose_status_failed"
    return {line.strip() for line in completed.stdout.splitlines() if line.strip()}, None


def _compose_project_host_ports(
    docker: str,
    compose: Path,
    compose_env: Mapping[str, str],
) -> tuple[set[int], str | None]:
    """Return fixed host ports currently published by this Compose project."""

    published: set[int] = set()
    for service, target_port in DATABASE_SERVICE_TARGET_PORTS.items():
        try:
            completed = subprocess.run(
                [
                    docker,
                    "compose",
                    "-f",
                    str(compose),
                    "port",
                    service,
                    str(target_port),
                ],
                cwd=compose.parent,
                env=dict(compose_env),
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )
        except (OSError, subprocess.TimeoutExpired):
            return set(), "marble_database_compose_port_probe_failed"
        # A stopped or absent service legitimately returns non-zero/no output.
        if completed.returncode != 0:
            continue
        for line in completed.stdout.splitlines():
            match = re.search(r":(\d+)\s*$", line.strip())
            if match:
                published.add(int(match.group(1)))
    return published, None


def database_service_image_evidence(
    upstream_root: Path,
) -> tuple[dict[str, Any] | None, str | None]:
    """Record immutable image identity for every running database service."""

    context, context_error = _database_compose_context(upstream_root)
    if context is None:
        return None, context_error
    docker, compose, compose_env = context
    services: dict[str, dict[str, Any]] = {}
    sha_pattern = re.compile(r"sha256:[0-9a-f]{64}")
    for service in sorted(DATABASE_SERVICES):
        try:
            container_result = subprocess.run(
                [
                    docker,
                    "compose",
                    "-f",
                    str(compose),
                    "ps",
                    "-q",
                    service,
                ],
                cwd=compose.parent,
                env=dict(compose_env),
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None, "marble_database_container_identity_probe_failed"
        containers = [
            line.strip()
            for line in container_result.stdout.splitlines()
            if line.strip()
        ]
        if container_result.returncode != 0 or len(containers) != 1:
            return None, f"marble_database_container_identity_missing:{service}"
        container_id = containers[0]

        values: list[str] = []
        for template in ("{{.Config.Image}}", "{{.Image}}"):
            try:
                inspected = subprocess.run(
                    [docker, "inspect", "--format", template, container_id],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
            except (OSError, subprocess.TimeoutExpired):
                return None, "marble_database_container_identity_probe_failed"
            value = inspected.stdout.strip()
            if inspected.returncode != 0 or not value:
                return None, f"marble_database_container_identity_missing:{service}"
            values.append(value)
        configured_image, image_id = values
        try:
            digest_result = subprocess.run(
                [
                    docker,
                    "image",
                    "inspect",
                    "--format",
                    "{{json .RepoDigests}}",
                    image_id,
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )
            repo_digests = json.loads(digest_result.stdout.strip())
        except (
            OSError,
            subprocess.TimeoutExpired,
            json.JSONDecodeError,
            TypeError,
        ):
            return None, "marble_database_image_digest_probe_failed"
        expected_reference = DATABASE_IMAGE_REFERENCES[service]
        expected_digest = expected_reference.rsplit("@", 1)[1]
        if (
            digest_result.returncode != 0
            or configured_image != expected_reference
            or not sha_pattern.fullmatch(image_id)
            or not isinstance(repo_digests, list)
            or not repo_digests
            or not any(
                isinstance(digest, str) and digest.endswith("@" + expected_digest)
                for digest in repo_digests
            )
        ):
            return None, f"marble_database_image_identity_mismatch:{service}"
        services[service] = {
            "configured_image": configured_image,
            "image_id": image_id,
            "repo_digests": sorted(repo_digests),
        }
    return {
        "compose_project": DATABASE_COMPOSE_PROJECT,
        "services": services,
    }, None


def _unowned_database_port_conflicts(
    owned_host_ports: set[int],
) -> list[str]:
    return [
        f"{name}:{port}"
        for name, port in DATABASE_PORTS.items()
        if port_is_available("127.0.0.1", port) and port not in owned_host_ports
    ]


def _database_endpoint_failures() -> list[str]:
    probes = {
        "postgres": lambda: port_is_available("127.0.0.1", 5432),
        "prometheus": lambda: _endpoint_ready("http://127.0.0.1:9090/-/ready"),
        "node_exporter": lambda: _endpoint_ready("http://127.0.0.1:9100/metrics"),
        "pg_exporter": lambda: _endpoint_ready("http://127.0.0.1:9187/metrics"),
    }
    return sorted(name for name, probe in probes.items() if not probe())


def _docker_ready(upstream_root: Path) -> tuple[bool, str | None]:
    """Non-mutating database readiness check used by ``--preflight-only``."""

    context, context_error = _database_compose_context(upstream_root)
    if context is None:
        return False, context_error
    docker, compose, compose_env = context
    running, status_error = _compose_service_names(docker, compose, compose_env, running_only=True)
    if status_error:
        return False, status_error
    owned_ports, port_error = _compose_project_host_ports(docker, compose, compose_env)
    if port_error:
        return False, port_error
    conflicts = _unowned_database_port_conflicts(owned_ports)
    if conflicts:
        return False, "marble_database_fixed_port_conflict:" + ",".join(conflicts)
    if running != DATABASE_SERVICES:
        missing = ",".join(sorted(DATABASE_SERVICES - running)) or "unknown"
        return False, f"marble_database_services_not_provisioned:{missing}"
    pending = _database_endpoint_failures()
    if pending:
        return False, "marble_database_service_endpoints_unready:" + ",".join(pending)
    return True, None


def provision_database_services(upstream_root: Path) -> tuple[bool, str | None]:
    """Explicitly recreate only the fixed MARBLE DB Compose project and volume."""

    context, context_error = _database_compose_context(upstream_root)
    if context is None:
        return False, context_error
    docker, compose, compose_env = context
    _owned, status_error = _compose_service_names(docker, compose, compose_env, running_only=False)
    if status_error:
        return False, status_error
    owned_ports, port_error = _compose_project_host_ports(docker, compose, compose_env)
    if port_error:
        return False, port_error
    conflicts = _unowned_database_port_conflicts(owned_ports)
    if conflicts:
        return False, "marble_database_fixed_port_conflict:" + ",".join(conflicts)
    # Destructive reset is scoped to this explicit project and only --provision.
    try:
        stopped = subprocess.run(
            [docker, "compose", "-f", str(compose), "down", "-v", "--remove-orphans"],
            cwd=compose.parent,
            env=compose_env,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, "marble_database_compose_reset_failed"
    if stopped.returncode != 0:
        return False, "marble_database_compose_reset_failed"
    try:
        started = subprocess.run(
            [
                docker,
                "compose",
                "-f",
                str(compose),
                "up",
                "-d",
                "--wait",
                "--wait-timeout",
                "45",
                "--remove-orphans",
            ],
            cwd=compose.parent,
            env=compose_env,
            check=False,
            capture_output=True,
            text=True,
            timeout=55,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, "marble_database_compose_start_timeout"
    if started.returncode != 0:
        tail = (started.stderr or started.stdout).strip().splitlines()
        detail = tail[-1][:160] if tail else "unknown_compose_error"
        return False, f"marble_database_compose_start_failed:{detail}"
    deadline = time.monotonic() + 30
    pending = _database_endpoint_failures()
    while pending and time.monotonic() < deadline:
        time.sleep(1)
        pending = _database_endpoint_failures()
    if pending:
        return False, "marble_database_service_endpoints_unready:" + ",".join(pending)
    return _docker_ready(upstream_root)


def episode_preflight(
    case_dir: Path,
    *,
    python: str | None,
    model: str,
    evaluator_model: str,
    upstream_root: Path,
    environment: Mapping[str, str] | None = None,
    initialize_native_environment: bool = False,
    provider_credentials_required: bool = True,
    source_evidence: Mapping[str, Any] | None = None,
) -> EpisodePreflight:
    """Fail closed before a MARBLE episode without provisioning services.

    The default path only inspects prerequisites and is therefore suitable for
    ``--preflight-only``.  A real launch explicitly opts into actual Engine,
    Environment, and Evaluator initialization after prerequisite checks pass.
    """

    env = provider_runtime_environment(environment)
    errors: list[str] = []
    checks: dict[str, bool] = {}
    config_path = case_dir.resolve() / "native_config.yaml"
    try:
        config = _load_yaml(config_path)
    except Exception:
        config = {}
        errors.append("marble_native_config_unreadable")
    scenario = str((config or {}).get("scenario") or "")

    validated_staging = _validated_staging_manifest(upstream_root)
    staging_ok = validated_staging is not None
    staging_manifest: dict[str, Any] = validated_staging or {}
    checks["temporary_portable_runtime_staged"] = staging_ok
    if not staging_ok:
        errors.append("marble_temporary_portability_staging_missing")

    selected_python, python_error = discover_supported_python(python)
    python_ok = selected_python is not None
    checks["supported_python_runtime"] = python_ok
    if python_error:
        errors.append(python_error)

    dependencies_ok = False
    if selected_python is not None:
        dependencies_ok, dependency_error = _dependency_probe(selected_python, upstream_root)
        if dependency_error:
            errors.append(dependency_error)
    checks["marble_dependencies_importable"] = dependencies_ok

    for label, selected_model in (("model", model), ("evaluator", evaluator_model)):
        if not provider_credentials_required:
            identifier_ready = bool(selected_model.strip())
            checks[f"{label}_provider_identifier_ready"] = identifier_ready
            checks[f"{label}_provider_calls_disabled"] = True
            if not identifier_ready:
                errors.append(f"{label}:marble_provider_identifier_missing")
            continue
        credential_error = _credential_error(selected_model, env)
        checks[f"{label}_provider_credential_ready"] = credential_error is None
        if credential_error:
            errors.append(f"{label}:{credential_error}")
        if selected_model.lower().startswith("ollama/") and credential_error is None:
            base = env.get("OLLAMA_API_BASE", "http://127.0.0.1:11434").rstrip("/")
            endpoint_ok = _endpoint_ready(base + "/api/tags")
            checks[f"{label}_provider_service_ready"] = endpoint_ok
            if not endpoint_ok:
                errors.append(f"{label}:marble_ollama_service_unavailable")
        else:
            checks[f"{label}_provider_service_ready"] = credential_error is None

    if scenario == "database":
        supported_anomalies = {
            "FETCH_LARGE_DATA",
            "LOCK_CONTENTION",
            "VACUUM",
            "INSERT_LARGE_DATA",
            "REDUNDANT_INDEX",
        }
        configured = {
            str(item.get("anomaly") or "")
            for item in ((config or {}).get("environment") or {}).get("anomalies", [])
            if isinstance(item, dict)
        }
        anomaly_config_ok = bool(configured) and configured.issubset(supported_anomalies)
        checks["database_anomaly_adapter_supported"] = anomaly_config_ok
        if not anomaly_config_ok:
            errors.append("marble_database_anomaly_adapter_unsupported")
        provider_checks_ready = all(
            value is True
            for name, value in checks.items()
            if name.startswith(("model_provider_", "evaluator_provider_"))
        )
        service_prerequisites = (
            python_ok and dependencies_ok and provider_checks_ready and staging_ok
        )
        if service_prerequisites:
            docker_ok, docker_error = _docker_ready(upstream_root)
        else:
            docker_ok = False
            docker_error = "marble_database_service_probe_skipped_due_to_failed_prerequisites"
        checks["scenario_service_ready"] = docker_ok
        if docker_error:
            errors.append(docker_error)
    else:
        checks["scenario_service_ready"] = scenario in SCENARIO_BINDINGS
        if scenario not in SCENARIO_BINDINGS:
            errors.append("marble_scenario_unsupported")

    checks["output_directory_writable"] = config_path.parent.is_dir() and os.access(
        config_path.parent, os.W_OK
    )
    if not checks["output_directory_writable"]:
        errors.append("marble_case_directory_not_writable")

    native_environment_evidence: dict[str, Any] | None = None
    prerequisites_ready = not errors and all(checks.values())
    if (
        initialize_native_environment
        and prerequisites_ready
        and selected_python is not None
    ):
        with __import__("tempfile").TemporaryDirectory(
            prefix="dtbench-marble-native-probe-"
        ) as probe_directory:
            probe_root = Path(probe_directory)
            materialized = probe_root / "native_config.yaml"
            evidence_path = probe_root / "native_environment_evidence.json"
            try:
                materialize_episode_config(
                    config_path,
                    materialized,
                    model=model,
                    evaluator_model=evaluator_model,
                )
                probe_environment = env.copy()
                existing = probe_environment.get("PYTHONPATH")
                probe_environment["PYTHONPATH"] = str(upstream_root) + (
                    os.pathsep + existing if existing else ""
                )
                probe_environment["COMPOSE_PROJECT_NAME"] = (
                    "dtbench-marble-db-runtime"
                )
                if not provider_credentials_required:
                    probe_environment["DTBENCH_MARBLE_INITIALIZATION_PROBE"] = "1"
                probe_script = (
                    Path(__file__).resolve().parents[1]
                    / "scripts/probe_marble_native_environment.py"
                )
                completed = subprocess.run(
                    [
                        selected_python,
                        str(probe_script),
                        "--config",
                        str(materialized),
                        "--case-id",
                        case_dir.name,
                        "--source-task-id",
                        f"{scenario}:{int((config or {}).get('task_id')):03d}",
                        "--scenario",
                        scenario,
                        "--output",
                        str(evidence_path),
                    ],
                    cwd=upstream_root,
                    env=probe_environment,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
            except (OSError, subprocess.TimeoutExpired, TypeError, ValueError) as exc:
                completed = None
                errors.append(
                    f"marble_native_environment_probe_failed:{type(exc).__name__}"
                )
            if completed is not None and completed.returncode == 0 and evidence_path.is_file():
                try:
                    candidate = _load_json(evidence_path)
                    runtime_binding, runtime_binding_error = (
                        native_runtime_binding(selected_python)
                    )
                    if runtime_binding is None:
                        errors.append(
                            runtime_binding_error
                            or "marble_native_runtime_binding_failed"
                        )
                    if source_evidence is None:
                        errors.append("marble_native_source_evidence_missing")
                    candidate["source_evidence"] = dict(source_evidence or {})
                    candidate["runtime_binding"] = runtime_binding
                    candidate["runtime_staging"] = {
                        "adapter": staging_manifest.get("adapter"),
                        "upstream_mutated": staging_manifest.get(
                            "upstream_mutated"
                        ),
                        "runtime_directories": staging_manifest.get(
                            "runtime_directories"
                        ),
                        "runtime_assets": staging_manifest.get("runtime_assets"),
                        "patches": staging_manifest.get("patches"),
                    }
                    if scenario == "database":
                        database_runtime, database_runtime_error = (
                            database_service_image_evidence(upstream_root)
                        )
                        if database_runtime is None:
                            errors.append(
                                database_runtime_error
                                or "marble_database_image_evidence_missing"
                            )
                        else:
                            candidate["database_runtime"] = database_runtime
                    if runtime_binding is not None and source_evidence is not None:
                        candidate.pop("evidence_sha256", None)
                        candidate["evidence_sha256"] = _json_digest(candidate)
                        valid, _reason = validate_native_environment_evidence(candidate)
                        if valid:
                            native_environment_evidence = candidate
                        else:
                            errors.append(
                                "marble_native_environment_probe_invalid_evidence:"
                                + str(_reason)
                            )
                except Exception:
                    errors.append("marble_native_environment_probe_invalid_json")
            elif completed is not None:
                tail = (completed.stderr or completed.stdout).strip().splitlines()
                detail = tail[-1][:240] if tail else "unknown_probe_error"
                errors.append(f"marble_native_environment_probe_failed:{detail}")
    if initialize_native_environment:
        checks["actual_native_environment_initialized_and_reset"] = (
            native_environment_evidence is not None
        )

    command = (
        selected_python or python or "<supported-python-3.9-to-3.11>",
        "-m",
        "marble.main",
        "--config_path",
        str(config_path),
    )
    return EpisodePreflight(
        ready=not errors and all(checks.values()),
        errors=tuple(dict.fromkeys(errors)),
        checks=checks,
        command=command,
        native_environment_evidence=native_environment_evidence,
    )


def materialize_episode_config(
    source: Path,
    destination: Path,
    *,
    model: str,
    evaluator_model: str,
) -> None:
    config = _load_yaml(source)
    if not isinstance(config, dict):
        raise MarbleQualificationError("marble_native_config_not_object")
    config["llm"] = model
    metrics = config.setdefault("metrics", {})
    if not isinstance(metrics, dict):
        raise MarbleQualificationError("marble_native_metrics_not_object")
    metrics["evaluate_llm"] = evaluator_model
    destination.parent.mkdir(parents=True, exist_ok=True)
    _write_text_lf(
        destination,
        # Upstream Config.load uses the Windows locale default instead of UTF-8.
        # ASCII-safe YAML escapes preserve the parsed Unicode values while making
        # every materialized case readable under that unchanged official loader.
        yaml.safe_dump(config, allow_unicode=False, sort_keys=False),
    )


def port_is_available(host: str, port: int) -> bool:
    """Small helper exposed for tests and future scenario-service gates."""

    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


__all__ = [
    "CONFIG_ENTRYPOINT",
    "ENGINE_ENTRYPOINT",
    "EVALUATOR_ENTRYPOINT",
    "MARBLE_BENCHMARK",
    "MARBLE_NATIVE_INITIALIZATION_PROFILE",
    "MARBLE_NATIVE_INITIALIZATION_SCOPE",
    "MARBLE_NATIVE_INITIALIZATION_STATUS",
    "MARBLE_NATIVE_RUNTIME_IMPORTS",
    "MARBLE_NATIVE_REQUIREMENTS_LOCK",
    "MARBLE_NATIVE_DEPENDENCY_ARTIFACT",
    "MARBLE_NATIVE_BOOTSTRAP_REPORT",
    "MARBLE_OFFLINE_PROVIDER",
    "MARBLE_SMOKE_SCHEMA",
    "MARBLE_SMOKE_SCOPE",
    "MARBLE_SMOKE_STATUS",
    "MARBLE_STAGING_ADAPTER",
    "PINNED_STAGING_SOURCE_SHA256",
    "PINNED_STAGING_OUTPUT_SHA256",
    "MarbleQualificationError",
    "MarbleUpstreamBindings",
    "LocalMarbleEnvironment",
    "OfflineDeterministicProvider",
    "EpisodePreflight",
    "episode_preflight",
    "discover_supported_python",
    "database_service_image_evidence",
    "materialize_episode_config",
    "merge_smoke_evidence",
    "native_runtime_binding",
    "official_record_digest",
    "provider_runtime_environment",
    "provision_database_services",
    "qualify_marble_case",
    "stage_marble_runtime",
    "validate_native_environment_evidence",
    "write_jsonl",
]
