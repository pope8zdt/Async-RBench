#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import pathlib
p=pathlib.Path('/app/output_data/solution.py'); t=p.read_text()
before="elif any(token.lower() in payload for token in self.contract['phishing_tokens']): threat='phishing'; verdict='malicious'"
after="elif any(token.lower() in payload for token in self.contract['phishing_tokens']): threat=None; verdict='benign'"
assert t.count(before)==1
p.write_text(t.replace(before,after))
PY
