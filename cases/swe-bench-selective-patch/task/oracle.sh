#!/usr/bin/env bash
# Benchmark-maintenance oracle for swe-bench-selective-patch.
#
# Reproduces the designed failure-then-repair process so the verifier's frozen
# outcome contract is satisfiable by a legitimate participant trajectory:
#   stage 1: an INCOMPLETE first fix is applied that repairs the metrics and
#            utils groups but not the preprocessing group's nullable path;
#   stage 2: the incomplete fix is recorded, the two unaffected groups are run
#            and pass, the preprocessing group fails and the failure is kept;
#   stage 3: the complete fix (reference_solution.sh) is applied, every group
#            and the full regression are re-verified, and the integration
#            verdict is recorded;
#   stage 4: the decision manifest is assembled from the recorded artifacts.
#
# This script is NEVER shipped to the participant image.
set -uo pipefail

cd /app

# --- Stage 1: an incomplete first fix attempt --------------------------------
python3 - <<'PY'
path = "/app/task_file/src/sklearn/utils/multiclass.py"
content = open(path, encoding="utf-8").read()

old_tot = (
    "    if not issparse(y) and y.dtype == object and not isinstance(y.flat[0], str):\n"
    "        # [obj_1] and not [\"label_1\"]\n"
    "        return \"unknown\"\n"
)
new_tot = (
    "    if not issparse(y) and y.dtype == object:\n"
    "        # First fix attempt: convert object-dtype (nullable) targets to float.\n"
    "        # This repairs the metrics and utils groups but does not handle the\n"
    "        # preprocessing group's missing markers, so those are coerced to NaN\n"
    "        # and rejected by the finite-value assertion.\n"
    "        try:\n"
    "            y = np.asarray(y, dtype=float)\n"
    "        except (TypeError, ValueError):\n"
    "            if not isinstance(y.flat[0], str):\n"
    "                return \"unknown\"\n"
)
assert old_tot in content, "type_of_target base block not found"
content = content.replace(old_tot, new_tot, 1)
open(path, "w", encoding="utf-8").write(content)
print("stage 1: incomplete first fix applied")
PY

# --- Stage 2a: record the first fix revision ---------------------------------
python3 /app/task_file/scripts/record_fix.py --stage initial || exit 1

# --- Stage 2b: run the two unaffected groups (expected to pass) --------------
python3 /app/task_file/scripts/run_module_group_a.py || true
python3 /app/task_file/scripts/run_module_group_c.py || true

# --- Stage 2c: run the preprocessing group (expected to fail) and keep the
# failure record so the manifest can report the first run honestly.
python3 /app/task_file/scripts/run_module_group_b.py || true
cp /app/output_data/module_groups/B_result.json \
   /app/output_data/module_groups/B_result_initial.json

# --- Stage 3: complete fix + full re-verification ----------------------------
bash /async_rbench/upstream_solutions/reference_solution.sh || exit 1

# --- Stage 4: assemble the process record ------------------------------------
python3 /app/task_file/scripts/write_manifest.py || exit 1

echo "oracle complete"
