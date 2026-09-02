"""Task 7: dual main/child provider backends reference-scaffold routing.

TDD: ``run_one_main_and_one_child_turn`` drives one main model call through the
``main_backend`` and one child turn through the ``child_backend``. A role-scoped
spy records which backend saw which ``role``, and the two backends carry distinct
URL / credential env name / request parameters / tokenizer metadata / concurrency
semaphore so a fixed child pool is provably isolated from the main provider.
"""

from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path

from async_rbench.evaluation.model_backend import (
    ModelTurn,
    OpenAICompatibleBackend,
    TokenEstimate,
    ToolCall,
)
from async_rbench.evaluation.runner import EpisodeConfig, _make_start
from async_rbench.evaluation.workspace_runtime import DisabledWorkspaceRuntime
from async_rbench.profiles.reference_scaffold_api.config import ScaffoldConfig
from async_rbench.profiles.reference_scaffold_api.gateway import (
    DeliveryReader,
    ProtocolEmitter,
)
from async_rbench.profiles.reference_scaffold_api.runtime import ReferenceScaffold
from async_rbench.spec import load_case


ROOT = Path(__file__).resolve().parents[1]


def _start(case_id: str = "data-recovery-service") -> dict:
    case_path = ROOT / "cases" / case_id / "public_case.yaml"
    case = load_case(case_path).raw
    import yaml

    task = yaml.safe_load((case_path.parent / "task" / "task.yaml").read_text(encoding="utf-8"))
    config = EpisodeConfig(
        episode_id="dual-provider-test",
        case_id=case_id,
        execution_mode="async",
        guidance="incentive",
        agent_seed=1,
        adapter_command=[str(ROOT / "adapters" / "reference_scaffold_api.py")],
        output_dir=ROOT / "artifacts" / "dual-provider-test",
        use_container=False,
    )
    return _make_start(config, case, task, None, "0123456789ab")


def _dual_config() -> ScaffoldConfig:
    """A config whose main/child providers differ on every role-specific axis."""
    return ScaffoldConfig.from_file(None, {
        "backend": "openai_compatible",
        "main_model": "main-model-1",
        "child_model": "child-model-fixed",
        "child_pool_id": "fixed-child-pool-A",
        "api_key_required": False,
        "api_url": "https://legacy.example/v1/chat/completions",
        "api_key_env": "LEGACY_KEY",
        "max_api_concurrency": 4,
        "max_tokens_parameter": "max_completion_tokens",
        "tokenizer": "legacy-tok",
        "request_body_extra": {"legacy": True},
        "main_provider": {
            "api_url": "https://main.example/v1/chat/completions",
            "api_key_env": "MAIN_KEY",
            "max_api_concurrency": 4,
            "max_tokens_parameter": "max_completion_tokens",
            "tokenizer": "main-tok",
            "request_body_extra": {"main_extra": True},
        },
        "child_provider": {
            "backend": "openai_compatible",
            "api_url": "https://child.example/v1/chat/completions",
            "api_key_env": "CHILD_KEY",
            "max_api_concurrency": 2,
            "max_tokens_parameter": "max_tokens",
            "tokenizer": "child-tok",
            "request_body_extra": {"child_extra": True},
        },
    })


class _SpyBackend:
    """Role-scoped backend spy that records the role of every model call."""

    def __init__(self, *, submits: bool = False) -> None:
        self.roles: list[str] = []
        self.config = None
        self.submits = submits
        self._semaphore = object()
        self.estimate_calls = 0

    def attach(self, config) -> None:
        self.config = config

    async def complete(
        self,
        *,
        role: str,
        model: str,
        messages: list[dict],
        tools: list[dict],
        seed: int,
    ) -> ModelTurn:
        self.roles.append(role)
        if self.submits:
            call = ToolCall(
                "sc-1", "submit_result", {"summary": "s", "result_kind_hint": "hint"},
            )
            return ModelTurn(
                assistant_message={
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "sc-1", "type": "function",
                        "function": {
                            "name": "submit_result",
                            "arguments": json.dumps({"summary": "s", "result_kind_hint": "hint"}),
                        },
                    }],
                },
                tool_calls=[call],
                total_tokens=0,
            )
        return ModelTurn(
            assistant_message={"role": "assistant", "content": "done"},
            tool_calls=[],
            total_tokens=0,
        )

    def estimate_input_tokens(self, messages: list[dict], tools: list[dict]) -> TokenEstimate:
        self.estimate_calls += 1
        return TokenEstimate(1, "conservative")

    def runtime_metadata(self) -> dict:
        cfg = self.config
        return {
            "role": cfg.role if cfg else "",
            "child_pool_id": cfg.child_pool_id if cfg else "",
            "model_observations": [
                {"role": role, "requested_model": "m", "resolved_model": "m"}
                for role in self.roles
            ],
        }


