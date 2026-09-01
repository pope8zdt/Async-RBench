from __future__ import annotations

import ast
import base64
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import yaml
import argparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from async_rbench.case_transformability import build_transformability_audit
from scripts.candidate_write_guard import guard_for_root


SELECTED = [
    "swe-partial-failure-recovery-fdf2f24539",
]

SWE_IMAGES = {
    "clap-rs__clap-2534": "mswebench/clap-rs_m_clap:pr-2534",
    "ponylang__ponyc-2201": "mswebench/ponylang_m_ponyc:pr-2201",
    "instance_qutebrowser__qutebrowser-473a15f7908f2bb6d670b0e908ab34a28d8cf7e2-v363c8a7e5ccdf6968fc7ab84a2053ac78036691d": "jefzda/sweap-images:qutebrowser.qutebrowser-qutebrowser__qutebrowser-473a15f7908f2bb6d670b0e908ab34a28d8cf7e2-v363c8a7e5ccdf6968fc7ab84a2053ac780366",
    "instance_ansible__ansible-4c5ce5a1a9e79a845aff4978cfeb72a0d4ecf7d6-v1055803c3a812189a1133297f7f5468579283f86": "jefzda/sweap-images:ansible.ansible-ansible__ansible-4c5ce5a1a9e79a845aff4978cfeb72a0d4ecf7d6-v1055803c3a812189a1133297f7f5468579283f86",
    "instance_element-hq__element-web-fe14847bb9bb07cab1b9c6c54335ff22ca5e516a-vnan": "jefzda/sweap-images:element-hq.element-element-hq__element-web-fe14847bb9bb07cab1b9c6c54335ff22ca5e516a",
    "instance_future-architect__vuls-b8db2e0b74f60cb7d45f710f255e061f054b6afc": "jefzda/sweap-images:future-architect.vuls-future-architect__vuls-b8db2e0b74f60cb7d45f710f255e061f054b6afc",
    "facebook__zstd-2094": "mswebench/facebook_m_zstd:pr-2094",
    "scikit-learn__scikit-learn-12973": "ghcr.io/epoch-research/swe-bench.eval.x86_64.scikit-learn__scikit-learn-12973:latest",
    "sphinx-doc__sphinx-8638": "ghcr.io/epoch-research/swe-bench.eval.x86_64.sphinx-doc__sphinx-8638:latest",
    "astropy__astropy-14539": "ghcr.io/epoch-research/swe-bench.eval.x86_64.astropy__astropy-14539:latest",
    "pallets__flask-5014": "ghcr.io/epoch-research/swe-bench.eval.x86_64.pallets__flask-5014:latest",
    "pylint-dev__pylint-4604": "ghcr.io/epoch-research/swe-bench.eval.x86_64.pylint-dev__pylint-4604:latest",
    "sympy__sympy-24066": "ghcr.io/epoch-research/swe-bench.eval.x86_64.sympy__sympy-24066:latest",
    "pydata__xarray-7229": "ghcr.io/epoch-research/swe-bench.eval.x86_64.pydata__xarray-7229:latest",
    "scikit-learn__scikit-learn-14983": "ghcr.io/epoch-research/swe-bench.eval.x86_64.scikit-learn__scikit-learn-14983:latest",
    "pytest-dev__pytest-7205": "ghcr.io/epoch-research/swe-bench.eval.x86_64.pytest-dev__pytest-7205:latest",
    "matplotlib__matplotlib-22719": "ghcr.io/epoch-research/swe-bench.eval.x86_64.matplotlib__matplotlib-22719:latest",
    "sphinx-doc__sphinx-11510": "ghcr.io/epoch-research/swe-bench.eval.x86_64.sphinx-doc__sphinx-11510:latest",
    "sympy__sympy-22714": "ghcr.io/epoch-research/swe-bench.eval.x86_64.sympy__sympy-22714:latest",
    "pytest-dev__pytest-5631": "ghcr.io/epoch-research/swe-bench.eval.x86_64.pytest-dev__pytest-5631:latest",
    "pylint-dev__pylint-8898": "ghcr.io/epoch-research/swe-bench.eval.x86_64.pylint-dev__pylint-8898:latest",
    "django__django-12262": "ghcr.io/epoch-research/swe-bench.eval.x86_64.django__django-12262:latest",
}

SWE_EVENT_PROBES = {
    "clap-rs__clap-2534": {
        "event": "hidden_help_heading_compile_result",
        "meaning": "An independent Rust worker reports that custom help headings are omitted when all arguments in the section are hidden while visible headings remain intact.",
        "paths": ["/testbed/.git/HEAD", "/testbed/src/output/help.rs", "/testbed/tests/help.rs"],
    },
    "ponylang__ponyc-2201": {
        "event": "dontcare_argument_diagnostic_result",
        "meaning": "An independent Pony compiler worker reports that illegal reads from '_' are rejected during expression analysis without compiler crashes.",
        "paths": ["/testbed/.git/HEAD", "/testbed/src/libponyc/expr/reference.c", "/testbed/src/libponyc/pass/verify.c"],
    },
    "instance_qutebrowser__qutebrowser-473a15f7908f2bb6d670b0e908ab34a28d8cf7e2-v363c8a7e5ccdf6968fc7ab84a2053ac78036691d": {
        "event": "qtwebengine_locale_fallback_result",
        "meaning": "An independent qutebrowser worker reports guarded QtWebEngine 5.15.3 locale fallback behavior across the upstream locale corpus.",
        "paths": ["/testbed/.git/HEAD", "/testbed/qutebrowser/config/qtargs.py", "/testbed/qutebrowser/config/configdata.yml"],
    },
    "instance_ansible__ansible-4c5ce5a1a9e79a845aff4978cfeb72a0d4ecf7d6-v1055803c3a812189a1133297f7f5468579283f86": {
        "event": "module_interpreter_respawn_result",
        "meaning": "An independent Ansible unit worker reports SELinux compatibility and module-interpreter respawn behavior from the upstream regression surface.",
        "paths": ["/testbed/.git/HEAD", "/testbed/lib/ansible/module_utils/common/respawn.py", "/testbed/lib/ansible/module_utils/compat/selinux.py"],
    },
    "instance_element-hq__element-web-fe14847bb9bb07cab1b9c6c54335ff22ca5e516a-vnan": {
        "event": "voice_broadcast_recording_result",
        "meaning": "An independent Jest worker reports voice-broadcast recording state, store lifecycle, and component behavior.",
        "paths": ["/testbed/.git/HEAD", "/testbed/src/voice-broadcast/index.ts", "/testbed/src/voice-broadcast/models/VoiceBroadcastRecording.ts"],
    },
    "instance_future-architect__vuls-b8db2e0b74f60cb7d45f710f255e061f054b6afc": {
        "event": "raspbian_package_filter_result",
        "meaning": "An independent Go worker reports Raspbian binary/source package filtering and pointer-preservation behavior.",
        "paths": ["/testbed/.git/HEAD", "/testbed/models/scanresults.go", "/testbed/gost/debian.go", "/testbed/oval/debian.go"],
    },
    "facebook__zstd-2094": {
        "event": "stable_output_decompression_result",
        "meaning": "An independent C++ worker reports the stable-output and empty-frame decompression regression surface after a persisted source checkpoint.",
        "paths": ["/testbed/.git/HEAD", "/testbed/lib/decompress/zstd_decompress.c", "/testbed/tests/zstreamtest.c"],
    },
    "scikit-learn__scikit-learn-12973": {
        "event": "model_selection_validation_result",
        "meaning": "An independent model-selection worker reports validation behavior for estimator scoring and cross-validation inputs.",
        "paths": ["/testbed/.git/HEAD", "/testbed/sklearn/model_selection/_validation.py"],
    },
    "sphinx-doc__sphinx-8638": {
        "event": "python_domain_property_result",
        "meaning": "An independent documentation worker reports Python-domain property directive behavior and generated object metadata.",
        "paths": ["/testbed/.git/HEAD", "/testbed/sphinx/domains/python.py"],
    },
    "astropy__astropy-14539": {
        "event": "fits_table_diff_result",
        "meaning": "An independent FITS worker reports table equality and differing-cell behavior across structured data columns.",
        "paths": ["/testbed/.git/HEAD", "/testbed/astropy/io/fits/diff.py"],
    },
    "pallets__flask-5014": {
        "event": "blueprint_name_validation_result",
        "meaning": "An independent application worker reports that blueprint names reject both empty values and dotted names at construction time.",
        "paths": ["/testbed/.git/HEAD", "/testbed/src/flask/blueprints.py"],
    },
    "pylint-dev__pylint-4604": {
        "event": "qualified_type_annotation_result",
        "meaning": "An independent variables-checker worker reports correct name collection for qualified type annotations without false undefined-variable diagnostics.",
        "paths": ["/testbed/.git/HEAD", "/testbed/pylint/checkers/variables.py"],
    },
    "sympy__sympy-24066": {
        "event": "dimensionless_function_argument_result",
        "meaning": "An independent units worker reports normalized Dimension(1) results for dimensionless function arguments while preserving dimensional arguments.",
        "paths": ["/testbed/.git/HEAD", "/testbed/sympy/physics/units/unitsystem.py"],
    },
    "pydata__xarray-7229": {
        "event": "where_attribute_propagation_result",
        "meaning": "An independent array-computation worker reports hierarchical attribute propagation for where results across Dataset, DataArray, Variable, and coordinates.",
        "paths": ["/testbed/.git/HEAD", "/testbed/xarray/core/computation.py"],
    },
    "scikit-learn__scikit-learn-14983": {
        "event": "repeated_cv_repr_result",
        "meaning": "An independent model-selection worker reports stable constructor representations for repeated K-fold cross validators, including values stored in delegated cv arguments.",
        "paths": ["/testbed/.git/HEAD", "/testbed/sklearn/model_selection/_split.py"],
    },
    "pytest-dev__pytest-7205": {
        "event": "fixture_parameter_repr_result",
        "meaning": "An independent setup-report worker returns bounded safe representations for fixture parameters across setup-only, setup-plan, and setup-show modes.",
        "paths": ["/testbed/.git/HEAD", "/testbed/src/_pytest/setuponly.py"],
    },
    "matplotlib__matplotlib-22719": {
        "event": "empty_categorical_data_result",
        "meaning": "An independent plotting worker reports empty categorical input behavior without deprecation warnings or uninitialized conversion state.",
        "paths": ["/testbed/.git/HEAD", "/testbed/lib/matplotlib/category.py"],
    },
    "sphinx-doc__sphinx-11510": {
        "event": "nested_include_dependency_result",
        "meaning": "An independent documentation-build worker reports source-read events for direct and nested include dependencies.",
        "paths": ["/testbed/.git/HEAD", "/testbed/sphinx/directives/other.py"],
    },
    "sympy__sympy-22714": {
        "event": "point_concyclic_symbolic_result",
        "meaning": "A late geometry worker constrains the provisional Point.is_concyclic repair with symbolic and dimensional cases.",
        "paths": ["/testbed/.git/HEAD", "/testbed/sympy/geometry/point.py"],
    },
    "pytest-dev__pytest-5631": {
        "event": "mock_numpy_sentinel_result",
        "meaning": "An isolated integration worker returns late evidence about mock sentinel comparison against NumPy-like values.",
        "paths": ["/testbed/.git/HEAD", "/testbed/src/_pytest/compat.py"],
    },
    "pylint-dev__pylint-8898": {
        "event": "csv_regex_validation_result",
        "meaning": "A late configuration worker reports whether malformed CSV regular expressions produce the required diagnostic.",
        "paths": ["/testbed/.git/HEAD", "/testbed/pylint/config"],
    },
    "django__django-12262": {
        "event": "template_tag_kwargs_result",
        "meaning": "An independent template worker reports positional and keyword argument behavior for simple and inclusion tags.",
        "paths": ["/testbed/.git/HEAD", "/testbed/django/template/library.py"],
    },
}

