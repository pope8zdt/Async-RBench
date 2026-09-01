from __future__ import annotations

import json
from typing import Any

from ...evaluation.model_backend import ModelTurn, ToolCall


class ScriptedTestBackend:
    """Non-evaluated deterministic backend used to drive protocol conformance.

    Moved out of the kernel (``evaluation.model_backend``) in Phase 4: it is a
    *conformance* concern, not a provider concern. It deterministically emits the
    full public event stream so a profile adapter can be exercised without a
    model API.
    """

    def __init__(self) -> None:
        self._turn_counter = 0

    def runtime_metadata(self) -> dict[str, Any]:
        return {"model_observations": []}

    async def complete(
        self,
        *,
        role: str,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        seed: int,
    ) -> ModelTurn:
        if role.startswith("child:"):
            task = next((str(m.get("content", "")) for m in messages if m.get("role") == "user"), "")
            hint = self._result_hint(task)
            evidence: dict[str, Any] = {"scripted": True, "hint": hint}
            if hint == "checkpoint recovery 5 rows":
                evidence["recovered_row_count"] = 5
            elif hint == "wal recovery 11 rows":
                evidence["recovered_row_count"] = 11
            return self._turn([("submit_result", {
                "summary": f"scripted isolated result for: {task[-300:]}",
                "result_kind_hint": hint,
                "evidence": evidence,
            })])

        # The benchmark owns the initial concurrent wave; the evaluated model is
        # never scored on having spawned the initial team, so the scripted
        # controller waits for, acknowledges, integrates and reverifies the
        # gateway-delivered completions instead of creating children.
        deliveries = self._deliveries(messages)
        acknowledged = {
            str(args.get("completion_id")) for name, args in self._call_items(messages)
            if name == "acknowledge_result"
        }
        new_deliveries = [item for item in deliveries if str(item.get("completion_id")) not in acknowledged]
        if new_deliveries:
            return self._turn([("acknowledge_result", {
                "completion_id": item["completion_id"],
                "decision": "reject" if item.get("stale") else "use",
                "reason": "reject explicitly stale evidence" if item.get("stale") else "use delivered evidence",
            }) for item in new_deliveries])
        if len(deliveries) < 3:
            return self._turn([("wait_for_results", {
                "child_ids": [], "timeout_seconds": 1.0, "return_when": "any",
            })])

        non_stale = [str(item["completion_id"]) for item in deliveries if not item.get("stale")]
        tool_map = {item["function"]["name"]: item for item in tools}
        commits = [args for name, args in self._call_items(messages) if name == "commit_artifact"]
        if not commits:
            artifact_schema = tool_map["commit_artifact"]["function"]["parameters"]["properties"]["artifact_id"]
            artifact_ids = artifact_schema.get("enum") or ["artifact"]
            return self._turn([("commit_artifact", {
                "artifact_id": artifact_ids[0],
                "version": "scripted-final",
                "lineage_completion_ids": non_stale,
                "evidence_paths": [],
                "final": True,
            })])

        verified = any(
            name == "verify_current_state" for name, _ in self._call_items(messages)
        )
        if not verified:
            artifact_schema = tool_map["verify_current_state"]["function"]["parameters"]["properties"]["artifact_ids"]["items"]
            return self._turn([("verify_current_state", {
                "artifact_ids": list(artifact_schema.get("enum") or []),
                "lineage_completion_ids": non_stale,
            })])
        return self._turn([("finish", {"status": "completed", "summary": "scripted scaffold conformance run"})])

    def _turn(self, items: list[tuple[str, dict[str, Any]]]) -> ModelTurn:
        self._turn_counter += 1
        raw_calls = []
        calls = []
        for index, (name, arguments) in enumerate(items):
            call_id = f"scripted-{self._turn_counter}-{name}-{index}"
            raw_calls.append({"id": call_id, "type": "function", "function": {
                "name": name, "arguments": json.dumps(arguments, sort_keys=True),
            }})
            calls.append(ToolCall(call_id, name, arguments))
        return ModelTurn(
            assistant_message={"role": "assistant", "content": None, "tool_calls": raw_calls},
            tool_calls=calls,
            total_tokens=10,
        )

    @staticmethod
    def _call_items(messages: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
        result = []
        for message in messages:
            if message.get("role") != "assistant":
                continue
            for call in message.get("tool_calls") or []:
                function = call.get("function", {})
                raw = function.get("arguments") or "{}"
                try:
                    args = json.loads(raw) if isinstance(raw, str) else raw
                except json.JSONDecodeError:
                    args = {}
                result.append((str(function.get("name", "")), args if isinstance(args, dict) else {}))
        return result

    @classmethod
    def _calls(cls, messages: list[dict[str, Any]]) -> set[str]:
        return {name for name, _ in cls._call_items(messages)}

    @staticmethod
    def _successful_spawn_tasks(messages: list[dict[str, Any]]) -> set[str]:
        calls: dict[str, tuple[str, dict[str, Any]]] = {}
        for message in messages:
            if message.get("role") == "assistant":
                for call in message.get("tool_calls") or []:
                    function = call.get("function", {})
                    raw = function.get("arguments") or "{}"
                    try:
                        args = json.loads(raw) if isinstance(raw, str) else raw
                    except json.JSONDecodeError:
                        args = {}
                    calls[str(call.get("id", ""))] = (str(function.get("name", "")), args if isinstance(args, dict) else {})
        successful = set()
        for message in messages:
            if message.get("role") != "tool":
                continue
            name, args = calls.get(str(message.get("tool_call_id", "")), ("", {}))
            if name != "spawn_subagent":
                continue
            try:
                result = json.loads(str(message.get("content", "{}")))
            except json.JSONDecodeError:
                result = {}
            if result.get("child_id"):
                successful.add(str(args.get("task", "")))
        return successful

    @staticmethod
    def _deliveries(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for message in messages:
            content = message.get("content")
            if message.get("role") != "user" or not isinstance(content, str) or not content.startswith("ASYNC_RBENCH_DELIVERY "):
                continue
            result.append(json.loads(content.removeprefix("ASYNC_RBENCH_DELIVERY ")))
        return result

    @staticmethod
    def _case_tasks(instruction: str) -> list[tuple[str, list[str]]]:
        lower = instruction.lower()
        if "main.db-wal" in lower:
            return [
                ("Recover the five-row checkpoint-only database state", ["checkpoint", "database"]),
                ("Recover all eleven authoritative WAL rows", ["wal", "authoritative", "database"]),
                ("Independently merge sources and support the gRPC integration", ["merge", "grpc"]),
            ]
        if "columnparallellinear" in lower:
            return [
                ("Build the provisional v1 tensor-parallel deployment branch", ["tp", "provisional"]),
                ("Inspect authoritative hardware profile v2 and choose the feasible backend", ["hardware", "profile", "authoritative"]),
                ("Recover the model and implement independent PP and scheduler support", ["model", "pp", "scheduler"]),
            ]
        return [
            ("Patch and deploy the security fix before the history rewrite", ["patch", "deploy"]),
            ("Perform the authoritative sanitized Git history rewrite", ["sanitized", "history", "authoritative"]),
            ("Configure independent Git and nginx runtime support", ["git", "nginx"]),
        ]

    @staticmethod
    def _workstream_id(task: str) -> str:
        lower = task.lower()
        if "five-row" in lower or "checkpoint" in lower:
            return "checkpoint_recovery"
        if "eleven" in lower or "wal" in lower:
            return "wal_recovery"
        if "merge" in lower:
            return "merge_support"
        if "provisional" in lower or "tensor-parallel" in lower:
            return "implement_tp"
        if "hardware" in lower or "profile" in lower:
            return "select_backend"
        if "recover the model" in lower:
            return "recover_model"
        if "patch and deploy" in lower:
            return "patch_pre_rewrite"
        if "sanitized" in lower or "history rewrite" in lower:
            return "sanitize_history"
        return "release_infrastructure"

    @staticmethod
    def _result_hint(task: str) -> str:
        lower = task.lower()
        if "checkpoint" in lower:
            return "checkpoint recovery 5 rows"
        if "wal" in lower:
            return "wal recovery 11 rows"
        if "provisional" in lower or "tensor-parallel" in lower:
            return "tp deployment for v1"
        if "hardware" in lower or "profile" in lower:
            return "hardware profile v2"
        if "patch and deploy" in lower:
            return "patch and deploy pre rewrite"
        if "sanitized" in lower or "history rewrite" in lower:
            return "authoritative sanitized history"
        return "independent support"
