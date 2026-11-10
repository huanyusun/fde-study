"""tests.json 生成器:期望值全部来自独立审核程序 audit_expectations.py,不从被测结果复制。

用法: .venv/bin/python customer/w03/build_tests.py
读 materials/data/small + 各批次 catalog 的单位定义,写 customer/w03/tests.json。
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
import audit_expectations as audit  # noqa: E402

DATA = ROOT / "materials/data/small"
CATALOGS = [ROOT / "artifacts/w03/build-v10/catalog.json"]
DATA_VERSION = "qinghe-w03-20260923-small"

cases = []


def units_for(metric_ids):
    for cat in CATALOGS:
        if not cat.exists():
            continue
        units = {m["id"]: m["unit"] for m in json.load(open(cat))}
        found = {k: units[k] for k in metric_ids if k in units}
        if len(found) == len(metric_ids):
            return found
    raise SystemExit(f"units not found for {metric_ids}")


def add(cid, question, metrics, start, end, values, source, group_by=None, filters=None):
    """values: 与 metrics 对齐的期望值列表;分组时为按组键组织的行。"""
    if group_by:
        columns = [group_by] + metrics if isinstance(group_by, str) else group_by + metrics
        rows = values
        intent_group = [group_by] if isinstance(group_by, str) else group_by
    else:
        columns = list(metrics)
        rows = [list(values)]
        intent_group = []
    cases.append({
        "id": cid,
        "question": question,
        "expected": {
            "status": "ok",
            "data_version": DATA_VERSION,
            "intent": {"metrics": list(metrics), "start": start, "end": end,
                       "group_by": intent_group, "filters": filters or []},
            "columns": columns,
            "rows": rows,
            "units": units_for(metrics),
        },
        "expected_source": source,
    })


def add_status(cid, question, status, source):
    cases.append({"id": cid, "question": question,
                  "expected": {"status": status}, "expected_source": source})


def base16(o):
    return [o[k] for k in ("order_count", "paid_order_count", "valid_order_count",
                           "cancelled_order_count", "refund_order_count",
                           "partial_refund_order_count", "full_refund_order_count",
                           "payment_cents", "refund_cents", "net_sales_cents",
                           "gross_cents", "discount_cents", "buyer_count",
                           "refund_buyer_count", "selling_store_count", "valid_order_items")]


def run(large=False):
    global DATA_VERSION
    data_dir = ROOT / "materials/data/large" if large else DATA
    if large:
        DATA_VERSION = "qinghe-w03-20260923-large"
    orders = audit.read_rows(data_dir, "orders")
    members = audit.read_rows(data_dir, "members")
    cards = audit.read_rows(data_dir, "cards")
    manifest = json.load(open(data_dir / "manifest.json"))
    cov = tuple(audit.parse_d(x) for x in manifest["coverage"])
    aug = (audit.parse_d("2026-08-01"), audit.parse_d("2026-09-01"))
    jul = (audit.parse_d("2026-07-01"), audit.parse_d("2026-08-01"))
    SRC = (f"期望由 customer/w03/audit_expectations.py 对 {data_dir.relative_to(ROOT)}"
           f"({DATA_VERSION},manifest 含 sha256)逐单计算得到,审核程序不导入指标库。")

    # --- 2026-08 全月 ---
    a = audit.order_metrics(orders, *aug)
    add("aug-order-counts",
        "2026年8月青禾的创建订单数、支付订单数、有效订单数、取消订单数分别是多少?",
        ["order_count", "paid_order_count", "valid_order_count", "cancelled_order_count"],
        "2026-08-01", "2026-09-01",
        [a["order_count"], a["paid_order_count"], a["valid_order_count"], a["cancelled_order_count"]],
        SRC + " 依据01_订单日报说明:8月共32笔订单,其中取消2笔(O0000005、O0000039),paid 30笔;"
              "有效订单=paid且实付-退款>0,全额退款3笔不计,得27笔。")
    add("aug-refund-counts",
        "2026年8月青禾的退款订单数、部分退款订单数、全额退款订单数、退款会员数分别是多少?",
        ["refund_order_count", "partial_refund_order_count", "full_refund_order_count",
         "refund_buyer_count"],
        "2026-08-01", "2026-09-01",
        [a["refund_order_count"], a["partial_refund_order_count"],
         a["full_refund_order_count"], a["refund_buyer_count"]],
        SRC + " 依据01_订单日报说明:退款订单=paid且退款>0,共4笔;O0000003 退款2000<实付9000为部分退款,"
              "O0000004/O0000012/O0000040 退款等于实付为全额退款;涉及 M00002/M00003/M00008/M00017 共4个账户。")
    add("aug-amounts",
        "2026年8月青禾的实付金额、退款金额、净销售额、支付订单原价金额、优惠金额分别是多少?",
        ["payment_cents", "refund_cents", "net_sales_cents", "gross_cents", "discount_cents"],
        "2026-08-01", "2026-09-01",
        [a["payment_cents"], a["refund_cents"], a["net_sales_cents"], a["gross_cents"],
         a["discount_cents"]],
        SRC + " 依据01_订单日报说明与02_财务邮件:仅 paid 单计入,退款按原订单下单日期归属;"
              "实付合计119050分,退款18750分,净额100300分,原价124250分,优惠5200分(退款不冲减原优惠)。")
    add("aug-buyer-store-items",
        "2026年8月青禾的购买会员数、成交门店数、有效订单商品件数分别是多少?",
        ["buyer_count", "selling_store_count", "valid_order_items"],
        "2026-08-01", "2026-09-01",
        [a["buyer_count"], a["selling_store_count"], a["valid_order_items"]],
        SRC + " 依据01_订单日报说明:有效订单涉及15个 CRM 账户(不做自然人去重),门店 S01/S02 共2家,"
              "有效订单 quantity 合计33件。")
    r = audit.ratio_metrics(a)
    add("aug-ratios",
        "2026年8月青禾的有效订单均额、购买会员人均消费、购买频次、退款金额占比、取消率、"
        "退款订单率、优惠率、单均商品件数分别是多少?",
        ["avg_order_value", "avg_buyer_value", "purchase_frequency", "refund_amount_rate",
         "cancel_rate", "refund_order_rate", "discount_rate", "items_per_order"],
        "2026-08-01", "2026-09-01",
        [r["avg_order_value"], r["avg_buyer_value"], r["purchase_frequency"],
         r["refund_amount_rate"], r["cancel_rate"], r["refund_order_rate"],
         r["discount_rate"], r["items_per_order"]],
        SRC + " 依据02_财务邮件:分子分母均为对应基础指标,分母零时未定义(8月分母均非零);"
              "均额=100300/27,人均=100300/15,频次=27/15,退款占比=18750/119050,取消率=2/32,"
              "退款订单率=4/30,优惠率=5200/124250,单均件数=33/27。")
    f = audit.first_purchase_metrics(orders, *aug, cov[0], cov[1])
    add("aug-first-purchase",
        "2026年8月青禾的观测期首购会员数、观测期首单净销售额、观测期首单数、观测期后续购买订单数分别是多少?",
        ["first_buyer_count", "first_order_sales_cents", "first_order_count", "repeat_order_count"],
        "2026-08-01", "2026-09-01",
        [f["first_buyer_count"], f["first_order_sales_cents"], f["first_order_count"],
         f["repeat_order_count"]],
        SRC + " 依据03_会员运营周报:先用覆盖期(2024-09-01至2026-09-01)全历史按 ordered_at、order_id "
              "确定每账户第一笔有效订单,再按窗口筛选;8月首单落窗5笔、净额12800分,第二笔及以后落窗22笔。")
    g = audit.monthly_general(orders, members, *aug)["2026-08"]
    add("aug-monthly-general",
        "2026年8月青禾的月内购买会员数、月内复购会员数、月内复购率是多少?",
        ["monthly_buyer_count", "monthly_repeat_buyer_count", "monthly_repeat_rate"],
        "2026-08-01", "2026-09-01",
        [g["monthly_buyer_count"], g["monthly_repeat_buyer_count"], g["monthly_repeat_rate"]],
        SRC + " 依据03_会员运营周报:同月有≥1笔有效订单的账户15个,≥2笔的12个,复购率12/15;"
              "仅整月、全门店口径,分母非零。")
    p = audit.monthly_paid(orders, cards, *aug)["2026-08"]
    add("aug-paid-family",
        "2026年8月青禾的月末付费会员购买人数、月末付费会员有效订单数、月末付费会员净销售额、"
        "月末付费会员复购人数、月末付费会员复购率、月末付费会员订单均额分别是多少?",
        ["monthly_paid_buyer_count", "monthly_paid_order_count", "monthly_paid_sales_cents",
         "monthly_paid_repeat_buyer_count", "monthly_paid_repeat_rate",
         "monthly_paid_avg_order_value"],
        "2026-08-01", "2026-09-01",
        [p["monthly_paid_buyer_count"], p["monthly_paid_order_count"], p["monthly_paid_sales_cents"],
         p["monthly_paid_repeat_buyer_count"], p["monthly_paid_repeat_rate"],
         p["monthly_paid_avg_order_value"]],
        SRC + " 依据04_本期统计确认邮件与业务模型付费资格规则(悦享年卡+家庭季卡;月末判定;"
              "valid_from 当天起有效、valid_until 当天已无效、ended_at 当天起无效;按账户多卡不重复):"
              "8月31日有资格且当月有有效订单的账户6个、有效订单10笔、净额47550分;"
              "M00005/M00011 卡于08-31终止→当天已无效不算,M00018 仅异业联名卡+体验卡不算,"
              "M00007/M00013 卡08-31起有效→算,M00014 悦享卡08-15终止但家庭卡08-20起有效→算。")

    # --- 2026-07 全月 ---
    j = audit.order_metrics(orders, *jul)
    add("jul-core",
        "2026年7月青禾的创建订单数、有效订单数、净销售额、购买会员数、注册会员数分别是多少?",
        ["order_count", "valid_order_count", "net_sales_cents", "buyer_count", "new_member_count"],
        "2026-07-01", "2026-08-01",
        [j["order_count"], j["valid_order_count"], j["net_sales_cents"], j["buyer_count"],
         audit.new_members(members, *jul)],
        SRC + " 依据01_订单日报说明与03_会员运营周报:7月13笔订单、有效订单与净额逐单累计,"
              "注册会员按 registered_at 计12个新账户。")
    pj = audit.monthly_paid(orders, cards, *jul)["2026-07"]
    add("jul-paid-family",
        "2026年7月青禾的月末付费会员购买人数、月末付费会员有效订单数、月末付费会员净销售额、"
        "月末付费会员复购人数、月末付费会员复购率、月末付费会员订单均额分别是多少?",
        ["monthly_paid_buyer_count", "monthly_paid_order_count", "monthly_paid_sales_cents",
         "monthly_paid_repeat_buyer_count", "monthly_paid_repeat_rate",
         "monthly_paid_avg_order_value"],
        "2026-07-01", "2026-08-01",
        [pj["monthly_paid_buyer_count"], pj["monthly_paid_order_count"], pj["monthly_paid_sales_cents"],
         pj["monthly_paid_repeat_buyer_count"], pj["monthly_paid_repeat_rate"],
         pj["monthly_paid_avg_order_value"]],
        SRC + " 与8月用例同一资格规则:7月31日有资格账户含 M00005(其卡08-31才终止)与 M00014(悦享卡当时仍有效),"
              "但不含 M00007/M00013(卡08-31才起效)——端点规则的反向验证;6个有资格账户当月各有1笔有效订单,"
              "复购0人、复购率0(分母6非零,是真零不是未定义)。")

    # --- 2024-09 观测期起点 ---
    s = audit.first_purchase_metrics(orders, audit.parse_d("2024-09-01"), audit.parse_d("2024-10-01"), cov[0], cov[1])
    so = audit.order_metrics(orders, audit.parse_d("2024-09-01"), audit.parse_d("2024-10-01"))
    add("sep2024-first",
        "2024年9月青禾的创建订单数、观测期首购会员数、观测期首单净销售额、注册会员数分别是多少?",
        ["order_count", "first_buyer_count", "first_order_sales_cents", "new_member_count"],
        "2024-09-01", "2024-10-01",
        [so["order_count"], s["first_buyer_count"], s["first_order_sales_cents"],
         audit.new_members(members, audit.parse_d("2024-09-01"), audit.parse_d("2024-10-01"))],
        SRC + " 覆盖期起点月:仅1笔订单 O0000013(M00001,paid、净额1000分),即该账户观测期首单;"
              "注册会员8个(M00001–M00008,均2024-09-01注册)。验证观测期以覆盖期全历史为历史。")

    # --- 2026-03 覆盖内空月 ---
    add("mar2026-empty",
        "2026年3月青禾的创建订单数、净销售额、购买会员数、有效订单均额、取消率分别是多少?",
        ["order_count", "net_sales_cents", "buyer_count", "avg_order_value", "cancel_rate"],
        "2026-03-01", "2026-04-01",
        [0, 0, 0, None, None],
        SRC + " 依据02_财务邮件:2026-03 在数据覆盖内但无任何订单,计数类为0(不是未定义),"
              "分母为零的比率未定义输出 null,不得输出 0 或 inf。")

    # --- 分组 / 筛选 ---
    bs = audit.by_store(orders, *aug)
    add("aug-group-store",
        "2026年8月青禾各成交门店的有效订单数和净销售额分别是多少?",
        ["valid_order_count", "net_sales_cents"],
        "2026-08-01", "2026-09-01",
        [[store, bs[store]["valid_order_count"], bs[store]["net_sales_cents"]]
         for store in sorted(bs)],
        SRC + " 依据01_订单日报说明按订单归属门店分组:8月有效订单落在 S01(13笔,54650分)与 S02(14笔,45650分)。",
        group_by="store")
    ch = audit.order_metrics([o for o in orders if o["channel"] == "小程序"], *aug)
    add("aug-filter-channel",
        "2026年8月青禾小程序渠道的有效订单数和净销售额分别是多少?",
        ["valid_order_count", "net_sales_cents"],
        "2026-08-01", "2026-09-01",
        [ch["valid_order_count"], ch["net_sales_cents"]],
        SRC + " 依据数据字典 channel 字段筛选小程序:有效订单13笔、净额48700分。",
        filters=[{"field": "order__channel", "op": "eq", "value": "小程序"}])

    # --- 跨多月按月展示 ---
    gj = audit.monthly_general(orders, members, *jul)["2026-07"]
    ga = audit.monthly_general(orders, members, *aug)["2026-08"]
    add("cross-month-monthly",
        "2026年7月和8月,青禾每个月的月内购买会员数和月内复购率分别是多少?",
        ["monthly_buyer_count", "monthly_repeat_rate"],
        "2026-07-01", "2026-09-01",
        [["2026-07-01", gj["monthly_buyer_count"], gj["monthly_repeat_rate"]],
         ["2026-08-01", ga["monthly_buyer_count"], ga["monthly_repeat_rate"]]],
        SRC + " 依据03_会员运营周报:连续整月按月分别展示、不跨月加总人数;7月11人、复购率1/11,8月15人、复购率12/15。",
        group_by="metric_time__month")

    # --- 澄清 / 越界 / 未定义指标 ---
    add_status("no-time-clarify", "青禾的有效订单数是多少?", "clarify",
               "问题未给明确时段,依据任务书与产品约定需要先澄清,不能默认取整月或全期。")
    add_status("out-of-coverage-unsupported", "2026年10月青禾的创建订单数是多少?", "unsupported",
               "2026-10 在覆盖期(2024-09-01至2026-09-01,结束日不含)之外,依据02_财务邮件"
               "数据覆盖之外不是零,应拒绝而不是报0。")
    add_status("unknown-metric-unsupported", "2026年8月青禾的毛利率是多少?", "unsupported",
               "毛利率不在38项目标与客户材料口径内,未定义指标不能假装算出。")

    if large:
        # --- 规模回归:通用订单、金额、首购、复购、付费月报 + 多种问法 ---
        cases.clear()  # 只保留规模用例
        la = audit.order_metrics(orders, *aug)
        add("large-aug-core",
            "2026年8月青禾的创建订单数、支付订单数、有效订单数、净销售额分别是多少?",
            ["order_count", "paid_order_count", "valid_order_count", "net_sales_cents"],
            "2026-08-01", "2026-09-01",
            [la["order_count"], la["paid_order_count"], la["valid_order_count"],
             la["net_sales_cents"]],
            SRC + " 依据01_订单日报说明,审核程序对 materials/data/large(qinghe-w03-20260923-large,"
                  "manifest 含 sha256)逐单计算。")
        add("large-aug-core-rephrase",
            "青禾2026年8月一共创建了多少订单?",
            ["order_count"], "2026-08-01", "2026-09-01",
            [la["order_count"]],
            SRC + " 同 large-aug-core 口径,验证不同问法解析到同一意图。")
        add("large-aug-members",
            "2026年8月青禾的购买会员数、注册会员数、成交门店数分别是多少?",
            ["buyer_count", "new_member_count", "selling_store_count"],
            "2026-08-01", "2026-09-01",
            [la["buyer_count"], audit.new_members(members, *aug), la["selling_store_count"]],
            SRC + " 依据01_订单日报说明与03_会员运营周报,逐记录去重计算。")
        add("large-aug-amounts",
            "2026年8月青禾的实付金额、退款金额、优惠金额分别是多少?",
            ["payment_cents", "refund_cents", "discount_cents"],
            "2026-08-01", "2026-09-01",
            [la["payment_cents"], la["refund_cents"], la["discount_cents"]],
            SRC + " 依据01_订单日报说明与02_财务邮件,仅 paid 单计入、退款按原订单日期归属。")
        lf = audit.first_purchase_metrics(orders, *jul, cov[0], cov[1])
        lj = audit.order_metrics(orders, *jul)
        add("large-jul-first",
            "2026年7月青禾的观测期首购会员数、观测期首单数、观测期后续购买订单数、有效订单数分别是多少?",
            ["first_buyer_count", "first_order_count", "repeat_order_count", "valid_order_count"],
            "2026-07-01", "2026-08-01",
            [lf["first_buyer_count"], lf["first_order_count"], lf["repeat_order_count"],
             lj["valid_order_count"]],
            SRC + " 依据03_会员运营周报:覆盖期全历史确定首次再按窗口筛选;审核程序按"
                  "(ordered_at, order_id)排序逐账户确定首单。")
        lg = audit.monthly_general(orders, members, *aug)["2026-08"]
        add("large-aug-monthly",
            "2026年8月青禾的月内购买会员数、月内复购会员数、月内复购率是多少?",
            ["monthly_buyer_count", "monthly_repeat_buyer_count", "monthly_repeat_rate"],
            "2026-08-01", "2026-09-01",
            [lg["monthly_buyer_count"], lg["monthly_repeat_buyer_count"],
             lg["monthly_repeat_rate"]],
            SRC + " 依据03_会员运营周报,审核程序按账户×月聚合后判定(≥1、≥2)。")
        lp = audit.monthly_paid(orders, cards, *aug)["2026-08"]
        add("large-aug-paid",
            "2026年8月青禾的月末付费会员购买人数、月末付费会员有效订单数、月末付费会员净销售额、"
            "月末付费会员复购人数、月末付费会员复购率、月末付费会员订单均额分别是多少?",
            ["monthly_paid_buyer_count", "monthly_paid_order_count", "monthly_paid_sales_cents",
             "monthly_paid_repeat_buyer_count", "monthly_paid_repeat_rate",
             "monthly_paid_avg_order_value"],
            "2026-08-01", "2026-09-01",
            [lp["monthly_paid_buyer_count"], lp["monthly_paid_order_count"],
             lp["monthly_paid_sales_cents"], lp["monthly_paid_repeat_buyer_count"],
             lp["monthly_paid_repeat_rate"], lp["monthly_paid_avg_order_value"]],
            SRC + " 依据04_本期统计确认邮件与业务模型付费资格规则(月末判定、悦享年卡+家庭季卡、"
                  "端点 valid_from 当天起有效/valid_until 当天已无效/ended_at 当天起无效、"
                  "按账户多卡不重复),审核程序逐卡逐月判定后接回当月有效订单。")
        pj = audit.monthly_paid(orders, cards, *jul)["2026-07"]
        add("large-jul-paid",
            "2026年7月青禾的月末付费会员购买人数、月末付费会员有效订单数、月末付费会员净销售额分别是多少?",
            ["monthly_paid_buyer_count", "monthly_paid_order_count", "monthly_paid_sales_cents"],
            "2026-07-01", "2026-08-01",
            [pj["monthly_paid_buyer_count"], pj["monthly_paid_order_count"],
             pj["monthly_paid_sales_cents"]],
            SRC + " 与 large-aug-paid 同一资格规则,7月为对照月。")
        bs = audit.by_store(orders, *aug)
        add("large-aug-store-group",
            "2026年8月青禾各成交门店的有效订单数分别是多少?",
            ["valid_order_count"], "2026-08-01", "2026-09-01",
            [[s, bs[s]["valid_order_count"]] for s in sorted(bs)],
            SRC + " 依据01_订单日报说明按订单归属门店分组,审核程序逐门店统计。",
            group_by="store")
    with open(HERE / ("tests-large.json" if large else "tests.json"), "w") as fh:
        json.dump(cases, fh, ensure_ascii=False, indent=1)
    ids = {m for c in cases if c["expected"]["status"] == "ok"
           for m in c["expected"]["intent"]["metrics"]}
    targets = {t["id"] for t in json.load(open(ROOT / "customer/w03/targets.json"))}
    print(f"{len(cases)} cases; ok-case metric coverage {len(ids)}/38; missing: {sorted(targets - ids)}")


if __name__ == "__main__":
    run(large="--large" in sys.argv)