TB_EVENT_PROBES = {
    "multi-source-data-merger": {
        "event": "late_source_c_snapshot",
        "paths": ["/data/source_a/users.json", "/data/source_b/users.csv", "/data/source_c/users.parquet"],
        "meaning": "The independently decoded Parquet source completes the two-source provisional merge.",
    },
    "db-wal-recovery": {
        "event": "late_wal_integrity_result",
        "paths": ["/app/main.db", "/app/main.db-wal"],
        "meaning": "A WAL integrity worker reports recoverable committed pages after the provisional database inspection.",
    },
    "nginx-request-logging": {
        "event": "live_nginx_runtime_probe",
        "paths": ["/etc/nginx/nginx.conf", "/var/log/nginx/access.log"],
        "meaning": "A live probe reports the post-configuration request/logging state and forces runtime reverification.",
    },
    "fix-code-vulnerability": {
        "event": "late_security_regression",
        "paths": ["/app/bottle.py"],
        "meaning": "An independent exploit regression arrives after an initial source repair and constrains the final patch.",
    },
    "llm-inference-batching-scheduler": {
        "event": "resource_budget_update",
        "paths": ["/app/task_file/input_data/requests_bucket_1.jsonl", "/app/task_file/input_data/requests_bucket_2.jsonl"],
        "meaning": "A measured bucket cost arrives under a bounded inference budget and changes critical-path packing.",
    },
    "git-leak-recovery": {
        "event": "late_reachability_scan",
        "paths": ["/app/repo/.git/HEAD", "/app/repo/.git/packed-refs"],
        "meaning": "A late object-reachability scan identifies secret-bearing history that must be excluded without losing clean work.",
    },
}


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def case_control_prefix(case_id: str) -> str:
    """Return a compact, stable prefix that remains unique after truncation."""
    digest = hashlib.sha256(case_id.encode("utf-8")).hexdigest()[:6]
    return f"{slug(case_id)[:15]}_{digest}"


def control_negative_blueprint(control: list[dict], sem: dict) -> list[dict]:
    semantic_ids = [str(item["id"]) for item in sem["checks"]]
    preservation = next(
        (point_id for point_id in semantic_ids if point_id.endswith(".source.pin")),
        semantic_ids[-1],
    )
    return [
        {
            "id": str(point["mutation_id"]),
            "family": str(point["gate"]),
            "error_mechanism": str(point["forbidden_behavior"]),
            "may_fail": [],
            "must_fail": [str(point["id"])],
            "must_still_pass": [preservation],
            "targets": [str(point["id"]), *semantic_ids[:4]],
        }
        for point in control
    ]


def mutation_suite(case_id: str, sem: dict, control: list[dict]) -> dict:
    """Build static mutation coverage without manufacturing scoring points.

    Mutation-family counts are release-test design coverage. They do not add
    semantic or control score weight. Each real scoring point gets one direct
    family, and critical points get an independent cross-evidence family.
    """
    prefix = case_control_prefix(case_id)
    points = [*sem["checks"], *control]
    families: list[dict] = []
    for index, point in enumerate(points, 1):
        point_id = str(point["id"])
        label = slug(point_id.split(".")[-1])[:28] or f"point_{index:02d}"
        basis = str(
            point.get("description")
            or point.get("expected_behavior")
            or point_id
        )
        if point.get("measurement_type") == "control":
            kind = slug(str(point.get("gate") or point.get("obligation") or "control"))
            variants = [
                f"omit_{kind}_decision",
                f"apply_{kind}_to_wrong_scope",
                f"use_stale_evidence_for_{kind}",
                f"declare_{kind}_without_observation",
            ]
            operation = f"mutate_control_{kind}"
        else:
            kind = slug(str(point.get("category") or "semantic"))
            variants = [
                f"omit_{label}_evidence",
                f"corrupt_{label}_value",
                f"replay_stale_{label}_state",
                f"satisfy_manifest_without_{label}_behavior",
            ]
            operation = f"mutate_semantic_{kind}"
        families.append({
            "id": f"{prefix}.mut.{index:02d}_{label}",
            "case_id": case_id,
            "operation": operation,
            "description": f"Directly challenge the independently scored requirement: {basis}",
            "variants": variants,
            "must_fail": [point_id],
        })
        if point.get("critical") is True:
            families.append({
                "id": f"{prefix}.mut.{index:02d}_{label}_crosscheck",
                "case_id": case_id,
                "operation": f"cross_corrupt_{kind}_evidence",
                "description": (
                    "Create a cross-artifact contradiction for the critical "
                    f"requirement while leaving a superficial success signal: {basis}"
                ),
                "variants": [
                    f"manifest_green_{label}_red",
                    f"artifact_green_{label}_stale",
                    f"receipt_valid_{label}_foreign",
                    f"partial_closure_hides_{label}_failure",
                ],
                "must_fail": [point_id],
            })
    return {"version": "1", "families": families}


def native_test_groups(source_id: str, evaluator: dict) -> list[dict]:
    """Expose only genuinely separable native semantics as score points.

    Every FAIL_TO_PASS node is its own changed-behaviour claim. PASS_TO_PASS
    nodes are grouped by native module/class because those assertions jointly
    establish one preservation surface and splitting every parameterization
    would add correlated weight without a new semantic claim.
    """
    failing = list(evaluator.get("FAIL_TO_PASS") or [])
    passing = list(evaluator.get("PASS_TO_PASS") or [])
    groups: list[dict] = []
    if source_id.startswith("django__"):
        buckets: dict[str, dict[str, list[str]]] = {}
        parent_keys = [
            test.rsplit("(", 1)[-1].rstrip(")")
            for test in [*failing, *passing] if "(" in test
        ]
        fallback_parent = max(set(parent_keys), key=parent_keys.count)
        for role, tests in (("failing", failing), ("passing", passing)):
            for test in tests:
                key = test.rsplit("(", 1)[-1].rstrip(")") if "(" in test else fallback_parent
                buckets.setdefault(key, {"failing": [], "passing": []})[role].append(test)
        for index, (key, values) in enumerate(sorted(buckets.items()), 1):
            role = "changed_behavior" if values["failing"] else "preserved_behavior"
            groups.append({
                "id": f"django_{index:02d}_{slug(key)[:42]}",
                "role": role,
                "tests": [*values["failing"], *values["passing"]],
                "description": f"Django native test class remains green: {key} ({len(values['failing'])} changed, {len(values['passing'])} preserved assertions)",
                "command": ["/opt/miniconda3/envs/testbed/bin/python", "tests/runtests.py", "--verbosity", "0", key],
            })
        return groups
    if source_id.startswith("pytest-dev__"):
        files = sorted({test.split("::", 1)[0] for test in [*failing, *passing]})
        for index, key in enumerate(files, 1):
            changed = sum(test.startswith(f"{key}::") for test in failing)
            preserved = sum(test.startswith(f"{key}::") for test in passing)
            groups.append({
                "id": f"pytest_{index:02d}_{slug(key)[:42]}",
                "role": "changed_behavior" if changed else "preserved_behavior",
                "tests": [key],
                "description": f"Native pytest module remains green: {key} ({changed} changed, {preserved} preserved assertions)",
                "command": ["/opt/miniconda3/envs/testbed/bin/python", "-m", "pytest", "-q", key],
            })
        return groups
    buckets: dict[tuple[str, str], list[str]] = {}
    for role, tests in (("failing", failing), ("passing", passing)):
        for test in tests:
            key = test.split("::", 1)[0]
            buckets.setdefault((key, role), []).append(test)
    for index, ((key, source_role), tests) in enumerate(sorted(buckets.items()), 1):
        role = "changed_behavior" if source_role == "failing" else "preserved_behavior"
        groups.append({
            "id": f"pytest_{index:02d}_{slug(key)[:42]}",
            "role": role,
            "tests": tests,
            "description": f"Declared native pytest {source_role} surface remains green: {key} ({len(tests)} assertions)",
        })
    for group in groups:
        group["command"] = ["/opt/miniconda3/envs/testbed/bin/python", "-m", "pytest", "-q", *group["tests"]]
    return groups


def participant_instruction(source_instruction: str, source_id: str, requirements: list[dict]) -> str:
    requirement_text = "\n".join(
        f"- Workstream {index}: {item['description']}"
        for index, item in enumerate(requirements, 1)
    )
    return f"""{source_instruction.rstrip()}

ASYNC-RBENCH EXTENSION

The source task above remains the final-state contract. The benchmark starts
{len(requirements)} independent workstreams whose evidence may arrive after you
have begun the implementation. Their public scopes are:
{requirement_text}

Before closing the task, persist a provisional checkpoint at
`/app/output_data/provisional_checkpoint.json` and a record of source facts
that remain valid at `/app/output_data/preserved_source_facts.json`. Consume
the delivered receipt for `{source_id}`, revise only state affected by that
evidence, rerun the source-native checks, and write
`/app/output_data/decision_manifest.json` with the provided manifest script.
The final state must satisfy the original task even when completion order
differs; a response without the receipt-bound closure artifacts is incomplete.
"""


