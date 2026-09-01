#!/usr/bin/env bash
# Reference solution for swe-bench-selective-patch (benchmark-maintenance only).
#
# Applies the complete gold-fix semantics to the single fix target
# sklearn/utils/multiclass.py, re-verifies every module group plus the full
# regression, and records the final fix and integration verdicts.
#
# The gold-fix semantics are structure-derived from the SWE-bench instance
# scikit-learn__scikit-learn-25638 (pandas nullable-dtype acceptance in
# sklearn/utils/multiclass.py, gh-25634/gh-25635/gh-25637); no upstream patch
# text is reproduced verbatim. This file is NEVER shipped to the participant
# image.
set -euo pipefail

cd /app

# --- Apply the complete fix to the single fix target -------------------------
python3 - <<'PY'
path = "/app/task_file/src/sklearn/utils/multiclass.py"
content = open(path, encoding="utf-8").read()

old_tot = (
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
new_tot = (
    "    if not issparse(y) and y.dtype == object:\n"
    "        # Gold-fix semantics (structure-derived from scikit-learn gh-25634/5/7):\n"
    "        # an object-dtype target array is the NumPy manifestation of a pandas\n"
    "        # nullable dtype. Convert its non-missing entries to numeric form for\n"
    "        # type inference so a missing marker never turns a discrete target into\n"
    "        # a continuous one.\n"
    "        cleaned = np.asarray(\n"
    "            [\n"
    "                v for v in y.ravel()\n"
    "                if v is not None and not (isinstance(v, float) and np.isnan(v))\n"
    "            ],\n"
    "            dtype=float,\n"
    "        )\n"
    "        if cleaned.size:\n"
    "            y = cleaned\n"
    "        elif not isinstance(y.flat[0], str):\n"
    "            return \"unknown\"\n"
)
assert old_tot in content, "type_of_target base block not found"
content = content.replace(old_tot, new_tot, 1)

old_um = (
    "def _unique_multiclass(y):\n"
    "    xp, is_array_api = get_namespace(y)\n"
    "    if hasattr(y, \"__array__\") or is_array_api:\n"
    "        return xp.unique_values(xp.asarray(y))\n"
    "    else:\n"
    "        return set(y)\n"
)
new_um = (
    "def _unique_multiclass(y):\n"
    "    xp, is_array_api = get_namespace(y)\n"
    "    if hasattr(y, \"__array__\") or is_array_api:\n"
    "        values = xp.asarray(y)\n"
    "        if values.dtype.kind == \"O\":\n"
    "            # Gold-fix semantics: drop missing markers from object-dtype\n"
    "            # (nullable) label arrays before taking the unique set.\n"
    "            values = np.array(\n"
    "                [v for v in values.ravel() if v is not None], dtype=object\n"
    "            )\n"
    "        return xp.unique_values(values)\n"
    "    else:\n"
    "        return set(y)\n"
)
assert old_um in content, "_unique_multiclass base block not found"
content = content.replace(old_um, new_um, 1)

open(path, "w", encoding="utf-8").write(content)
print("reference solution applied (sklearn/utils/multiclass.py)")
PY

# --- Record the final fix revision -------------------------------------------
python3 /app/task_file/scripts/record_fix.py --stage final || exit 1

# --- Re-verify every module group against the complete fix -------------------
python3 /app/task_file/scripts/run_module_group_a.py || exit 1
python3 /app/task_file/scripts/run_module_group_b.py || exit 1
python3 /app/task_file/scripts/run_module_group_c.py || exit 1

# --- Full regression (the three groups + smoke, deterministic order) ---------
python3 /app/task_file/scripts/run_regression.py || exit 1

# --- Record the integrated-fix verdict ---------------------------------------
python3 /app/task_file/scripts/record_integrated.py || exit 1
