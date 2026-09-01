#!/usr/bin/env bash
set -euo pipefail
cd /app

# Independently construct the required failure-then-repair trajectory.  The
# preprocessing group is intentionally exercised first so this is not the
# canonical oracle ordering.
python3 - <<'PY'
from pathlib import Path
p=Path('/app/task_file/src/sklearn/utils/multiclass.py')
t=p.read_text(encoding='utf-8')
old='''    if not issparse(y) and y.dtype == object and not isinstance(y.flat[0], str):
        # [obj_1] and not ["label_1"]
        return "unknown"
'''
new='''    if not issparse(y) and y.dtype == object:
        # First fix attempt: convert object-dtype (nullable) targets to float.
        # This repairs the metrics and utils groups but does not handle the
        # preprocessing group's missing markers, so those are coerced to NaN
        # and rejected by the finite-value assertion.
        try:
            y = np.asarray(y, dtype=float)
        except (TypeError, ValueError):
            if not isinstance(y.flat[0], str):
                return "unknown"
'''
assert t.count(old)==1
p.write_text(t.replace(old,new),encoding='utf-8')
PY
python3 /app/task_file/scripts/record_fix.py --stage initial
python3 /app/task_file/scripts/run_module_group_b.py || true
cp /app/output_data/module_groups/B_result.json /app/output_data/module_groups/B_result_initial.json
python3 /app/task_file/scripts/run_module_group_a.py
python3 /app/task_file/scripts/run_module_group_c.py
# Apply the complete semantics independently instead of calling the canonical
# evaluator solution.  Keeping this implementation self-contained proves that
# the verifier accepts a second legitimate trajectory rather than one script
# path or one fixed execution order.
python3 - <<'PY'
from pathlib import Path

p = Path('/app/task_file/src/sklearn/utils/multiclass.py')
t = p.read_text(encoding='utf-8')
old_tot = '''    if not issparse(y) and y.dtype == object:
        # First fix attempt: convert object-dtype (nullable) targets to float.
        # This repairs the metrics and utils groups but does not handle the
        # preprocessing group's missing markers, so those are coerced to NaN
        # and rejected by the finite-value assertion.
        try:
            y = np.asarray(y, dtype=float)
        except (TypeError, ValueError):
            if not isinstance(y.flat[0], str):
                return "unknown"
'''
new_tot = '''    if not issparse(y) and y.dtype == object:
        cleaned = np.asarray(
            [
                v for v in y.ravel()
                if v is not None and not (isinstance(v, float) and np.isnan(v))
            ],
            dtype=float,
        )
        if cleaned.size:
            y = cleaned
        elif not isinstance(y.flat[0], str):
            return "unknown"
'''
old_unique = '''def _unique_multiclass(y):
    xp, is_array_api = get_namespace(y)
    if hasattr(y, "__array__") or is_array_api:
        return xp.unique_values(xp.asarray(y))
    else:
        return set(y)
'''
new_unique = '''def _unique_multiclass(y):
    xp, is_array_api = get_namespace(y)
    if hasattr(y, "__array__") or is_array_api:
        values = xp.asarray(y)
        if values.dtype.kind == "O":
            values = np.array(
                [v for v in values.ravel() if v is not None], dtype=object
            )
        return xp.unique_values(values)
    else:
        return set(y)
'''
assert t.count(old_tot) == 1
assert t.count(old_unique) == 1
p.write_text(t.replace(old_tot, new_tot).replace(old_unique, new_unique), encoding='utf-8')
PY
python3 /app/task_file/scripts/record_fix.py --stage final
python3 /app/task_file/scripts/run_module_group_c.py
python3 /app/task_file/scripts/run_module_group_a.py
python3 /app/task_file/scripts/run_module_group_b.py
python3 /app/task_file/scripts/run_regression.py
python3 /app/task_file/scripts/record_integrated.py
python3 /app/task_file/scripts/write_manifest.py