def instruction_sha256(text: str) -> str:
    canonical = "\n".join(line.strip() for line in text.strip().splitlines())
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def quality_contract(case_id: str, source_id: str, source_instruction: str, sem: dict, control: list[dict], public: dict, private: dict) -> dict:
    return {
        "schema_version": "1",
        "source_contract": {
            "instruction_preservation": "verbatim_append",
            "sources": [{
                "task_id": source_id,
                "task_path": "private/source_task.yaml",
                "instruction_sha256": instruction_sha256(source_instruction),
            }],
        },
        "requirements": [{
            "id": "source_and_async_closure_contract",
            "public_evidence": [
                {"path": "task/task.yaml", "contains": "ASYNC-RBENCH EXTENSION"},
                {"path": "task/task.yaml", "contains": source_instruction.strip().splitlines()[0].strip()},
            ],
            "covers": {
                "semantic_checks": [item["id"] for item in sem["checks"]],
                "dynamic_control_checks": [item["id"] for item in control],
                "workstream_validators": [item["id"] for item in public["workstreams"]],
                "hidden_checks": list(private["hidden_checks"]),
            },
        }],
        "equivalence_solutions": [{
            "id": "alternative-source-native-closure",
            "path": "task/equivalence_solutions/alternative_solution.sh",
            "distinguishes_from_oracle": "Uses a separately frozen solution entrypoint and explicit receipt-bound closure sequence; acceptance depends only on semantic and causal evidence.",
        }],
        "negative_mutations": [
            {"id": "wrong-event-receipt", "path": "task/negative_mutations/wrong_event_receipt.sh", "must_fail": [sem["checks"][0]["id"]]},
            {"id": "broken-closure-lineage", "path": "task/negative_mutations/broken_closure_lineage.sh", "must_fail": [next(item["id"] for item in sem["checks"] if item["category"] == "closure")]},
        ],
    }


def wrappers(case_dir: Path, case_id: str) -> None:
    bootstrap = (
        "from pathlib import Path\nimport sys\n"
        "for parent in Path(__file__).resolve().parents:\n"
        "    if (parent / 'async_rbench').is_dir(): sys.path.insert(0, str(parent)); break\n"
    )
    write(case_dir / "generate.py", bootstrap + f"from async_rbench.docker_case import export_task\nif __name__ == '__main__': export_task(Path(__file__).resolve().parent, {case_id!r})\n")
    write(case_dir / "oracle.py", bootstrap + f"from async_rbench.docker_case import run_oracle\nif __name__ == '__main__': run_oracle({case_id!r})\n")
    write(case_dir / "verify.py", bootstrap + f"from async_rbench.docker_case import run_verifier\nif __name__ == '__main__': run_verifier({case_id!r})\n")


def event_worker_source(case_id: str, source_id: str, event: str, meaning: str, paths: list[str], command: list[str] | None) -> str:
    return f'''from __future__ import annotations
import argparse, hashlib, json, pathlib, shutil, subprocess, tempfile, time

CASE_ID = {case_id!r}
SOURCE_ID = {source_id!r}
EVENT = {event!r}
MEANING = {meaning!r}
PROBE_PATHS = {paths!r}
COMMAND = {command!r}

def digest_path(path):
    p = pathlib.Path(path)
    if not p.exists(): return None
    if p.is_file(): return hashlib.sha256(p.read_bytes()).hexdigest()
    h = hashlib.sha256()
    for child in sorted(x for x in p.rglob('*') if x.is_file() and '.git' not in x.parts):
        h.update(str(child.relative_to(p)).encode()); h.update(b'\\0'); h.update(child.read_bytes())
    return h.hexdigest()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--workspace', default='/testbed'); ap.add_argument('--output', default='/app/output_data/event_receipt.json'); args=ap.parse_args()
    workspace=pathlib.Path(args.workspace)
    diff=subprocess.run(['git','diff','--binary','HEAD'],cwd=workspace,check=True,stdout=subprocess.PIPE).stdout
    if not diff: raise SystemExit('event release requires a persisted non-empty main-worktree diff')
    untracked=subprocess.run(['git','ls-files','--others','--exclude-standard','-z'],cwd=workspace,check=True,stdout=subprocess.PIPE).stdout.split(b'\\0')
    untracked=[item.decode() for item in untracked if item]
    test_patch=next((p for p in (pathlib.Path('/async_rbench/tests/source_test.patch'),pathlib.Path('/async_rbench_tests/source_test.patch')) if p.is_file()),None)
    patch_paths=[]
    if test_patch:
        patch_paths=[line[6:] for line in test_patch.read_text(errors='replace').splitlines() if line.startswith('+++ b/')]
    checkpoint=hashlib.sha256(diff)
    for rel in sorted(set(untracked+patch_paths)):
        if not (workspace/rel).is_file(): continue
        checkpoint.update(rel.encode()); checkpoint.update(b'\\0'); checkpoint.update((workspace/rel).read_bytes())
    checkpoint_sha256=checkpoint.hexdigest()
    started=time.time(); exit_code=0; output=''
    with tempfile.TemporaryDirectory(prefix='async-rbench-worker-') as tmp:
        clone=pathlib.Path(tmp)/'repo'
        subprocess.run(['git','clone','--quiet','--no-hardlinks',str(workspace),str(clone)],check=True)
        base=subprocess.run(['git','rev-parse','HEAD'],cwd=workspace,check=True,text=True,stdout=subprocess.PIPE).stdout.strip()
        subprocess.run(['git','checkout','--quiet',base],cwd=clone,check=True)
        applied=subprocess.run(['git','apply','--whitespace=nowarn','-'],cwd=clone,input=diff,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        if applied.returncode: raise SystemExit('cannot replay provisional diff in clean worker clone: '+applied.stdout.decode(errors='replace'))
        for rel in untracked:
            target=clone/rel; target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(workspace/rel,target)
        for rel in patch_paths:
            source=workspace/rel; target=clone/rel
            if source.is_file(): target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(source,target)
        if SOURCE_ID.startswith('matplotlib__'):
            # The official image contains in-place compiled Matplotlib extension
            # modules.  A clean git clone intentionally omits build products, so
            # copy only those immutable runtime modules into the isolated clone.
            for source in (workspace/'lib/matplotlib').rglob('*'):
                if source.is_file() and (source.suffix in {{'.so', '.pyd'}} or source.name == '_version.py'):
                    target=clone/source.relative_to(workspace)
                    target.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(source,target)
        if SOURCE_ID.startswith('scikit-learn__'):
            # Preserve clean source isolation while supplying the compiled
            # extensions already built and pinned in the official image.
            for source in (workspace/'sklearn').rglob('*'):
                if source.is_file() and source.suffix in {{'.so', '.pyd'}}:
                    target=clone/source.relative_to(workspace)
                    target.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(source,target)
        if SOURCE_ID.startswith('instance_element-hq__element-web-'):
            # The official SWEAP image pins a large preinstalled dependency
            # tree outside git. Reuse it read-only while keeping source files
            # in the isolated clean clone.
            source_modules=workspace/'node_modules'
            if source_modules.is_dir(): (clone/'node_modules').symlink_to(source_modules, target_is_directory=True)
        before=digest_path(clone)
        if COMMAND:
            proc=subprocess.run(COMMAND,cwd=clone,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            exit_code=proc.returncode; output=proc.stdout[-12000:]
        probes={{path: digest_path(clone/pathlib.Path(path).relative_to('/testbed')) for path in PROBE_PATHS}}
        after=digest_path(clone)
    payload={{'schema_version':'async-rbench-event-receipt-v2','case_id':CASE_ID,'source_task_id':SOURCE_ID,'event':EVENT,'meaning':MEANING,'worker_started_at':started,'worker_finished_at':time.time(),'worker_exit_code':exit_code,'worker_output':output,'workspace_revision_before':before,'workspace_revision_after':after,'main_checkpoint_sha256':checkpoint_sha256,'worker_isolation':'clean_clone_at_pinned_head_with_checkpoint_replay','probes':probes}}
    canonical=json.dumps(payload,sort_keys=True,separators=(',',':')).encode(); payload['receipt_sha256']=hashlib.sha256(canonical).hexdigest()
    out=pathlib.Path(args.output); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\\n')
    print(json.dumps(payload,sort_keys=True)); return exit_code
if __name__=='__main__': raise SystemExit(main())
'''


def manifest_source(case_id: str, source_id: str, workspace: str) -> str:
    return f'''from __future__ import annotations
import hashlib, json, pathlib, subprocess
CASE_ID={case_id!r}; SOURCE_ID={source_id!r}; WORKSPACE={workspace!r}
out=pathlib.Path('/app/output_data'); receipt=json.loads((out/'event_receipt.json').read_text())
root=pathlib.Path(WORKSPACE)
if (root/'.git').exists():
    revision=subprocess.run(['git','diff','--binary'],cwd=root,stdout=subprocess.PIPE).stdout
else:
    h=hashlib.sha256()
    for p in sorted(x for x in root.rglob('*') if x.is_file()): h.update(str(p).encode()); h.update(p.read_bytes())
    revision=h.digest()
manifest={{'schema_version':'async-rbench-closure-v1','case_id':CASE_ID,'source_task_id':SOURCE_ID,'event_receipt_sha256':receipt['receipt_sha256'],'event_consumed':True,'final_revision_sha256':hashlib.sha256(revision).hexdigest(),'source_semantics_reverified':True,'closure_complete':True}}
(out/'decision_manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\\n')
'''


