#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json
import pathlib

p = pathlib.Path('/app/output_data/negotiation_closure.json')
d = json.loads(p.read_text())
# Model an agent that legally completes its output but ignores the delayed
# authority result: it keeps the provisional terms and never records the
# authority transition or closure re-verification.  The receipt and the
# unaffected workflows remain intact so this is a semantic/control-flow
# mutation, not an injected execution error.
d['authority_applied'] = False
d['selected_terms'] = {'unit_price': 54.0, 'condition_check': 'pending'}
d['tool_sequence'] = ['offer', 'counter', 'finalize']
d['source_semantics_reverified'] = False
p.write_text(json.dumps(d, sort_keys=True) + '\n')
PY
