"""Protocol probe: intentionally delegates only one child, then waits."""
import json
import sys


def emit(value): print(json.dumps(value), flush=True)


start=json.loads(sys.stdin.readline())
emit({"type":"participant_metadata","backend":"mock","main_model":"mock-model","child_model":"mock-model","workspace_mode":"disabled","config_sha256":"0"*64})
emit({"type":"ready"})
emit({"type":"child_spawned","child_id":"only","parent_id":"main","work_units":[start["allowed_work_units"][0]]})
emit({"type":"child_started","child_id":"only"})
emit({"type":"child_completed","child_id":"only","completion_id":"only-result",
      "result_kind":start["allowed_result_kinds"][0],"payload":{"partial":True},"usage":{"tokens":10}})
delivery=json.loads(sys.stdin.readline())
emit({"type":"result_consumed","completion_id":delivery["completion_id"],"action_id":"consume"})
emit({"type":"episode_ended","declared_task_success":True})