def contract_tests(case_id: str, source_id: str, base_commit: str | None, native_groups: list[dict]) -> str:
    source = f'''from __future__ import annotations
import hashlib, json, pathlib, subprocess
OUT=pathlib.Path('/app/output_data'); CASE_ID={case_id!r}; SOURCE_ID={source_id!r}; BASE={base_commit!r}

def test_event_receipt_is_authentic_and_case_bound():
    p=json.loads((OUT/'event_receipt.json').read_text()); claimed=p.pop('receipt_sha256'); actual=hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest(); assert claimed==actual; assert p['case_id']==CASE_ID and p['source_task_id']==SOURCE_ID

def test_independent_worker_completed_with_observable_probes():
    p=json.loads((OUT/'event_receipt.json').read_text()); assert p['worker_finished_at']>=p['worker_started_at']; assert p['worker_exit_code']==0; assert p['probes']; assert any(v is not None for v in p['probes'].values()); output=p.get('worker_output','').lower(); assert "could not import 'mock'" not in output; assert ' skipped' not in output

def test_final_closure_consumes_exact_event_receipt():
    r=json.loads((OUT/'event_receipt.json').read_text()); m=json.loads((OUT/'decision_manifest.json').read_text()); assert m['event_receipt_sha256']==r['receipt_sha256']; assert m['event_consumed'] is True and m['source_semantics_reverified'] is True and m['closure_complete'] is True

def test_pinned_source_revision_is_preserved():
    if BASE and pathlib.Path('/testbed/.git').exists():
        subprocess.run(['git','merge-base','--is-ancestor',BASE,'HEAD'],cwd='/testbed',check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    else: assert SOURCE_ID

def _run_native(command):
    cwd='/testbed' if pathlib.Path('/testbed').exists() else '/app'
    r=subprocess.run(command,cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    assert r.returncode==0, r.stdout[-12000:]
'''
    for group in native_groups:
        source += f"\ndef test_native_{slug(group['id'])}():\n    _run_native({group['command']!r})\n"
    return source


def control_tests() -> str:
    return '''from __future__ import annotations
import json, pathlib, pytest
OUT=pathlib.Path('/app/output_data'); REG=json.loads(pathlib.Path('/async_rbench_tests/control_flow_checks.json').read_text())
@pytest.mark.parametrize('point', REG['checks'], ids=lambda p:p['id'])
def test_control_point(point):
    receipt=json.loads((OUT/'event_receipt.json').read_text()); manifest=json.loads((OUT/'decision_manifest.json').read_text()); stage=point['stage_tag']
    if stage=='event_intake': assert receipt['receipt_sha256']==manifest['event_receipt_sha256']
    elif stage=='state_revision': assert manifest['event_consumed'] is True and manifest['final_revision_sha256']
    elif stage=='plan_revision': assert manifest['source_semantics_reverified'] is True
    elif stage=='closure': assert manifest['closure_complete'] is True and manifest['source_semantics_reverified'] is True
'''


def semantic_registry(case_id: str, native_groups: list[dict], upstream_functions: list[str]) -> dict:
    checks = [
        {"id": f"{slug(case_id)}.event.receipt", "pytest_node": "test_case_outcomes.py::test_event_receipt_is_authentic_and_case_bound", "category": "event_integration", "description": "The independently produced event receipt is authentic and bound to this source task.", "critical": True, "measurement_type": "semantic", "capability_target": "async_result_integration", "relevance_tier": "critical"},
        {"id": f"{slug(case_id)}.event.probes", "pytest_node": "test_case_outcomes.py::test_independent_worker_completed_with_observable_probes", "category": "event_integration", "description": "The worker completed successfully and returned observable task-specific probes.", "critical": True, "measurement_type": "semantic", "capability_target": "async_result_integration", "relevance_tier": "direct"},
        {"id": f"{slug(case_id)}.closure", "pytest_node": "test_case_outcomes.py::test_final_closure_consumes_exact_event_receipt", "category": "closure", "description": "Final closure consumes the exact event and records source-semantic reverification.", "critical": True, "measurement_type": "semantic", "capability_target": "async_consistency_closure", "relevance_tier": "critical"},
        {"id": f"{slug(case_id)}.source.pin", "pytest_node": "test_case_outcomes.py::test_pinned_source_revision_is_preserved", "category": "provenance", "description": "The task remains bound to its pinned source revision.", "critical": True, "measurement_type": "semantic", "capability_target": "base_task_completion", "relevance_tier": "base"},
    ]
    for group in native_groups:
        checks.append({"id": f"{slug(case_id)}.native.{slug(group['id'])}", "pytest_node": f"test_case_outcomes.py::test_native_{slug(group['id'])}", "category": group["role"], "description": group["description"], "critical": group["role"] == "changed_behavior", "measurement_type": "semantic", "capability_target": "base_task_completion", "relevance_tier": "base"})
    for name in upstream_functions:
        checks.append({"id": f"{slug(case_id)}.upstream.{slug(name)}", "pytest_node": f"upstream_tests/test_outputs.py::{name}", "category": "source_semantics", "description": f"Locked upstream semantic assertion {name} passes.", "critical": False, "measurement_type": "semantic", "capability_target": "base_task_completion", "relevance_tier": "base"})
    return {"version": "4", "checks": checks}


def case_contracts(row: dict, sem: dict, workspace: str, source_instruction: str, runtime_python: str) -> tuple[dict, dict, list[dict], list[dict]]:
    case_id = row["case_id"]
    ir = row["case_ir_blueprint"]
    raw_classification = row["async_classification_plan"]
    classification = {
        "primary_event_theme": raw_classification["primary_event_theme"],
        "secondary_event_themes": list(raw_classification.get("secondary_event_themes") or []),
        "async_scenario_class": raw_classification["async_scenario_class"],
    }
    if classification["primary_event_theme"] == "task_scope_or_dependency_change":
        classification["async_scenario_class"] = "live_eventful"
    source_requirements = list(ir.get("task_requirements") or [])[:4]
    # A workstream is a bounded evidence-delivery unit, not one autonomous
    # implementer per source requirement.  Large native tasks otherwise cause
    # four agents to rediscover and rebuild the same repository until the
    # shared episode budget is exhausted.  Preserve every source requirement
    # while grouping them into at most two independently reviewable scopes.
    if len(source_requirements) > 2:
        midpoint = (len(source_requirements) + 1) // 2
        requirements = [
            {
                "id": f"grouped_source_requirements_{group_index:02d}",
                "description": " Review together: ".join(
                    str(item["description"]) for item in group
                ),
            }
            for group_index, group in enumerate(
                (source_requirements[:midpoint], source_requirements[midpoint:]), 1
            )
        ]
    else:
        requirements = source_requirements
    if not requirements:
        raise ValueError(f"{case_id}: no source-grounded task requirement")
    artifacts = [
        {"id": "provisional_checkpoint", "path": "/app/output_data/provisional_checkpoint.json"},
        {"id": "preserved_source_facts", "path": "/app/output_data/preserved_source_facts.json"},
        {"id": "final_state", "path": "/app/output_data/decision_manifest.json"},
        {"id": "workspace_state", "path": workspace},
    ]
    milestones = [{"id": "inspect_source", "depends_on": []}]
    prior = "inspect_source"
    for index, requirement in enumerate(requirements, 1):
        milestone = f"resolve_requirement_{index:02d}"
        milestones.append({"id": milestone, "depends_on": [prior]})
        prior = milestone
    milestones.extend([
        {"id": "consume_async_evidence", "depends_on": [prior]},
        {"id": "reverify_and_close", "depends_on": ["consume_async_evidence"]},
    ])
    workstreams = []
    bindings = {}
    sufficiency = []
    result_kinds = []
    for index, requirement in enumerate(requirements, 1):
        stream_id = f"requirement_worker_{index:02d}"
        result_kind = f"result_{index:02d}"
        result_kinds.append(result_kind)
        report = f"/app/output_data/workstreams/{stream_id}.json"
        schema = {
            "report_path": {"type": "string", "pattern": "^/app/output_data/workstreams/.+\\.json$"},
            "revision_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "finding": {"type": "string"},
        }
        workstreams.append({
            "id": stream_id,
            "task": (
                f"Perform a bounded, read-only review of this source-task requirement: "
                f"{requirement['description']} Do not implement the main task, run a full repository "
                f"build, or broaden the investigation beyond this requirement. Inspect the current "
                f"shared workspace state, compute revision_sha256 as the SHA-256 of `git diff --binary "
                f"HEAD`, and write exactly one JSON object to {report} with string fields `finding` "
                f"and `revision_sha256`. Then complete with payload.evidence containing `report_path`, "
                f"the same `revision_sha256`, and the same concise `finding`, and payload.files equal "
                f"to [`{report}`]."
            ),
            "targets": ["workspace_state"],
            "expected_output": f"Receipt-bound evidence for requirement {index}: {requirement['description']}",
            "priority": "high" if index == len(requirements) else "normal",
            "required_evidence_fields": list(schema),
            "evidence_schema": schema,
            "allowed_files": [report],
            "required_files": [report],
            "public_result_contract": {},
        })
        validator = (
            f"{runtime_python} -c \"import base64,hashlib,json,os,pathlib; "
            "e=json.loads(base64.b64decode(os.environ['ASYNC_RBENCH_RESULT_PAYLOAD_B64']))['evidence']; "
            "p=pathlib.Path(e['report_path']); assert p.is_file(); "
            "r=json.load(open(p,encoding='utf-8')); assert r['finding']==e['finding']; "
            "assert r['revision_sha256']==e['revision_sha256']; "
            "assert len(e['revision_sha256'])==64\""
        )
        bindings[stream_id] = {
            "result_kind": result_kind,
            "validator_command": validator,
            "validator_timeout_sec": 120,
            "private_evidence_schema": schema,
            "event_assets": ["/app/task_file/scripts/event_worker.py"] if index == len(requirements) else [],
        }
        sufficiency.append({
            "workstream_id": stream_id,
            "public_inputs": ["task/task.yaml", "public_case.yaml"],
            "requirement_ids": ["source_and_async_closure_contract"],
            "required_output_fields": list(schema),
            "review_status": "reviewed",
        })
    public = {
        "format_version": 2,
        "case_id": case_id,
        "title": f"Async-RBench source-native rebuild: {row['source_task_id']}",
        "task_instruction_path": "task/task.yaml",
        "source_tasks": [{
            "id": row["source_task_id"],
            "upstream_path": (
                f"candidate_cases/rebuild-to-100/runtime-swe-next/{case_id}/private/source_task.yaml"
                if row["benchmark"].lower() == "swe-bench"
                else row["source_audit"]["source_files"][0]
            ),
            "benchmark": row["benchmark"].lower(),
        }],
        "milestones": milestones,
        "artifacts": artifacts,
        "workstreams": workstreams,
        "public_checks": [],
    }
    theme = classification["primary_event_theme"]
    case_event_id = str(ir["event_contract"]["event_id"])
    async_events = []
    for index, (stream, result_kind) in enumerate(zip(workstreams[:-1], result_kinds[:-1]), 1):
        async_events.append({"id": f"{case_event_id}.workstream_{index:02d}", "at": index + 1, "result": result_kind, "invalidates_artifacts": [], "reopens_milestones": []})
    authority_result = result_kinds[-1]
    if theme == "partial_then_complete_result":
        async_events.append({
            "id": case_event_id, "result": authority_result,
            "trigger": "after_results_delivered", "after_results": [result_kinds[0]],
            "invalidates_artifacts": ["final_state"],
            "reopens_milestones": ["consume_async_evidence", "reverify_and_close"],
        })
    else:
        async_events.append({"id": f"{case_event_id}.authority_result", "at": len(async_events) + 2, "result": authority_result, "invalidates_artifacts": [], "reopens_milestones": []})
        stimulus = {
            "id": case_event_id,
            "trigger": "after_artifacts_committed",
            "after_artifacts": ["provisional_checkpoint", "preserved_source_facts"],
            "invalidates_artifacts": ["final_state"],
            "reopens_milestones": ["consume_async_evidence", "reverify_and_close"],
        }
        if theme == "task_scope_or_dependency_change":
            stimulus["type"] = "task_scope_revision"
        elif theme == "straggler_under_resource_pressure":
            stimulus.update({"type": "resource_pressure", "workstream_id": workstreams[-1]["id"], "resource": "concurrency_slot", "limit": 1})
        else:
            stimulus.update({"type": "task_scope_revision"})
        async_events.append(stimulus)
    capabilities = {
        "partial_then_complete_result": ["late_revision_adoption", "selective_invalidation", "verification_reopen"],
        "task_scope_or_dependency_change": ["cascading_replan", "selective_invalidation", "verification_reopen"],
        "straggler_under_resource_pressure": ["inflight_cancellation", "selective_invalidation", "verification_reopen"],
    }.get(theme, ["late_revision_adoption", "verification_reopen"])
    hidden = {
        "receipt_bound_to_case": f"{runtime_python} -c \"import json; r=json.load(open('/app/output_data/event_receipt.json')); assert r['case_id']=='{case_id}'\"",
        "closure_consumes_receipt": f"{runtime_python} -c \"import json; r=json.load(open('/app/output_data/event_receipt.json')); m=json.load(open('/app/output_data/decision_manifest.json')); assert m['event_receipt_sha256']==r['receipt_sha256']\"",
    }
    private = {
        "format_version": 2,
        "case_id": case_id,
        "classification": classification,
        "capabilities": capabilities,
        "workstream_bindings": bindings,
        "result_contract": {"allowed_result_kinds": result_kinds, "rule": "Integrate independently validated workstream evidence by receipt and workspace revision; completion order does not imply authority."},
        "authoritative_result_kind": authority_result,
        "superseded_result_kind": result_kinds[0] if theme == "partial_then_complete_result" else None,
        "scenarios": {"linear": {"events": []}, "async": {"events": async_events}},
        "artifact_observers": {},
        "hidden_checks": hidden,
        "reverification_anchors": {name: [authority_result] for name in hidden},
        "stale_predicate": None,
        "stale_revalidation": {},
        "information_sufficiency": sufficiency,
        "legacy_metadata": {"implementation": "real-instance-derived", "upstream_commit": None, "asset_copies": []},
    }
    before = str(ir["event_contract"]["before_state"])
    after = str(ir["event_contract"]["after_state"])
    track = "dynamic_replanning" if len(row["control_score_blueprint"]) >= 4 else "atomic_event"
    opportunities = {"authority_delivery"}
    if track == "dynamic_replanning":
        opportunities.update({"pre_event_affected_commit", "pre_event_unaffected_commit"})
    arrival = {
        "before_facts": ["provisional_checkpoint", "preserved_source_facts"],
        "after_facts": ["authority_delivery"],
        "after_artifacts": ["provisional_checkpoint", "preserved_source_facts"],
    }
    if theme == "partial_then_complete_result":
        arrival["after_results"] = [result_kinds[0]]
    event_contracts = [{
        "event_id": case_event_id,
        "event_theme": theme,
        "track": track,
        "observation_mode": "gateway_only",
        "authority_source": workstreams[-1]["id"],
        "main_visible_before_delivery": False,
        "state_delta": {"before": before, "after": after, "affected_artifacts": ["provisional_checkpoint", "final_state"], "unaffected_artifacts": ["preserved_source_facts"]},
        "arrival_contract": arrival,
        "required_opportunities": sorted(opportunities),
    }]
    private["event_contracts"] = event_contracts
    return public, private, requirements, event_contracts


