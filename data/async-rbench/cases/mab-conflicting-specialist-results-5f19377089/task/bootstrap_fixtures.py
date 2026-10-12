"""Create Linux-only fixture paths that cannot be portably stored in Git."""
import json
from pathlib import Path

root = Path("/app/task_file/src")
manifest = json.loads((root.parent / "source_manifest.json").read_text())
for name in manifest["included"]:
    path = root / name
    if name.startswith(("deep/", "long/")):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"deep\r\n" if name.startswith("deep/") else b"long\r\n")
    elif name == "link-out" and not path.is_symlink():
        path.symlink_to("/outside/target")

# Deliberately inert exclusion fixtures, not credentials or a real repository.
for name, content in ((".git/config", b"secret\n"), ("keys/private.key", b"key\n")):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
(root / "keys/private.key").chmod(0o600)
