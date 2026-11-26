"""Explicit scripted model outputs for deterministic diagnosis demonstrations."""

import json
from .models import ScriptedModel

DEMO_PROMPT = "查询样例门店 SAMPLE-01 在 2026-01-01 的订单数，并说明数据来源。"


def tool_turn(arguments):
    return {"role": "assistant", "content": None, "tool_calls": [{
        "id": "demo-call-1", "type": "function", "function": {
            "name": "count_sample_orders", "arguments": json.dumps(arguments)}}]}


def fixture(case):
    args = {"store_id": "SAMPLE-01", "day": "2026-01-01"}
    answers = {
        "B0": "样例门店有 3 单。来源：DATA-DEMO-ORDERS-v1/SAMPLE-01/2026-01-01。",
        "B2": "工具参数未通过校验，需要补齐合法日期后重新查询。",
        "B3": "该日期数据未提供，不能判断订单数，也不能据此认定为零。",
        "B4": "样例门店有 30 单。来源：DATA-DEMO-ORDERS-v1/SAMPLE-01/2026-01-01。",
        "ZERO": "样例门店有 0 单。来源：DATA-DEMO-ORDERS-v1/SAMPLE-01/2026-01-02。",
    }
    if case == "B1":
        return ScriptedModel(["MODEL_TIMEOUT"])
    if case == "B2":
        args["day"] = "not-a-date"
    if case == "B3":
        args["day"] = "2026-01-03"
    if case == "ZERO":
        args["day"] = "2026-01-02"
    return ScriptedModel([tool_turn(args), {"role": "assistant", "content": answers[case]}])