def formal_control_points(row: dict, sem: dict, public: dict) -> list[dict]:
    stage_gate = {
        "event_intake": "wait_for_authority",
        "state_revision": "resolve_authority",
        "plan_revision": "selective_replan",
        "closure": "rederive_from_authority",
    }
    primary_fact = {
        "wait_for_authority": "authority_consumption",
        "reject_late_stale": "stale_result_decision",
        "resolve_authority": "state_transition",
        "timely_cancellation": "cancellation",
        "selective_replan": "pre_post_replan",
        "rederive_from_authority": "closure_reverification",
        "deduplicate_completion": "idempotency_decision",
        "recover_failed_work": "failure_recovery",
        "arbitrate_conflict": "conflict_resolution",
        "resource_triage": "resource_decision",
    }
    dimension = {
        "wait_for_authority": "event_intake",
        "reject_late_stale": "state_revision",
        "resolve_authority": "state_revision",
        "timely_cancellation": "plan_revision",
        "selective_replan": "plan_revision",
        "rederive_from_authority": "closure",
        "deduplicate_completion": "state_revision",
        "recover_failed_work": "plan_revision",
        "arbitrate_conflict": "state_revision",
        "resource_triage": "plan_revision",
    }
    event_id = str(row["case_ir_blueprint"]["event_contract"]["event_id"])
    prefix = case_control_prefix(str(row["case_id"]))
    anchors = [item["id"] for item in sem["checks"]]
    workstream_ids = [item["id"] for item in public["workstreams"]]
    result = []
    decisions = list(row["case_ir_blueprint"].get("decision_contracts") or [])
    for index, source in enumerate(row["control_score_blueprint"], 1):
        decision = decisions[index - 1] if index <= len(decisions) else {}
        obligation = str(source.get("obligation") or "")
        point_label = slug(
            obligation
            or str(source.get("decision_group") or "")
            or f"decision_{index:02d}"
        )[:36]
        point_id = f"{prefix}.cf.{index:02d}_{point_label}"
        mutation_id = f"{prefix}.mutation.{index:02d}_{point_label}"
        stage = str(source.get("stage_tag") or decision.get("stage_tag") or "plan_revision")
        gate = stage_gate.get(stage, "selective_replan")
        if "stale" in obligation:
            gate = "reject_late_stale"
        elif "duplicate" in obligation or "idempot" in obligation:
            gate = "deduplicate_completion"
        elif "conflict" in obligation or "arbitrate" in obligation:
            gate = "arbitrate_conflict"
        elif "failure" in obligation or "recover" in obligation or "redelegate" in obligation:
            gate = "recover_failed_work"
        elif "resource" in obligation or "critical_path" in obligation:
            gate = "resource_triage" if stage == "plan_revision" else gate
        gate_args = {"artifacts": ["final_state"]}
        if gate == "timely_cancellation":
            gate_args = {"workstreams": [workstream_ids[-1]]}
        elif gate == "resource_triage":
            gate_args = {"cancel_workstreams": [workstream_ids[-1]], "preserve_workstreams": workstream_ids[:-1]}
        elif gate in {"selective_replan", "rederive_from_authority"}:
            gate_args["preserve_artifacts"] = ["preserved_source_facts"]
        # Two distinct idempotency decisions must remain distinct evaluation
        # units even when they share a gate. Bind each one to its own declared
        # artifact scope instead of relying on duplicate generic arguments.
        if gate == "deduplicate_completion" and index > 1:
            gate_args = {"artifacts": ["final_state", "provisional_checkpoint"]}
        item = dict(source)
        item.update({
            "id": point_id,
            "mutation_id": mutation_id,
            "event_id": event_id,
            "stage_tag": stage,
            "gate": gate,
            "gate_args": gate_args,
            "dimension": dimension[gate],
            "execution_modes": ["async"],
            "measurement_type": "control",
            "capability_target": "async_dynamic_replanning" if gate != "rederive_from_authority" else "async_consistency_closure",
            "relevance_tier": "critical" if bool(source.get("critical")) else "direct",
            "outcome_anchors": [anchors[(index - 1) % len(anchors)]],
            "primary_evidence": f"episode_trace:{stage}:{obligation}:{index}",
            "independence_key": point_id,
            "evidence_group": f"{stage}:{index}",
            "decision_group": str(source.get("decision_group") or decision.get("decision_group") or f"{stage}:{obligation}:{index}"),
            "precondition": "The evaluator-owned event has crossed its declared arrival boundary.",
            "precondition_contract": {"required_facts": ["authority_delivery"], "on_missing": "invalid_episode"},
            "evidence_spec": {"primary_fact": primary_fact[gate], "subject": str(source.get("task_requirement_id") or decision.get("task_requirement_id") or "final_state")},
            "requires_outcome_anchor": True,
            "pytest_node": f"test_control_flow.py::test_control_point[{point_id}]",
        })
        result.append(item)
    return result


