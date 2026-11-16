"""生成 9 类错误注入用例并用判定程序逐个验证:注入必须被拒,原始对照必须通过。

输入取 artifacts/w03/test-small-v1(首轮已核对通过的报告)与 traces。
用法: .venv/bin/python customer/w03/make_injections.py
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
REPORT = ROOT / "artifacts/w03/test-small-v1/metric_test_report.json"
TRACES = ROOT / "artifacts/w03/test-small-v1/traces"
OUT = ROOT / "artifacts/w03/judge-checks"
JUDGE = [str(ROOT / ".venv/bin/python"), str(ROOT / "customer/w03/judge.py")]

report = json.load(open(REPORT))
expected = {c["id"]: c["expected"] for c in report["cases"]}


def actual_for(metrics, start=None, group_by=None):
    """按 intent 特征(metrics/时段/分组)找回该用例的 result.json。"""
    want = group_by or []
    for d in sorted(TRACES.iterdir()):
        try:
            r = json.load(open(d / "result.json"))
        except Exception:
            continue
        i = r.get("intent") or {}
        if i.get("metrics") == metrics and (start is None or i.get("start") == start) \
                and i.get("group_by") == want:
            return r
    raise SystemExit(f"trace not found for {metrics} start={start} group={want}")


def run(name, pair):
    path = OUT / f"{name}.json"
    json.dump(pair, open(path, "w"), ensure_ascii=False)
    out = subprocess.run(JUDGE, stdin=open(path), capture_output=True, text=True)
    verdict = json.loads(out.stdout)
    return verdict["passed"]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cases = [
        ("inj-wrong-metric", "aug-order-counts", ["order_count", "paid_order_count",
                                                  "valid_order_count", "cancelled_order_count"],
         "2026-08-01"),
        ("inj-wrong-date", "aug-order-counts", ["order_count", "paid_order_count",
                                                "valid_order_count", "cancelled_order_count"],
         "2026-08-01"),
        ("inj-wrong-filter", "aug-filter-channel", ["valid_order_count", "net_sales_cents"],
         "2026-08-01", []),
        ("inj-missing-group", "aug-group-store", ["valid_order_count", "net_sales_cents"],
         "2026-08-01", ["store"]),
        ("inj-unit-yuan", "aug-amounts", ["payment_cents", "refund_cents", "net_sales_cents",
                                          "gross_cents", "discount_cents"], "2026-08-01"),
        ("inj-ratio-percent", "aug-ratios", ["avg_order_value", "avg_buyer_value",
                                             "purchase_frequency", "refund_amount_rate",
                                             "cancel_rate", "refund_order_rate",
                                             "discount_rate", "items_per_order"], "2026-08-01"),
        ("inj-null-to-zero", "mar2026-empty", ["order_count", "net_sales_cents", "buyer_count",
                                               "avg_order_value", "cancel_rate"], "2026-03-01"),
        ("inj-tamper-value", "aug-order-counts", ["order_count", "paid_order_count",
                                                  "valid_order_count", "cancelled_order_count"],
         "2026-08-01"),
        ("inj-error-as-ok", "mar2026-empty", ["order_count", "net_sales_cents", "buyer_count",
                                              "avg_order_value", "cancel_rate"], "2026-03-01"),
    ]
    pairs = {}
    for case in cases:
        name, cid, metrics, start = case[0], case[1], case[2], case[3]
        gb = case[4] if len(case) > 4 else []
        exp = json.loads(json.dumps(expected[cid]))
        act = json.loads(json.dumps(actual_for(metrics, start, gb)))
        act.pop("answer", None)
        if name == "inj-wrong-metric":
            act["intent"]["metrics"][0] = "payment_cents"
        elif name == "inj-wrong-date":
            act["intent"]["end"] = "2026-09-02"
        elif name == "inj-wrong-filter":
            act["intent"]["filters"] = [{"field": "order__channel", "op": "eq", "value": "门店"}]
        elif name == "inj-missing-group":
            act["rows"] = act["rows"][:1]  # 只留 S01,漏 S02
        elif name == "inj-unit-yuan":
            act["units"]["payment_cents"] = "yuan"
        elif name == "inj-ratio-percent":
            act["rows"][0] = [v * 100 if isinstance(v, float) else v for v in act["rows"][0]]
        elif name == "inj-null-to-zero":
            act["rows"][0][3] = 0  # avg_order_value null→0
        elif name == "inj-tamper-value":
            act["rows"][0][0] = act["rows"][0][0] + 1
        elif name == "inj-error-as-ok":
            failed = json.loads(json.dumps(actual_for(["order_count"], "2026-10-01")))
            failed["status"] = "ok"  # 失败结果伪装成 ok,行残留为空
            failed.pop("reason", None)
            act = failed
        pairs[name] = {"expected": exp, "actual": act}

    rejected = {name: not run(name, pairs[name]) for name in pairs}
    originals = {}
    for case in cases:
        name, cid, metrics, start = case[0], case[1], case[2], case[3]
        gb = case[4] if len(case) > 4 else []
        if name in originals:
            continue
        exp = json.loads(json.dumps(expected[cid]))
        act = json.loads(json.dumps(actual_for(metrics, start, gb)))
        act.pop("answer", None)
        originals[cid] = run(f"orig-{cid}", {"expected": exp, "actual": act})
    ok = True
    for name, rejected_ok in rejected.items():
        print(f"{name:22s} 注入被拒={'YES' if rejected_ok else 'NO!!'}")
        ok &= rejected_ok
    for cid, passed in originals.items():
        print(f"orig-{cid:22s} 原始通过={'YES' if passed else 'NO!!'}")
        ok &= passed
    print("ALL OK" if ok else "SOME CHECKS FAILED", file=sys.stderr)


if __name__ == "__main__":
    main()
