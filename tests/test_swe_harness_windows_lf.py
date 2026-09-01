import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "upstream" / "swe-bench-harness" / "swebench" / "harness" / "run_evaluation.py"


def load_write_container_text():
    tree = ast.parse(HARNESS.read_text(encoding="utf-8"))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "write_container_text")
    function.returns = None
    for argument in function.args.args:
        argument.annotation = None
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(HARNESS), "exec"), namespace)
    return namespace["write_container_text"]


def test_container_script_is_lf_only(tmp_path):
    write_container_text = load_write_container_text()
    target = tmp_path / "eval.sh"
    write_container_text(target, "#!/bin/bash\nset -uxo pipefail\necho ok\n")
    raw = target.read_bytes()
    assert b"\r\n" not in raw
    assert raw.count(b"\n") == 3


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        test_container_script_is_lf_only(Path(directory))