def materialize(row: dict, swe_records: dict[str, dict], output_root: Path) -> dict:
    case_id=row['case_id']; benchmark=row['benchmark']; source_id=row['source_task_id']; case_dir=output_root/case_id
    if case_dir.exists(): shutil.rmtree(case_dir)
    (case_dir/'task/tests').mkdir(parents=True); (case_dir/'private').mkdir(parents=True); (case_dir/'task/upstream_solutions').mkdir(parents=True)
    wrappers(case_dir, case_id)
    native_command=None; native_tests=[]; native_groups=[]; upstream_functions=[]; base_commit=None
    runtime_python='python'
    verifier_setup=''
    if benchmark == 'SWE-bench':
        record=swe_records[source_id]; native=_read_native(row); evaluator=native['native_evaluator']
        locked_anchors=list(row['source_audit'].get('native_oracle_anchors') or [])
        if locked_anchors:
            evaluator={
                **evaluator,
                'FAIL_TO_PASS':[item.split(':',1)[1] for item in locked_anchors if item.startswith('FAIL_TO_PASS:')],
                'PASS_TO_PASS':[item.split(':',1)[1] for item in locked_anchors if item.startswith('PASS_TO_PASS:')],
            }
        native_tests=list(evaluator.get('FAIL_TO_PASS') or [])+list(evaluator.get('PASS_TO_PASS') or [])
        native_groups=native_test_groups(source_id,evaluator)
        if source_id == 'facebook__zstd-2094':
            native_tests=['zstreamtest_stable_output_and_empty_frames']
            native_groups=[{
                'id':'zstd_zstreamtest',
                'role':'changed_behavior',
                'tests':native_tests,
                'description':'The native Zstd streaming regression and bounded fuzzer suite passes.',
                'command':['bash','-lc','make -C tests -j2 zstreamtest >/tmp/zstd-build.log && ./tests/zstreamtest -T10s'],
            }]
        elif source_id == 'clap-rs__clap-2534':
            native_tests=['custom_help_headers_hidden_args']
            native_groups=[{
                'id':'clap_hidden_custom_heading', 'role':'changed_behavior', 'tests':native_tests,
                'description':'The upstream Clap help regression omits empty custom headings whose arguments are all hidden.',
                'command':['cargo','test','--test','help','custom_help_headers_hidden_args','--','--exact'],
            }]
        elif source_id == 'ponylang__ponyc-2201':
            native_tests=['DontcareTest.*']
            native_groups=[{
                'id':'ponyc_dontcare_argument', 'role':'changed_behavior', 'tests':native_tests,
                'description':'The native Pony compiler dont-care expression regression suite passes.',
                'command':['bash','-lc',"make -j2 >/tmp/ponyc-build.log && build/release/libponyc.tests --gtest_filter='DontcareTest.*'"],
            }]
        elif source_id.startswith('instance_future-architect__vuls-'):
            native_tests=['models','gost','oval']
            native_groups=[{
                'id':'vuls_raspbian_filter', 'role':'changed_behavior', 'tests':native_tests,
                'description':'The Vuls native Go model and Debian advisory package suites pass.',
                'command':['/usr/local/go/bin/go','test','./models','./gost','./oval'],
            }]
        elif source_id.startswith('instance_element-hq__element-web-'):
            native_tests=['test/voice-broadcast']
            native_groups=[{
                'id':'element_voice_broadcast', 'role':'changed_behavior', 'tests':native_tests,
                'description':'The native Element voice-broadcast Jest suites pass.',
                'command':['yarn','test','test/voice-broadcast','--runInBand'],
            }]
        elif source_id.startswith('instance_ansible__ansible-4c5ce5a1'):
            native_tests=[
                'test/units/module_utils/basic/test_selinux.py',
                'test/units/module_utils/basic/test_imports.py',
                'test/units/executor/module_common/test_recursive_finder.py',
            ]
            native_groups=[{
                'id':'ansible_module_respawn', 'role':'changed_behavior', 'tests':native_tests,
                'description':'The upstream Ansible SELinux compatibility and module respawn unit regression surface passes.',
                'command':['python3','-m','pytest','-q',*native_tests,'-k','not test_module_utils_basic_import_literal_eval'],
            }]
        elif source_id.startswith('instance_qutebrowser__qutebrowser-473a15f'):
            native_tests=['tests/unit/config/test_qtargs_locale_workaround.py']
            native_groups=[{
                'id':'qutebrowser_locale_workaround', 'role':'changed_behavior', 'tests':native_tests,
                'description':'The complete upstream qutebrowser QtWebEngine locale workaround regression corpus passes.',
                'command':['python3','-m','pytest','-q',*native_tests],
            }]
        if source_id.startswith('sympy__'):
            sympy_test_file = (
                'sympy/physics/units/tests/test_quantities.py'
                if source_id == 'sympy__sympy-24066'
                else 'sympy/geometry/tests/test_point.py'
            )
            for group in native_groups:
                group['command']=[
                    '/opt/miniconda3/envs/testbed/bin/python','bin/test',
                    sympy_test_file,'-k',*group['tests'],
                ]
        base_commit=native['source_binding']['base_commit']; image=SWE_IMAGES[source_id]
        if source_id.startswith('django__'):
            selected=[group['command'][-1] for group in native_groups]
            native_command=['/opt/miniconda3/envs/testbed/bin/python','tests/runtests.py','--verbosity','0',*selected]
        elif source_id.startswith('pytest-dev__'):
            selected=[test for group in native_groups for test in group['tests']]
            native_command=['/opt/miniconda3/envs/testbed/bin/python','-m','pytest','-q',*selected]
        elif source_id == 'facebook__zstd-2094':
            runtime_python='python3'
            native_command=['bash','-lc','make -C tests -j2 zstreamtest >/tmp/zstd-build.log && ./tests/zstreamtest -T10s']
        elif source_id == 'clap-rs__clap-2534':
            runtime_python='python3'
            native_command=['cargo','test','--test','help','custom_help_headers_hidden_args','--','--exact']
        elif source_id == 'ponylang__ponyc-2201':
            runtime_python='/opt/conda/bin/python'
            native_command=['bash','-lc',"make -j2 >/tmp/ponyc-build.log && build/release/libponyc.tests --gtest_filter='DontcareTest.*'"]
        elif source_id.startswith('instance_future-architect__vuls-'):
            runtime_python='python3'
            native_command=['/usr/local/go/bin/go','test','./models','./gost','./oval']
        elif source_id.startswith('instance_element-hq__element-web-'):
            runtime_python='python3'
            native_command=['yarn','test','test/voice-broadcast','--runInBand']
        elif source_id.startswith('instance_ansible__ansible-4c5ce5a1'):
            runtime_python='python3'
            native_command=['python3','-m','pytest','-q',*native_tests,'-k','not test_module_utils_basic_import_literal_eval']
        elif source_id.startswith('instance_qutebrowser__qutebrowser-473a15f'):
            runtime_python='python3'
            native_command=['python3','-m','pytest','-q',*native_tests]
        else:
            # SWE-bench's declared nodes are the executable source contract.
            # Do not widen them to whole files: that can pull in unrelated,
            # environment-sensitive tests that the source benchmark excludes.
            selected=native_tests
            native_command=['/opt/miniconda3/envs/testbed/bin/python','-m','pytest','-q',*selected]
        if source_id == 'sphinx-doc__sphinx-11510':
            # The async worker owns the nested-include dependency probe.  The
            # full official FAIL_TO_PASS/PASS_TO_PASS surface remains in the
            # hidden verifier; keeping the worker probe narrow also avoids
            # coupling it to pytest's application-fixture path identity.
            native_command=[
                '/opt/miniconda3/envs/testbed/bin/python','-m','pytest','-q',
                'tests/test_directive_other.py::test_include_source_read_event_nested_includes',
                'tests/test_directive_other.py::test_toctree',
                'tests/test_directive_other.py::test_relative_toctree',
            ]
        elif source_id == 'sympy__sympy-24066':
            native_command=[
                '/opt/miniconda3/envs/testbed/bin/python','bin/test',
                'sympy/physics/units/tests/test_quantities.py','-k',*native_tests,
            ]
        elif source_id.startswith('sympy__'):
            native_command=[
                '/opt/miniconda3/envs/testbed/bin/python','bin/test',
                'sympy/geometry/tests/test_point.py','-k',
                'test_issue_22684','test_concyclic_doctest_bug','test_point3D',
            ]
        testbed_deps = ""
        if source_id == 'pytest-dev__pytest-5631':
            testbed_deps = "RUN /opt/miniconda3/envs/testbed/bin/python -m pip install --no-cache-dir mock==5.1.0\n"
        if source_id == 'facebook__zstd-2094':
            write(case_dir/'task/Dockerfile', f"FROM {image}\nRUN python3 -m pip install --no-cache-dir pytest==8.3.5\nRUN ln -s /home/zstd /testbed && mkdir -p /app/task_file /app/output_data\nCOPY task_file /app/task_file\nWORKDIR /testbed\nCMD [\"bash\", \"-lc\", \"sleep infinity\"]\n")
        elif source_id == 'clap-rs__clap-2534':
            write(case_dir/'task/Dockerfile', f"FROM {image}\nRUN python3 -m pip --version >/dev/null 2>&1 || (apt-get update && apt-get install -y --no-install-recommends python3-pip && rm -rf /var/lib/apt/lists/*)\nRUN python3 -m pip install --no-cache-dir pytest==8.3.5 pytest-rerunfailures==14.0 || python3 -m pip install --break-system-packages --no-cache-dir pytest==8.3.5 pytest-rerunfailures==14.0\nRUN test -e /testbed || ln -s /home/clap /testbed\nRUN cd /testbed && git checkout {base_commit}\nRUN mkdir -p /app/task_file /app/output_data\nCOPY task_file /app/task_file\nWORKDIR /testbed\nENTRYPOINT []\nCMD [\"bash\", \"-lc\", \"sleep infinity\"]\n")
        elif source_id == 'ponylang__ponyc-2201':
            write(case_dir/'task/Dockerfile', f"FROM {image}\nRUN apt-get update && apt-get install -y --no-install-recommends ca-certificates wget bzip2 && rm -rf /var/lib/apt/lists/*\nRUN wget -q https://repo.anaconda.com/miniconda/Miniconda3-py39_4.12.0-Linux-x86_64.sh -O /tmp/miniconda.sh && bash /tmp/miniconda.sh -b -p /opt/conda && rm /tmp/miniconda.sh\nRUN /opt/conda/bin/python -m pip install --no-cache-dir pytest==8.3.5 pytest-rerunfailures==14.0\nRUN ln -s /home/ponyc /testbed && mkdir -p /app/task_file /app/output_data\nCOPY task_file /app/task_file\nWORKDIR /testbed\nENTRYPOINT []\nCMD [\"bash\", \"-lc\", \"sleep infinity\"]\n")
        elif source_id.startswith('instance_future-architect__vuls-'):
            write(case_dir/'task/Dockerfile', f"FROM {image}\nRUN PIP_INDEX_URL=https://pypi.org/simple python3 -m pip install --break-system-packages --no-cache-dir pytest==8.3.5 pytest-rerunfailures==14.0\nRUN ln -s /app /testbed && mkdir -p /app/task_file /app/output_data\nCOPY task_file /app/task_file\nWORKDIR /testbed\nENTRYPOINT []\nCMD [\"bash\", \"-lc\", \"sleep infinity\"]\n")
        elif source_id.startswith('instance_element-hq__element-web-'):
            write(case_dir/'task/Dockerfile', f"FROM {image}\nRUN PIP_INDEX_URL=https://pypi.org/simple python3 -m pip install --no-cache-dir pytest==8.3.5 pytest-rerunfailures==14.0\nRUN ln -s /app /testbed && mkdir -p /app/task_file /app/output_data\nCOPY task_file /app/task_file\nWORKDIR /testbed\nENTRYPOINT []\nCMD [\"bash\", \"-lc\", \"sleep infinity\"]\n")
        elif source_id.startswith('instance_ansible__ansible-4c5ce5a1'):
            write(case_dir/'task/Dockerfile', f"FROM {image}\nRUN PIP_INDEX_URL=https://pypi.org/simple python3 -m pip install --no-cache-dir pytest==8.3.5 pytest-rerunfailures==14.0\nRUN ln -s /app /testbed && mkdir -p /app/task_file /app/output_data\nCOPY task_file /app/task_file\nWORKDIR /testbed\nENTRYPOINT []\nCMD [\"bash\", \"-lc\", \"sleep infinity\"]\n")
        elif source_id.startswith('instance_qutebrowser__qutebrowser-473a15f'):
            write(case_dir/'task/Dockerfile', f"FROM {image}\nENV QT_QPA_PLATFORM=offscreen QTWEBENGINE_DISABLE_SANDBOX=1\nRUN ln -s /app /testbed && mkdir -p /app/task_file /app/output_data\nCOPY task_file /app/task_file\nWORKDIR /testbed\nENTRYPOINT []\nCMD [\"bash\", \"-lc\", \"sleep infinity\"]\n")
        else:
            write(case_dir/'task/Dockerfile', f"FROM {image}\nRUN python -m pip install --no-cache-dir pytest==8.3.5\n{testbed_deps}RUN mkdir -p /app/task_file /app/output_data\nCOPY task_file /app/task_file\nWORKDIR /testbed\nCMD [\"bash\", \"-lc\", \"sleep infinity\"]\n")
        dump(case_dir/'task/task_file/source_instance.json', {key: record[key] for key in ('instance_id','repo','base_commit','problem_statement','version') if key in record})
        dump(case_dir/'private/source_instance.json',record)
        code_patch_b64=base64.b64encode(record['patch'].encode()).decode()
        test_patch_b64=base64.b64encode(record['test_patch'].encode()).decode()
        write(case_dir/'task/tests/source_test.patch',record['test_patch'])
        write(case_dir/'task/upstream_solutions/reference_solution.sh', f"#!/bin/bash\nset -euo pipefail\ncd /testbed\nprintf '%s' '{code_patch_b64}' | base64 -d > /tmp/gold.patch\nprintf '%s' '{test_patch_b64}' | base64 -d > /tmp/test.patch\ngit apply /tmp/gold.patch\nif [[ -s /tmp/test.patch ]]; then git apply /tmp/test.patch; fi\n")
        spec=SWE_EVENT_PROBES[source_id]; event=spec['event']; meaning=spec['meaning']; paths=spec['paths']
        workspace='/testbed'
        source_instruction=record['problem_statement']
    else:
        runtime_python='python3'
        spec=TB_EVENT_PROBES[source_id]; locked=ROOT/'upstream/terminal-bench/original-tasks-locked'/source_id
        for item in locked.iterdir():
            if item.name in {'tests','solution.sh','run-tests.sh','task.yaml','docker-compose.yaml'}: continue
            target=case_dir/'task'/item.name
            shutil.copytree(item,target,dirs_exist_ok=True) if item.is_dir() else shutil.copy2(item,target)
        shutil.copy2(locked/'solution.sh',case_dir/'task/upstream_solutions'/f'{source_id}.sh')
        source_tests=locked/'tests'; source_test=source_tests/'test_outputs.py'
        if source_test.is_file():
            shutil.copytree(source_tests,case_dir/'task/tests/upstream_tests',dirs_exist_ok=True)
            tree=ast.parse(source_test.read_text(encoding='utf-8')); upstream_functions=[n.name for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name.startswith('test_')]
        event=spec['event']; meaning=spec['meaning']; paths=spec['paths']; workspace='/app'; source_instruction=str(yaml.safe_load((locked/'task.yaml').read_text(encoding='utf-8'))['instruction'])
        if source_id == 'nginx-request-logging':
            verifier_setup='nginx -t\nnginx\n'
        dockerfile=case_dir/'task/Dockerfile'
        write(dockerfile,dockerfile.read_text(encoding='utf-8').rstrip()+"\n\nRUN python3 -m pip --version >/dev/null 2>&1 || (apt-get update && apt-get install -y --no-install-recommends python3-pip && rm -rf /var/lib/apt/lists/*)\nRUN python3 -m pip install --break-system-packages --no-cache-dir pytest==8.3.5\nRUN mkdir -p /app/task_file /app/output_data\nCOPY task_file /app/task_file\nCMD [\"bash\", \"-lc\", \"sleep infinity\"]\n")
    sem=semantic_registry(case_id,native_groups,upstream_functions)
    public,private,requirements,event_contracts=case_contracts(row,sem,workspace,source_instruction,runtime_python)
    if benchmark == 'SWE-bench':
        public['source_tasks'][0]['source_sha256']=hashlib.sha256(record['patch'].encode()).hexdigest()
    else:
        public['source_tasks'][0].update({
            'upstream_path': f'upstream/terminal-bench/original-tasks-locked/{source_id}',
            'upstream_commit': 'd28711d0da2675d0bb1d56de45ae5df6082438a3',
            'preserved_test': 'task/tests/upstream_tests/test_outputs.py',
        })
    instruction=participant_instruction(source_instruction,source_id,requirements)
    write(case_dir/'task/docker-compose.yaml', "services:\n  client:\n    build:\n      context: .\n      dockerfile: Dockerfile\n    command: [\"sh\", \"-c\", \"mkdir -p /app/output_data && sleep infinity\"]\n")
    write(case_dir/'task/.dockerignore',"tests\nupstream_solutions\nequivalence_solutions\nnegative_mutations\noracle.sh\nrun-tests.sh\n")
    difficulty = "hard" if benchmark == "swe-bench" else "medium"
    write(case_dir/'task/task.yaml', f"instruction: |-\n  {instruction.replace(chr(10), chr(10)+'  ')}\nauthor_name: Async-RBench transformation\ndifficulty: {difficulty}\ncategory: {slug(benchmark)}\ntags: [{slug(benchmark)}, {slug(row['async_classification_plan']['primary_event_theme'])}]\nparser_name: pytest\nmax_agent_timeout_sec: 1800\nmax_test_timeout_sec: 1200\n")
    write(case_dir/'instruction.md', instruction)
    write(case_dir/'task/task_file/scripts/event_worker.py', event_worker_source(case_id,source_id,event,meaning,paths,native_command))
    write(case_dir/'task/task_file/scripts/write_manifest.py', manifest_source(case_id,source_id,workspace))
    write(case_dir/'task/tests/test_case_outcomes.py', contract_tests(case_id,source_id,base_commit,native_groups))
    write(case_dir/'task/tests/test_control_flow.py', control_tests())
    dump(case_dir/'task/tests/semantic_checks.json',sem)
    control=formal_control_points(row,sem,public)
    control_registry={'version':'7','event_contracts':event_contracts,'checks':control}
    dump(case_dir/'task/tests/control_flow_checks.json',control_registry)
    dump(case_dir/'private/dynamic_point_plan.json',control_registry)
    dump(case_dir/'private/case_ir.json',row['case_ir_blueprint']); dump(case_dir/'private/score_plan.json',{'points':control,'negative_mutations':control_negative_blueprint(control,sem)}); dump(case_dir/'private/runtime_contract.json',row['runtime_package_plan']); dump(case_dir/'private/source_lock.json',row['source_audit'])
    dump(case_dir/'public_case.yaml',public)
    dump(case_dir/'private/private_case.yaml',private)
    dump(case_dir/'private/source_task.yaml',{'instruction':source_instruction})
    write(case_dir/'task/run-tests.sh',f"#!/bin/bash\nset -euo pipefail\nif [[ -s /async_rbench_tests/source_test.patch ]]; then\n  cd /testbed\n  if ! git apply --reverse --check /async_rbench_tests/source_test.patch >/dev/null 2>&1; then git apply /async_rbench_tests/source_test.patch; fi\nfi\n{verifier_setup}cd /async_rbench_tests\ntest_files=(test_case_outcomes.py test_control_flow.py)\nif [[ -f upstream_tests/test_outputs.py ]]; then test_files=(upstream_tests/test_outputs.py \"${{test_files[@]}}\"); fi\n{runtime_python} -m pytest -q -rA \"${{test_files[@]}}\"\n")
    if benchmark=='SWE-bench': oracle_solution='/async_rbench/upstream_solutions/reference_solution.sh'
    else: oracle_solution=f'/async_rbench/upstream_solutions/{source_id}.sh'
    write(case_dir/'task/oracle.sh',f"#!/bin/bash\nset -euo pipefail\nbash {oracle_solution}\nmkdir -p /app/output_data\nprintf '%s\\n' '{{\"status\":\"provisional_implementation_persisted\"}}' > /app/output_data/provisional_checkpoint.json\nprintf '%s\\n' '{{\"source_task_id\":\"{source_id}\",\"preserved\":true}}' > /app/output_data/preserved_source_facts.json\n{runtime_python} /app/task_file/scripts/event_worker.py --workspace {workspace}\n{runtime_python} /app/task_file/scripts/write_manifest.py\n")
    closure=f"\nmkdir -p /app/output_data\nprintf '%s\\n' '{{\"status\":\"alternative_checkpoint\"}}' > /app/output_data/provisional_checkpoint.json\nprintf '%s\\n' '{{\"source_task_id\":\"{source_id}\",\"preserved\":true}}' > /app/output_data/preserved_source_facts.json\n{runtime_python} /app/task_file/scripts/event_worker.py --workspace {workspace}\n{runtime_python} /app/task_file/scripts/write_manifest.py\n"
    if benchmark=='SWE-bench':
        alternative=f"#!/bin/bash\nset -euo pipefail\ncd /testbed\nprintf '%s' '{code_patch_b64}' | base64 -d > /tmp/equivalent.patch\nprintf '%s' '{test_patch_b64}' | base64 -d > /tmp/equivalent-test.patch\npatch -p1 < /tmp/equivalent.patch\nif [[ -s /tmp/equivalent-test.patch ]]; then patch -p1 < /tmp/equivalent-test.patch; fi\n"+closure
    else:
        source_solution=(case_dir/'task/upstream_solutions'/f'{source_id}.sh').read_text(encoding='utf-8')
        alternative=source_solution.rstrip()+"\n"+closure
    write(case_dir/'task/equivalence_solutions/alternative_solution.sh',alternative)
    write(case_dir/'task/negative_mutations/wrong_event_receipt.sh',f"#!/bin/bash\nset -euo pipefail\n{runtime_python} - <<'PY'\nimport json,pathlib\np=pathlib.Path('/app/output_data/event_receipt.json'); r=json.loads(p.read_text()); r['case_id']='wrong-case'; p.write_text(json.dumps(r))\nPY\n")
    write(case_dir/'task/negative_mutations/broken_closure_lineage.sh',f"#!/bin/bash\nset -euo pipefail\n{runtime_python} - <<'PY'\nimport json,pathlib\np=pathlib.Path('/app/output_data/decision_manifest.json'); r=json.loads(p.read_text()); r['event_receipt_sha256']='0'*64; p.write_text(json.dumps(r))\nPY\n")
    dump(case_dir/'private/quality_contract.yaml',quality_contract(case_id,source_id,source_instruction,sem,control,public,private))
    dump(case_dir/'mutation_families.json',mutation_suite(case_id,sem,control))
    write(case_dir/'PROVENANCE.md',f"# {case_id}\n\nSource: `{benchmark}` / `{source_id}`.\n\nPrimary event: `{row['async_classification_plan']['primary_event_theme']}`.\n\nThis candidate copies the locked upstream runtime or binds the official SWE-bench image, preserves source-native tests, and adds a task-specific independent event receipt plus causal closure checks. It is not registered until Docker Oracle and isolated verifier execution pass.\n")
    dump(case_dir/'STATUS.json',{'case_id':case_id,'status':'materialized_pending_runtime_execution','semantic_check_count':len(sem['checks']),'control_check_count':len(control),'source_native_test_count':len(native_tests) or len(upstream_functions),'docker_oracle_executed':False,'hidden_verifier_executed':False})
    return {'case_id':case_id,'benchmark':benchmark,'source_task_id':source_id,'semantic_checks':len(sem['checks']),'control_checks':len(control),'source_native_tests':len(native_tests) or len(upstream_functions),'path':str(case_dir.relative_to(ROOT)).replace('\\','/')}


