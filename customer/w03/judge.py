"""确定性判定程序:只比较期望与实际,不调用大模型,不另起查询。

比较顺序:状态 → 数据版本 → 意图 → 单位 → 列 → 行/值。
- 整数与字符串严格相等;浮点数(比率/均额)用相对误差 1e-9 容差,防止"比例误作百分数"蒙混。
- null 与 0 视为不同("null 改零"必须被拒);null 与 null 相等(分母零未定义)。
- 分组行按键元组匹配,允许无意义的行列重排;漏组、多组、重复组都判不通过。
调试信息写标准错误,标准输出只输出 {"passed": bool, "differences": [...]}。
"""
import json
import re
import sys
from datetime import datetime

REL_TOL = 1e-9
_DATEISH = re.compile(r"^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?$")


def _norm_key(v):
    """日期型分组键按解析后的时间点比较(如 '2026-07-01' 与 '2026-07-01 00:00:00' 同义);其余原样。"""
    if isinstance(v, str) and _DATEISH.fullmatch(v.strip()):
        s = v.strip().replace("T", " ")
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
    return v


def _num_eq(a, b):
    """数值比较:整数严格,浮点用相对容差;null 只与 null 相等。"""
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int,)) and isinstance(b, (int,)):
        return a == b
    try:
        fa, fb = float(a), float(b)
    except (TypeError, ValueError):
        return False
    if fa == fb:
        return True
    denom = max(abs(fa), abs(fb))
    return abs(fa - fb) <= REL_TOL * max(denom, 1e-12)


def _intent_diff(exp_intent, act_intent, diffs):
    exp_m = sorted(exp_intent.get("metrics", []))
    act_m = sorted((act_intent or {}).get("metrics", []))
    if exp_m != act_m:
        diffs.append(f"指标不一致: 期望 {exp_m} 实际 {act_m}")
    for key in ("start", "end"):
        if exp_intent.get(key) != (act_intent or {}).get(key):
            diffs.append(f"{key} 不一致: 期望 {exp_intent.get(key)} 实际 {(act_intent or {}).get(key)}")
    exp_g = sorted(exp_intent.get("group_by", []))
    act_g = sorted((act_intent or {}).get("group_by", []))
    if exp_g != act_g:
        diffs.append(f"分组不一致: 期望 {exp_g} 实际 {act_g}")
    exp_f = sorted((f.get("field"), f.get("op"), json.dumps(f.get("value"), sort_keys=True, ensure_ascii=False))
                   for f in exp_intent.get("filters", []))
    act_f = sorted((f.get("field"), f.get("op"), json.dumps(f.get("value"), sort_keys=True, ensure_ascii=False))
                   for f in (act_intent or {}).get("filters", []))
    if exp_f != act_f:
        diffs.append(f"筛选不一致: 期望 {exp_f} 实际 {act_f}")


def _row_diff(exp_row, act_row, n_keys, diffs, label, exp_cols=None, act_cols=None):
    """键列按位置(日期归一)比较;值列在两侧列名集合一致时按列名对齐,否则按位置。"""
    align = None
    if exp_cols and act_cols and len(exp_cols) == len(act_cols) \
            and sorted(exp_cols[n_keys:]) == sorted(act_cols[n_keys:]):
        act_pos = {c: i for i, c in enumerate(act_cols)}
        align = {i: act_pos[c] for i, c in enumerate(exp_cols) if i >= n_keys}
    for i, e in enumerate(exp_row):
        if i < n_keys:
            if _norm_key(e) != _norm_key(act_row[i]):
                diffs.append(f"{label} 键不符: 期望 {e} 实际 {act_row[i]}")
        else:
            j = align[i] if align else i
            a = act_row[j] if j < len(act_row) else None
            name = exp_cols[i] if exp_cols and i < len(exp_cols) else f"第{i}列"
            if not _num_eq(e, a):
                diffs.append(f"{label} 值不符 {name}: 期望 {e!r} 实际 {a!r}")


def _rows_diff(expected, actual, diffs):
    exp_rows = expected.get("rows", [])
    act_rows = actual.get("rows", [])
    n_keys = len(expected.get("intent", {}).get("group_by", []))
    exp_cols = expected.get("columns")
    act_cols = actual.get("columns")
    if n_keys == 0:
        if len(exp_rows) != len(act_rows):
            diffs.append(f"行数不一致: 期望 {len(exp_rows)} 实际 {len(act_rows)}")
            return
        for i, (er, ar) in enumerate(zip(exp_rows, act_rows)):
            _row_diff(er, ar, 0, diffs, f"第{i}行", exp_cols, act_cols)
        return
    # 分组:按键元组匹配,顺序不敏感;日期型键归一后比较
    def key_of(row):
        return tuple(_norm_key(k) for k in row[:n_keys])

    exp_map, dup = {}, []
    for r in exp_rows:
        k = key_of(r)
        if k in exp_map:
            dup.append(k)
        exp_map[k] = r
    if dup:
        diffs.append(f"期望行存在重复分组键: {dup}")
    act_map = {}
    for r in act_rows:
        k = key_of(r)
        if k in act_map:
            diffs.append(f"实际行存在重复分组键: {k}")
        act_map[k] = r
    missing = sorted(set(exp_map) - set(act_map))
    extra = sorted(set(act_map) - set(exp_map))
    if missing:
        diffs.append(f"缺少分组行: {missing}")
    if extra:
        diffs.append(f"多出分组行: {extra}")
    for k in sorted(set(exp_map) & set(act_map)):
        _row_diff(exp_map[k], act_map[k], n_keys, diffs, f"组{k}", exp_cols, act_cols)


def compare(expected, actual):
    diffs = []
    exp_status = expected.get("status")
    act_status = actual.get("status")
    if exp_status != act_status:
        diffs.append(f"状态不一致: 期望 {exp_status} 实际 {act_status}(实际原因: {actual.get('reason') or actual.get('code')})")
        return {"passed": False, "differences": diffs}
    if exp_status != "ok":
        return {"passed": diffs == [], "differences": diffs}
    exp_ver = expected.get("data_version")
    if exp_ver and actual.get("data_version") != exp_ver:
        diffs.append(f"数据版本不一致: 期望 {exp_ver} 实际 {actual.get('data_version')}")
    _intent_diff(expected.get("intent", {}), actual.get("intent"), diffs)
    exp_units = expected.get("units", {})
    act_units = actual.get("units", {})
    for mid, unit in exp_units.items():
        if act_units.get(mid) != unit:
            diffs.append(f"单位不一致 {mid}: 期望 {unit} 实际 {act_units.get(mid)}")
    exp_cols = expected.get("columns", [])
    act_cols = actual.get("columns", [])
    if sorted(exp_cols) != sorted(act_cols):
        diffs.append(f"列不一致: 期望 {exp_cols} 实际 {act_cols}")
    elif exp_cols != act_cols:
        print("提示: 列顺序不同,按无意义重排处理", file=sys.stderr)
    _rows_diff(expected, actual, diffs)
    return {"passed": diffs == [], "differences": diffs}


if __name__ == "__main__":
    data = json.load(sys.stdin)
    print(json.dumps(compare(data["expected"], data["actual"]), ensure_ascii=False))
