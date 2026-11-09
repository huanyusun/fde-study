"""独立审核程序:期望值计算器。

不导入指标库、不执行被测 SQL,直接按客户材料口径从 CSV 逐记录计算期望:
- 通用订单 16 项与比率 8 项:materials/w03/01_订单日报说明.md、02_财务邮件.md
- 会员周报 8 项:materials/w03/03_会员运营周报.md
- 付费月报 6 项:materials/w03/04_本期统计确认邮件.md + 业务模型付费资格规则
  (悦享年卡/家庭季卡;valid_from 当天起有效;valid_until 当天已无效;ended_at 当天起无效)

用法:
  .venv/bin/python customer/w03/audit_expectations.py \
      --data materials/data/small --start 2026-08-01 --end 2026-09-01
窗口为半开区间 [start, end);比率分母为零输出 null;月度族按自然月逐月输出。
"""
import argparse
import csv
import json
from datetime import date
from pathlib import Path

PAID_CARD_TYPES = ("悦享年卡", "家庭季卡")  # 小林 MSG-03325,仅本期月报口径


def read_rows(data_dir, name):
    with open(Path(data_dir) / f"{name}.csv", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_d(s):
    return date.fromisoformat(s) if s else None


def card_valid_on(card, day):
    """付费卡在判定日 day 是否处于有效状态(按业务模型候选定稿端点)。"""
    if card["card_type"] not in PAID_CARD_TYPES:
        return False
    if parse_d(card["valid_from"]) > day:  # 开始日当天起有效
        return False
    vu = parse_d(card["valid_until"])
    if vu and day >= vu:  # 结束日当天已无效(不含)
        return False
    ea = parse_d(card["ended_at"])
    if ea and day >= ea:  # 提前终止日当天起无效
        return False
    return True


def eligible_accounts(cards, day):
    """判定日有资格的账户集合(任一张付费卡有效即成立,按账户去重)。"""
    return {c["member_id"] for c in cards if card_valid_on(c, day)}


def in_window(d, start, end):
    return start <= d < end


def order_metrics(orders, start, end):
    """通用订单 16 项;[start, end) 半开区间。"""
    create = paid = valid = cancelled = refund_o = partial = full = 0
    pay_c = ref_c = gross_c = disc_c = net_c = items = 0
    buyers, refund_buyers, stores = set(), set(), set()
    for o in orders:
        d = parse_d(o["ordered_at"])
        if not in_window(d, start, end):
            continue
        create += 1
        st = o["status"]
        pc, rc = int(o["paid_cents"]), int(o["refund_cents"])
        if st == "cancelled":
            cancelled += 1
            continue  # 取消单:金额列为 0,也不进 paid 族
        paid += 1
        pay_c += pc
        gross_c += int(o["gross_cents"])
        disc_c += int(o["gross_cents"]) - pc
        ref_c += rc
        net_c += pc - rc
        if rc > 0:
            refund_o += 1
            refund_buyers.add(o["member_id"])
            if rc < pc:
                partial += 1
            elif pc > 0:
                full += 1
        if pc - rc > 0:  # 有效订单:paid 且实付-退款>0
            valid += 1
            items += int(o["quantity"])
            buyers.add(o["member_id"])
            stores.add(o["store_id"])
    return {
        "order_count": create,
        "paid_order_count": paid,
        "valid_order_count": valid,
        "cancelled_order_count": cancelled,
        "refund_order_count": refund_o,
        "partial_refund_order_count": partial,
        "full_refund_order_count": full,
        "payment_cents": pay_c,
        "refund_cents": ref_c,
        "net_sales_cents": net_c,
        "gross_cents": gross_c,
        "discount_cents": disc_c,
        "buyer_count": len(buyers),
        "refund_buyer_count": len(refund_buyers),
        "selling_store_count": len(stores),
        "valid_order_items": items,
    }


def ratio_metrics(m):
    """比率 8 项;分母为零输出 None(未定义)。"""
    def div(a, b):
        return None if b == 0 else a / b
    return {
        "avg_order_value": div(m["net_sales_cents"], m["valid_order_count"]),
        "avg_buyer_value": div(m["net_sales_cents"], m["buyer_count"]),
        "purchase_frequency": div(m["valid_order_count"], m["buyer_count"]),
        "refund_amount_rate": div(m["refund_cents"], m["payment_cents"]),
        "cancel_rate": div(m["cancelled_order_count"], m["order_count"]),
        "refund_order_rate": div(m["refund_order_count"], m["paid_order_count"]),
        "discount_rate": div(m["discount_cents"], m["gross_cents"]),
        "items_per_order": div(m["valid_order_items"], m["valid_order_count"]),
    }


def first_purchase_metrics(orders, start, end, cov_start, cov_end):
    """观测期首购 4 项:先全覆盖期确定每账户首笔有效订单,再按窗口筛选。

    repeat_order_count = 每账户按(下单日期,订单号)排序后第二笔及以后的有效订单按下单日期落窗计数
    ——同日但订单号靠后的也是"第二笔",与指标库 row_number 排序语义一致。
    """
    firsts = {}  # member_id -> 首笔有效订单
    repeat_in_window = 0
    for o in sorted(orders, key=lambda x: (x["ordered_at"], x["order_id"])):
        if o["status"] != "paid" or int(o["paid_cents"]) - int(o["refund_cents"]) <= 0:
            continue
        d = parse_d(o["ordered_at"])
        if not (cov_start <= d < cov_end):
            continue
        mid = o["member_id"]
        if mid not in firsts:
            firsts[mid] = o
        elif in_window(d, start, end):
            repeat_in_window += 1
    fb = fo = 0
    fsales = 0
    for mid, o in firsts.items():
        d = parse_d(o["ordered_at"])
        if in_window(d, start, end):
            fb += 1
            fo += 1
            fsales += int(o["paid_cents"]) - int(o["refund_cents"])
    return {
        "first_buyer_count": fb,
        "first_order_sales_cents": fsales,
        "first_order_count": fo,
        "repeat_order_count": repeat_in_window,
    }


def monthly_general(orders, members, start, end):
    """月内族:窗口内逐自然月输出(仅整月、全门店口径)。"""
    per_month = {}
    for o in orders:
        if o["status"] != "paid" or int(o["paid_cents"]) - int(o["refund_cents"]) <= 0:
            continue
        d = parse_d(o["ordered_at"])
        if in_window(d, start, end):
            per_month.setdefault(d.strftime("%Y-%m"), {}).setdefault(o["member_id"], 0)
            per_month[d.strftime("%Y-%m")][o["member_id"]] += 1
    out = {}
    for ym, acct in sorted(per_month.items()):
        out[ym] = {
            "monthly_buyer_count": len(acct),
            "monthly_repeat_buyer_count": sum(1 for n in acct.values() if n >= 2),
        }
        b = out[ym]["monthly_buyer_count"]
        r = out[ym]["monthly_repeat_buyer_count"]
        out[ym]["monthly_repeat_rate"] = None if b == 0 else r / b
    return out


def monthly_paid(orders, cards, start, end):
    """付费月报族:逐自然月,月末判定资格,当月有效订单按资格账户筛选。"""
    out = {}
    months = sorted({parse_d(o["ordered_at"]).strftime("%Y-%m") for o in orders
                     if in_window(parse_d(o["ordered_at"]), start, end)})
    for ym in months:
        y, m = map(int, ym.split("-"))
        if m == 12:
            last = date(y, 12, 31)
        else:
            last = date(y, m + 1, 1).replace(day=1) - (date(y, m + 1, 1) - date(y, m, 28)) if False else None
        # 月末最后一天
        import calendar
        last = date(y, m, calendar.monthrange(y, m)[1])
        elig = eligible_accounts(cards, last)
        vo = po = buyers = 0
        sales = 0
        per_acct = {}
        for o in orders:
            d = parse_d(o["ordered_at"])
            if o["status"] != "paid" or not in_window(d, start, end) or d.strftime("%Y-%m") != ym:
                continue
            if int(o["paid_cents"]) - int(o["refund_cents"]) <= 0:
                continue
            if o["member_id"] not in elig:
                continue
            vo += 1
            sales += int(o["paid_cents"]) - int(o["refund_cents"])
            per_acct.setdefault(o["member_id"], 0)
            per_acct[o["member_id"]] += 1
        buyers = len(per_acct)
        repeat = sum(1 for n in per_acct.values() if n >= 2)
        out[ym] = {
            "monthly_paid_buyer_count": buyers,
            "monthly_paid_order_count": vo,
            "monthly_paid_sales_cents": sales,
            "monthly_paid_repeat_buyer_count": repeat,
            "monthly_paid_repeat_rate": None if buyers == 0 else repeat / buyers,
            "monthly_paid_avg_order_value": None if vo == 0 else sales / vo,
        }
    return out


def new_members(members, start, end):
    return sum(1 for m in members if in_window(parse_d(m["registered_at"]), start, end))


def by_store(orders, start, end):
    """按成交门店分组的基础指标(用于分组用例)。"""
    out = {}
    for o in orders:
        d = parse_d(o["ordered_at"])
        if not in_window(d, start, end):
            continue
        s = out.setdefault(o["store_id"], {"valid_order_count": 0, "net_sales_cents": 0,
                                           "buyer_count": set()})
        if o["status"] != "paid":
            continue
        pc, rc = int(o["paid_cents"]), int(o["refund_cents"])
        if pc - rc > 0:
            s["valid_order_count"] += 1
            s["net_sales_cents"] += pc - rc
            s["buyer_count"].add(o["member_id"])
    return {k: {"valid_order_count": v["valid_order_count"],
                "net_sales_cents": v["net_sales_cents"],
                "buyer_count": len(v["buyer_count"])} for k, v in sorted(out.items())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--group", choices=["store"], help="按成交门店分组输出")
    ap.add_argument("--channel", help="按渠道筛选后输出基础 16 项")
    ap.add_argument("--store", help="按门店筛选后输出基础 16 项")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    orders = read_rows(args.data, "orders")
    members = read_rows(args.data, "members")
    cards = read_rows(args.data, "cards")
    manifest = json.load(open(Path(args.data) / "manifest.json"))
    cov_start, cov_end = (parse_d(x) for x in manifest["coverage"])
    start, end = parse_d(args.start), parse_d(args.end)

    result = {}
    result.update(order_metrics(orders, start, end))
    result.update(ratio_metrics(result))
    result.update(first_purchase_metrics(orders, start, end, cov_start, cov_end))
    result["new_member_count"] = new_members(members, start, end)
    general = monthly_general(orders, members, start, end)
    for ym, v in general.items():
        result[f"general[{ym}]"] = v
    paid = monthly_paid(orders, cards, start, end)
    for ym, v in paid.items():
        result[f"paid[{ym}]"] = v
    if args.group == "store":
        result["by_store"] = by_store(orders, start, end)
    if args.channel:
        result["channel_filter"] = order_metrics(
            [o for o in orders if o["channel"] == args.channel], start, end)
    if args.store:
        result["store_filter"] = order_metrics(
            [o for o in orders if o["store_id"] == args.store], start, end)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for k, v in result.items():
            if isinstance(v, dict):
                print(f"{k}:")
                for k2, v2 in v.items():
                    print(f"  {k2}: {v2 if not isinstance(v2, float) else round(v2, 6)}")
            else:
                print(f"{k}: {v if not isinstance(v, float) else round(v, 6)}")


if __name__ == "__main__":
    main()