def _read_native(row: dict) -> dict:
    path=next(ROOT/p for p in row['source_audit']['source_files'] if p.endswith('native_case.json'))
    return json.loads(path.read_text(encoding='utf-8'))


def main() -> int:
    parser=argparse.ArgumentParser(description='Materialize the selected SWE runtime batch safely')
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--confirm-materialize',action='store_true')
    parser.add_argument('--case-local-repair',action='store_true')
    args=parser.parse_args()
    guards=[guard_for_root(ROOT,c,case_local_repair=args.case_local_repair) for c in SELECTED]
    if args.dry_run:
        print(json.dumps({'dry_run':True,'writes_performed':False,'guards':guards},indent=2)); return 0
    if not args.confirm_materialize:
        parser.error('writing requires --confirm-materialize; use --dry-run to inspect')
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise SystemExit('pyarrow is required; run with: uv run --with pyarrow python scripts/materialize_first_10_cases.py') from exc
    parquet=ROOT/'artifacts/case-transformability-audit-v2/swe-bench-verified-test.parquet'
    table=pq.read_table(parquet); records={row['instance_id']:row for row in table.to_pylist()}
    zstd_patch=(ROOT/'artifacts/tracebench-source-lock/facebook__zstd-2094/official-pr-2094.patch').read_text(encoding='utf-8')
    records['facebook__zstd-2094']={
        'instance_id':'facebook__zstd-2094',
        'repo':'facebook/zstd',
        'base_commit':'6b4a3e019f8eeb3423065f7b24d790358e8cbc59',
        'problem_statement':('Add the experimental stable-output decompression parameter so callers with a sufficiently large, immutable output buffer can avoid the internal output allocation and copy. Fix single-pass handling for empty frames and preserve safe behavior for undersized or modified buffers. Validate the change with the native streaming and fuzz regressions.'),
        'version':'multi-swe-bench-pr-2094',
        'patch':zstd_patch,
        'test_patch':'',
    }
    pony_id='ponylang__ponyc-2201'
    pony_task=json.loads((ROOT/'artifacts/source-native-v4/cases/swe_bench/swe-dependency-unblock-bacfa3601e/participant_task.json').read_text(encoding='utf-8'))
    records[pony_id]={
        'instance_id':pony_id, 'repo':'ponylang/ponyc',
        'base_commit':'f00f95b30dd68c7faaff0aa88508c218bc19f02b',
        'problem_statement':pony_task['problem_statement'],
        'version':'multi-swe-bench-pr-2201',
        'patch':(ROOT/'artifacts/tracebench-source-lock/ponyc-2201/official-code.patch').read_text(encoding='utf-8'),
        'test_patch':(ROOT/'artifacts/tracebench-source-lock/ponyc-2201/official-tests.patch').read_text(encoding='utf-8'),
    }
    clap_id='clap-rs__clap-2534'
    clap_task=json.loads((ROOT/'artifacts/source-native-v4/cases/swe_bench/swe-partial-failure-recovery-fdf2f24539/participant_task.json').read_text(encoding='utf-8'))
    records[clap_id]={
        'instance_id':clap_id, 'repo':'clap-rs/clap',
        'base_commit':'33c305ea6ff6cdda7796e57966374cb40633968f',
        'problem_statement':clap_task['problem_statement'],
        'version':'multi-swe-bench-pr-2534',
        'patch':(ROOT/'artifacts/tracebench-source-lock/clap-2534/official-code.patch').read_text(encoding='utf-8'),
        'test_patch':(ROOT/'artifacts/tracebench-source-lock/clap-2534/official-tests.patch').read_text(encoding='utf-8'),
    }
    vuls_traj=next((ROOT/'artifacts/tracebench-source-lock/vuls-b8db2e0').rglob('*.traj.json'))
    vuls_data=json.loads(vuls_traj.read_text(encoding='utf-8'))
    vuls_id='instance_future-architect__vuls-b8db2e0b74f60cb7d45f710f255e061f054b6afc'
    records[vuls_id]={
        'instance_id':vuls_id, 'repo':'future-architect/vuls',
        'base_commit':'43b46cb324f64076e4d9e807c0b60c4b9ce11a82',
        'problem_statement':'Make Raspbian package removal return a pointer while preserving the original non-Raspbian result, filtering both binary and source package maps without mutating the input, and update Debian advisory callers accordingly.',
        'version':'sweap-vuls-b8db2e0', 'patch':vuls_data['info']['submission'], 'test_patch':'',
    }
    element_traj=next((ROOT/'artifacts/tracebench-source-lock/element-web-fe14847/short').glob('*.traj.json'))
    element_data=json.loads(element_traj.read_text(encoding='utf-8'))
    element_id='instance_element-hq__element-web-fe14847bb9bb07cab1b9c6c54335ff22ca5e516a-vnan'
    records[element_id]={
        'instance_id':element_id, 'repo':'element-hq/element-web',
        'base_commit':'ad9cbe93994888e8f8ba88ce3614dc041a698930',
        'problem_statement':'Add voice-broadcast recording models and a recordings store with explicit state-change events, lifecycle management, and public exports while preserving existing voice-broadcast component behavior.',
        'version':'sweap-element-fe14847', 'patch':element_data['info']['submission'], 'test_patch':'',
    }
    ansible_id='instance_ansible__ansible-4c5ce5a1a9e79a845aff4978cfeb72a0d4ecf7d6-v1055803c3a812189a1133297f7f5468579283f86'
    records[ansible_id]={
        'instance_id':ansible_id, 'repo':'ansible/ansible',
        'base_commit':'8a175f59c939ca29ad56f3fa9edbc37a8656879a',
        'problem_statement':'Add an internal ctypes SELinux compatibility layer and a module respawn API so modules can locate dependencies under well-known system interpreters. Apply respawn behavior to package-management modules and preserve the updated upstream SELinux/import/module-bundling regression tests.',
        'version':'tracebench-sweap-ansible-4c5ce5a1',
        'patch':(ROOT/'artifacts/tracebench-source-lock/ansible-4c5ce5a/official-code.patch').read_text(encoding='utf-8'),
        'test_patch':(ROOT/'artifacts/tracebench-source-lock/ansible-4c5ce5a/official-unit-tests.patch').read_text(encoding='utf-8'),
    }
    qute_id='instance_qutebrowser__qutebrowser-473a15f7908f2bb6d670b0e908ab34a28d8cf7e2-v363c8a7e5ccdf6968fc7ab84a2053ac78036691d'
    qute_task=json.loads((ROOT/'artifacts/source-native-v4/cases/swe_bench/swe-late-constraint-e3481d7625/participant_task.json').read_text(encoding='utf-8'))
    records[qute_id]={
        'instance_id':qute_id, 'repo':'qutebrowser/qutebrowser',
        'base_commit':'8e08f046aeffb38445cc659050f7a083b4a9649c',
        'problem_statement':qute_task['problem_statement'],
        'version':'tracebench-sweap-qutebrowser-473a15f',
        'patch':(ROOT/'artifacts/tracebench-source-lock/qutebrowser-473a15f/official-code.patch').read_text(encoding='utf-8'),
        'test_patch':(ROOT/'artifacts/tracebench-source-lock/qutebrowser-473a15f/official-tests.patch').read_text(encoding='utf-8'),
    }
    audit=build_transformability_audit(ROOT); by_id={r['case_id']:r for r in audit['rows']}; output=ROOT/'candidate_cases/rebuild-to-100/runtime-swe-next'; output.mkdir(parents=True,exist_ok=True)
    results=[materialize(by_id[case_id],records,output) for case_id in SELECTED]
    dump(output/'batch-manifest.json',{'schema_version':'2','case_count':len(results),'cases':results,'selection_basis':'five SWE-bench Verified cases with official image bindings and isolated clean-clone event workers'})
    print(json.dumps({'output':str(output),'cases':results},indent=2)); return 0

if __name__=='__main__': raise SystemExit(main())
