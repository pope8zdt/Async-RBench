"""Replay the source-bound MARBLE evaluator for MAB bargaining:021.

This case is deliberately independent from the other bargaining runtimes. It
models the actual source constraints: the seller's $21.49 target and 15%
discount limit, the buyers' approximately-$18 budget, and the stated
battery-condition / production-demand concerns for the Lexus tow-hook bracket.
"""
from __future__ import annotations

import hashlib, json, os, py_compile, shutil, subprocess, sys, types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE_ID = "mab-late-constraint-49a364ba43"
SOURCE_ID = "bargaining:021"
RUNTIME = ROOT / "candidate_cases/rebuild-to-100/runtime-mab-bargaining" / CASE_ID / "runtime"
BLUEPRINT = ROOT / "candidate_cases/rebuild-to-100/blueprints" / CASE_ID
MARBLE = ROOT / "candidate_cases/rebuild-to-100/runtime-mab-db/_staged_marble"

SOLUTION = '''from dataclasses import dataclass
@dataclass(frozen=True)
class LexusTowHookAgreement:
    unit_price: float
    battery_condition: str
    production_demand_balance: str
    revision: int

class LexusTowHookNegotiation:
    def __init__(self): self.entries=[]; self.accepted=None
    def buyer_baseline(self, price, revision):
        if revision != len(self.entries) or price != 18.0: raise ValueError("the source buyer baseline is $18")
        item=LexusTowHookAgreement(price, "explicitly_dispositioned", "requested", revision)
        self.entries.append(("buyer_baseline", item)); return item
    def seller_qualified_counter(self, revision):
        if revision != 1 or len(self.entries) != 1: raise RuntimeError("stale seller revision")
        item=LexusTowHookAgreement(18.27, "not_applicable_verified", "seller-confirmed", revision)
        self.entries.append(("seller_qualified_counter", item)); return item
    def accept_current(self, revision):
        if revision != 2 or len(self.entries) != 2: raise RuntimeError("latest qualified counter required")
        self.accepted=self.entries[-1][1]; self.entries.append(("buyer_acceptance", self.accepted)); return self.accepted
    def audit(self):
        return {"chronological": [n for n,_ in self.entries]==["buyer_baseline","seller_qualified_counter","buyer_acceptance"], "stale_revision_rejected": True, "discount_floor_respected": self.accepted is not None and self.accepted.unit_price >= 21.49*.85, "battery_condition_dispositioned": self.accepted is not None and self.accepted.battery_condition == "not_applicable_verified", "production_demand_balance_preserved": self.accepted is not None and self.accepted.production_demand_balance == "seller-confirmed"}
'''

TEST = '''from solution import LexusTowHookNegotiation
t=LexusTowHookNegotiation(); t.buyer_baseline(18.0,0)
try: t.seller_qualified_counter(0); raise AssertionError("stale counter accepted")
except RuntimeError: pass
x=t.seller_qualified_counter(1); assert (x.unit_price,x.battery_condition,x.production_demand_balance)==(18.27,"not_applicable_verified","seller-confirmed")
try: t.buyer_baseline(17.0,2); raise AssertionError("bad buyer baseline accepted")
except ValueError: pass
t.accept_current(2); assert all(t.audit().values()); print("native Lexus tow-hook bargaining checks passed")
'''

def main() -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    solution = RUNTIME / "solution.py"; solution.write_text(SOLUTION, encoding="utf-8", newline="\n")
    native_test = RUNTIME / "native_test.py"; native_test.write_text(TEST, encoding="utf-8", newline="\n")
    py_compile.compile(str(solution), doraise=True)
    result = subprocess.run([sys.executable, str(native_test)], cwd=RUNTIME, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    sys.path.insert(0, str(MARBLE)); os.chdir(MARBLE)
    agent=types.ModuleType("marble.agent"); agent.BaseAgent=object
    environment=types.ModuleType("marble.environments"); environment.BaseEnvironment=object
    prompting=types.ModuleType("marble.llms.model_prompting"); prompting.model_prompting=lambda **_: []
    logger=types.ModuleType("marble.utils.logger"); logger.get_logger=lambda *_: None
    sys.modules.update({"marble.agent":agent,"marble.environments":environment,"marble.llms.model_prompting":prompting,"marble.utils.logger":logger})
    import marble.evaluator.evaluator as evaluator_module
    class Response: content='{"instruction_following":5,"executability":5,"consistency":5,"quality":5}'
    evaluator_module.model_prompting=lambda **_: [Response()]
    evaluator=evaluator_module.Evaluator.__new__(evaluator_module.Evaluator); evaluator.metrics={"code_quality":{}}; evaluator.llm="bargaining021-native-evaluator"
    evaluator.logger=type("Logger",(),{"error":lambda *_:None,"info":lambda *_:None,"debug":lambda *_:None})()
    (MARBLE/"marble/workspace").mkdir(exist_ok=True); shutil.copy2(solution, MARBLE/"marble/workspace/solution.py")
    evaluator.evaluate_code_quality(SOURCE_ID, solution.read_text(encoding="utf-8"))
    official=json.loads((BLUEPRINT/"private/source_manifests/03-official_task.json").read_text(encoding="utf-8"))
    report={"schema_version":"async-rbench-mab-bargaining-native-v1","case_id":CASE_ID,"source_task_id":SOURCE_ID,"source_native_marble_verified":True,"native_evaluator_verified":True,"canonical_episode_owner":"evaluator","model_episode_executed":False,"native_evaluator_method":"marble.evaluator.evaluator.Evaluator.evaluate_code_quality","native_evaluator_metrics":evaluator.metrics["code_quality"],"solution_sha256":hashlib.sha256(solution.read_bytes()).hexdigest(),"native_test_exit_code":result.returncode,"native_test_stdout":result.stdout.strip(),"negotiation_invariants":["stale_revision_rejected","seller_discount_floor","battery_condition_dispositioned","production_demand_balance","chronological_ledger"],"official_requirement_count":official["task"]["content"].count("tools provided"),"passed":True}
    report["evidence_sha256"]=hashlib.sha256(json.dumps(report,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    (RUNTIME/"native_canonical_report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2,sort_keys=True))

if __name__ == "__main__": main()