def make_scaffold(main_backend, child_backend, config) -> ReferenceScaffold:
    return ReferenceScaffold(
        start=_start(),
        config=config,
        main_backend=main_backend,
        child_backend=child_backend,
        workspace=DisabledWorkspaceRuntime(),
        emitter=ProtocolEmitter(stdout=io.StringIO()),
        delivery_reader=DeliveryReader(),
    )


def test_main_and_children_use_distinct_backends() -> None:
    config = _dual_config()
    main_spy = _SpyBackend(submits=False)
    child_spy = _SpyBackend(submits=True)
    main_spy.attach(config.provider_role_config("main"))
    child_spy.attach(config.provider_role_config("child"))
    scaffold = make_scaffold(main_spy, child_spy, config)

    asyncio.run(scaffold.run_one_main_and_one_child_turn())

    assert main_spy.roles == ["main"]
    assert child_spy.roles == ["child:child-1"]


def test_provider_role_config_is_role_scoped() -> None:
    config = _dual_config()
    main_cfg = config.provider_role_config("main")
    child_cfg = config.provider_role_config("child")

    assert main_cfg.role == "main"
    assert child_cfg.role == "child"
    assert main_cfg.child_pool_id == child_cfg.child_pool_id == "fixed-child-pool-A"
    # URL
    assert main_cfg.api_url != child_cfg.api_url
    assert main_cfg.api_url == "https://main.example/v1/chat/completions"
    assert child_cfg.api_url == "https://child.example/v1/chat/completions"
    # credential env name
    assert main_cfg.api_key_env == "MAIN_KEY"
    assert child_cfg.api_key_env == "CHILD_KEY"
    # request parameters (max_tokens_parameter + request_body_extra)
    assert main_cfg.max_tokens_parameter == "max_completion_tokens"
    assert child_cfg.max_tokens_parameter == "max_tokens"
    assert main_cfg.request_body_extra == {"main_extra": True}
    assert child_cfg.request_body_extra == {"child_extra": True}
    # tokenizer metadata
    assert main_cfg.tokenizer == "main-tok"
    assert child_cfg.tokenizer == "child-tok"
    # concurrency ceiling differs per role
    assert main_cfg.max_api_concurrency != child_cfg.max_api_concurrency
    assert main_cfg.max_api_concurrency == 4
    assert child_cfg.max_api_concurrency == 2
    # model identity is role-scoped too
    assert main_cfg.model == "main-model-1"
    assert child_cfg.model == "child-model-fixed"


def test_build_backends_creates_two_role_scoped_backends() -> None:
    from async_rbench.profiles.reference_scaffold_api.config import build_backends

    config = _dual_config()
    main_backend, child_backend = build_backends(config)

    assert isinstance(main_backend, OpenAICompatibleBackend)
    assert isinstance(child_backend, OpenAICompatibleBackend)
    assert main_backend is not child_backend
    # Distinct concurrency semaphores (role-separated transport budgets).
    assert main_backend._semaphore is not child_backend._semaphore
    assert main_backend.config.role == "main"
    assert child_backend.config.role == "child"
    assert child_backend.config.child_pool_id == "fixed-child-pool-A"


def test_public_metadata_stamps_child_pool_and_provider_identity() -> None:
    config = _dual_config()
    metadata = config.public_metadata()
    assert metadata["child_pool_id"] == "fixed-child-pool-A"
    assert metadata["main_provider"]["api_url"] == "https://main.example/v1/chat/completions"
    assert metadata["main_provider"]["max_api_concurrency"] == 4
    assert metadata["child_provider"]["api_url"] == "https://child.example/v1/chat/completions"
    assert metadata["child_provider"]["max_api_concurrency"] == 2
    # The legacy top-level identity is retained for Track A eligibility.
    assert metadata["backend"] == "openai_compatible"
    assert metadata["main_model"] == "main-model-1"
    assert metadata["child_model"] == "child-model-fixed"
