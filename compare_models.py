import json
from pathlib import Path

PROD = {
    "label_up_1h": {"accuracy": 0.81, "macro_f1": 0.79, "note": "stable"},
    "label_up_4h": {"accuracy": 0.79, "macro_f1": 0.68, "note": "stable"},
    "label_up_24h": {"accuracy": 0.89, "macro_f1": 0.83, "note": "stable"},
}

report_path = Path("data/models_experimental_v2/report.json")
if not report_path.exists():
    print("report missing")
    raise SystemExit(1)

rows = json.loads(report_path.read_text(encoding="utf-8"))
for r in rows:
    t = r["target"]
    p = PROD.get(t, {})
    print("=" * 50)
    print(t)
    print("production:", p)
    print("experimental_v2:", r)
    # 실전 효용성 관점 코멘트
    if r.get("precision", 0) >= 0.7 and r.get("accept_rate", 1) <= 0.5:
        print("verdict: 고확신 필터로는 실전 적용 후보")
    else:
        print("verdict: 추가 검증 필요")
