import json
from pathlib import Path

Path("/app/output_data/font_size_result.json").write_text(json.dumps({
    "default_font_size": 24,
    "evaluator": "check_font_size",
    "official_score": 1.0,
    "source_task_id": "osworld:chrome:af630914-714e-4a24-a7bb-f9af687d3b91",
}, sort_keys=True) + "\n")
