"""E 组边界小样本测试（人工构造样本，不是青禾真实记录）。

覆盖：
1. 弱线索（同名、同脱敏手机号、同设备）不自动合并；
2. 有效依据冲突（same 与 different 矛盾）由框架标为 conflict，不强行合并；
3. 59 / 60 / 61 天最近有效购买边界，以及全额退款与已取消订单不计入有效购买；
4. 未知与零分别表达（无有效购买记录不等于 0 天，也不自动归入沉睡）。
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "platform"), str(ROOT / "customer/w05")]

import solution  # noqa: E402
from fde_product.w05.identity import resolve  # noqa: E402
from fde_product.w05.features import recent_purchase  # noqa: E402


def test_weak_clues_never_merge():
    # 小样本，人工构造，不是青禾记录
    accounts = [
        {
            "source_id": "CRM:SAMPLE_1",
            "system": "CRM",
            "source_file": "sample_crm.csv",
            "source_row": 1,
            "registered_store": "1203",
            "raw": {"hy_id": "SAMPLE_1", "nm": "王小明", "mobile": "138****8888", "reg_dev": "dev-abc"},
        },
        {
            "source_id": "POS:SAMPLE_1",
            "system": "POS",
            "source_file": "sample_pos.csv",
            "source_row": 1,
            "registered_store": None,
            "raw": {"pos_member_id": "SAMPLE_1", "name": "王小明", "mobile": "138****8888"},
        },
    ]
    materials = {"reference_date": "2026-09-01"}
    res = solution.identity_evidence(accounts, materials)
    assert res["evidence"] == [], f"弱线索不应产生合并边: {res['evidence']}"
    assert res["verified_singletons"] == [], "无有效覆盖声明时孤立账户不应直接认定为独立会员"
    mapping = resolve([a["source_id"] for a in accounts], res["evidence"], mapping_version=res["rule_version"], verified_singletons=res["verified_singletons"])
    assert all(m["status"] == "unresolved" and m["member_id"] is None for m in mapping)


def test_valid_evidence_conflict():
    # 小样本，人工构造，不是青禾记录
    accounts = [
        {"source_id": "CRM:C_CONF", "system": "CRM", "source_file": "sample.csv", "source_row": 1, "registered_store": "1203", "raw": {}},
        {"source_id": "POS:P_CONF", "system": "POS", "source_file": "sample_pos.csv", "source_row": 1, "registered_store": None, "raw": {}},
    ]
    materials = {
        "reference_date": "2026-09-01",
        "business_basis.csv": [
            {"document_id": "DOC-SAME", "source_accounts": "POS:P_CONF|CRM:C_CONF"},
            {"document_id": "DOC-DIFF", "source_accounts": "CRM:C_CONF|POS:P_CONF"},
        ],
        "migration_records.csv": [
            {
                "record_id": "MG-CONF-1",
                "pos_source_id": "POS:P_CONF",
                "crm_source_id": "CRM:C_CONF",
                "status": "success",
                "valid_from": "2025-03-15",
                "valid_until": "2026-09-02",
                "basis_file": "business_basis.csv",
                "basis_row": "1",
                "basis_document_id": "DOC-SAME",
            }
        ],
        "account_review_records.csv": [
            {
                "record_id": "RV-CONF-1",
                "left_source_id": "CRM:C_CONF",
                "right_source_id": "POS:P_CONF",
                "conclusion": "different",
                "status": "current",
                "valid_from": "2026-08-31",
                "valid_until": "2026-09-02",
                "basis_file": "business_basis.csv",
                "basis_row": "2",
                "basis_document_id": "DOC-DIFF",
            }
        ],
    }
    res = solution.identity_evidence(accounts, materials)
    assert len(res["evidence"]) == 2
    mapping = resolve([a["source_id"] for a in accounts], res["evidence"], mapping_version=res["rule_version"], verified_singletons=res["verified_singletons"])
    assert all(m["status"] == "conflict" and m["member_id"] is None for m in mapping)


def test_recency_59_60_61_and_refund_cancel_boundaries():
    # 小样本，人工构造，不是青禾记录
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE raw_members (member_id VARCHAR)")
    con.execute("CREATE TABLE raw_orders (member_id VARCHAR, ordered_at DATE, status VARCHAR, paid_cents BIGINT, refund_cents BIGINT)")
    for mid in ["M59", "M60", "M61", "M_NONE"]:
        con.execute("INSERT INTO raw_members VALUES (?)", [mid])
    sample_orders = [
        # M59: 2026-07-04 -> 59 days (not dormant)
        ("M59", date(2026, 7, 4), "paid", 10000, 0),
        # M60: 2026-07-03 -> 60 days (dormant), plus a cancelled order on 2026-08-20 (must be ignored)
        ("M60", date(2026, 7, 3), "paid", 10000, 0),
        ("M60", date(2026, 8, 20), "cancelled", 10000, 0),
        # M61: 2026-07-02 -> 61 days (dormant), plus a full-refund order on 2026-08-25 (must be ignored)
        ("M61", date(2026, 7, 2), "paid", 10000, 0),
        ("M61", date(2026, 8, 25), "paid", 10000, 10000),
        # M_NONE: only full refund & cancelled -> no effective purchase (unknown, NOT 0 and NOT dormant)
        ("M_NONE", date(2026, 8, 1), "paid", 5000, 5000),
        ("M_NONE", date(2026, 8, 5), "cancelled", 5000, 0),
    ]
    con.executemany("INSERT INTO raw_orders VALUES (?, ?, ?, ?, ?)", sample_orders)
    dataset = {"id": "synthetic-boundary-sample", "coverage": ["2024-09-01", "2026-09-01"]}

    r59 = recent_purchase(con, dataset, {"member_id": "M59", "reference_date": "2026-09-01", "dormant_days": 60})
    r60 = recent_purchase(con, dataset, {"member_id": "M60", "reference_date": "2026-09-01", "dormant_days": 60})
    r61 = recent_purchase(con, dataset, {"member_id": "M61", "reference_date": "2026-09-01", "dormant_days": 60})
    r_none = recent_purchase(con, dataset, {"member_id": "M_NONE", "reference_date": "2026-09-01", "dormant_days": 60})
    con.close()

    assert r59["status"] == "ok" and r59["dormant_days"] == 59 and r59["is_dormant"] is False, r59
    assert r60["status"] == "ok" and r60["dormant_days"] == 60 and r60["is_dormant"] is True, r60
    assert r61["status"] == "ok" and r61["dormant_days"] == 61 and r61["is_dormant"] is True, r61
    assert r_none["status"] == "unknown" and r_none["code"] == "NO_EFFECTIVE_PURCHASE_IN_EXPORT" and r_none["is_dormant"] is None, r_none


if __name__ == "__main__":
    test_weak_clues_never_merge()
    test_valid_evidence_conflict()
    test_recency_59_60_61_and_refund_cancel_boundaries()
    print("ALL BOUNDARY SMALL-SAMPLE TESTS PASSED (3/3)")
