"""Unit tests for Step 2: identity_evidence and member_attributes (synthetic small samples)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "platform"), str(ROOT / "customer/w05")]

import solution  # noqa: E402
from fde_product.w05.identity import resolve  # noqa: E402


def _make_account(
    source_id: str,
    *,
    system: str = "CRM",
    source_file: str = "crm_member_export.csv",
    source_row: int = 1,
    registered_store: str | None = "1203",
    raw: dict | None = None,
) -> dict:
    return {
        "source_id": source_id,
        "system": system,
        "source_file": source_file,
        "source_row": source_row,
        "registered_store": registered_store,
        "raw": raw or {},
    }


class TestIdentityEvidence(unittest.TestCase):
    def test_weak_clues_never_merge_without_records(self):
        accounts = [
            _make_account("CRM:A1", source_row=1, raw={"nm": "张三", "mobile": "138****0001"}),
            _make_account(
                "POS:P1",
                system="POS",
                source_file="pos_member_export.csv",
                source_row=1,
                registered_store=None,
                raw={"name": "张三", "mobile": "138****0001"},
            ),
        ]
        materials = {"reference_date": "2026-09-01"}
        res = solution.identity_evidence(accounts, materials)
        self.assertEqual(res["evidence"], [])
        self.assertEqual(res["verified_singletons"], [])

    def test_migration_accepts_only_active_success_with_valid_basis(self):
        accounts = [
            _make_account("CRM:C1", source_row=1),
            _make_account("POS:P1", system="POS", source_file="pos_member_export.csv", source_row=1, registered_store=None),
            _make_account("CRM:C2", source_row=2),
            _make_account("POS:P2", system="POS", source_file="pos_member_export.csv", source_row=2, registered_store=None),
        ]
        materials = {
            "reference_date": "2026-09-01",
            "business_basis.csv": [
                {"document_id": "DOC-1", "source_accounts": "POS:P1|CRM:C1"},
                {"document_id": "DOC-2", "source_accounts": "POS:P2|CRM:C2"},
            ],
            "migration_records.csv": [
                # Valid success
                {
                    "record_id": "MG-OK",
                    "pos_source_id": "POS:P1",
                    "crm_source_id": "CRM:C1",
                    "status": "success",
                    "valid_from": "2025-03-15",
                    "valid_until": "2026-09-02",
                    "basis_file": "business_basis.csv",
                    "basis_row": "1",
                    "basis_document_id": "DOC-1",
                },
                # Failed attempt
                {
                    "record_id": "MG-FAIL",
                    "pos_source_id": "POS:P1",
                    "crm_source_id": "CRM:C1",
                    "status": "failed",
                    "valid_from": "2025-03-15",
                    "valid_until": "2026-09-02",
                    "basis_file": "business_basis.csv",
                    "basis_row": "1",
                    "basis_document_id": "DOC-1",
                },
                # Expired (end exclusive: valid_until == reference_date is expired)
                {
                    "record_id": "MG-EXP",
                    "pos_source_id": "POS:P2",
                    "crm_source_id": "CRM:C2",
                    "status": "success",
                    "valid_from": "2025-03-15",
                    "valid_until": "2026-09-01",
                    "basis_file": "business_basis.csv",
                    "basis_row": "2",
                    "basis_document_id": "DOC-2",
                },
                # Bad basis (points to wrong document)
                {
                    "record_id": "MG-BAD-BASIS",
                    "pos_source_id": "POS:P2",
                    "crm_source_id": "CRM:C2",
                    "status": "success",
                    "valid_from": "2025-03-15",
                    "valid_until": "2026-09-02",
                    "basis_file": "business_basis.csv",
                    "basis_row": "1",
                    "basis_document_id": "DOC-1",
                },
            ],
        }
        res = solution.identity_evidence(accounts, materials)
        self.assertEqual([e["evidence_id"] for e in res["evidence"]], ["MG-OK"])
        finding_map = {f["record_id"]: f["reason"] for f in res["findings"]}
        self.assertEqual(finding_map["MG-FAIL"], "INACTIVE_OR_UNCONFIRMED_RECORD")
        self.assertEqual(finding_map["MG-EXP"], "INACTIVE_OR_UNCONFIRMED_RECORD")
        self.assertEqual(finding_map["MG-BAD-BASIS"], "UNVERIFIED_BASIS")

    def test_out_of_export_review_goes_to_findings_not_evidence(self):
        accounts = [_make_account("CRM:C1", source_row=1)]
        materials = {
            "reference_date": "2026-09-01",
            "business_basis.csv": [
                {"document_id": "DOC-OUT", "source_accounts": "CRM:C1|CRM:MISSING"},
            ],
            "account_review_records.csv": [
                {
                    "record_id": "RV-OUT",
                    "left_source_id": "CRM:C1",
                    "right_source_id": "CRM:MISSING",
                    "conclusion": "same",
                    "status": "current",
                    "valid_from": "2026-08-31",
                    "valid_until": "2026-09-02",
                    "basis_file": "business_basis.csv",
                    "basis_row": "1",
                    "basis_document_id": "DOC-OUT",
                }
            ],
        }
        res = solution.identity_evidence(accounts, materials)
        self.assertEqual(res["evidence"], [])
        self.assertEqual(len(res["findings"]), 1)
        self.assertEqual(res["findings"][0]["reason"], "OUT_OF_EXPORT_ACCOUNT")
        self.assertEqual(res["findings"][0]["missing_accounts"], ["CRM:MISSING"])

    def test_conflicting_same_and_different_edges_produce_conflict_status(self):
        accounts = [
            _make_account("CRM:C1", source_row=1),
            _make_account("POS:P1", system="POS", source_file="pos_member_export.csv", source_row=1, registered_store=None),
        ]
        materials = {
            "reference_date": "2026-09-01",
            "business_basis.csv": [
                {"document_id": "DOC-M", "source_accounts": "POS:P1|CRM:C1"},
                {"document_id": "DOC-R", "source_accounts": "CRM:C1|POS:P1"},
            ],
            "migration_records.csv": [
                {
                    "record_id": "MG-1",
                    "pos_source_id": "POS:P1",
                    "crm_source_id": "CRM:C1",
                    "status": "success",
                    "valid_from": "2025-03-15",
                    "valid_until": "2026-09-02",
                    "basis_file": "business_basis.csv",
                    "basis_row": "1",
                    "basis_document_id": "DOC-M",
                }
            ],
            "account_review_records.csv": [
                {
                    "record_id": "RV-DIFF",
                    "left_source_id": "CRM:C1",
                    "right_source_id": "POS:P1",
                    "conclusion": "different",
                    "status": "current",
                    "valid_from": "2026-08-31",
                    "valid_until": "2026-09-02",
                    "basis_file": "business_basis.csv",
                    "basis_row": "2",
                    "basis_document_id": "DOC-R",
                }
            ],
        }
        res = solution.identity_evidence(accounts, materials)
        mapping = resolve(
            [a["source_id"] for a in accounts],
            res["evidence"],
            mapping_version=res["rule_version"],
            verified_singletons=res["verified_singletons"],
        )
        self.assertTrue(all(m["status"] == "conflict" and m["member_id"] is None for m in mapping))

    def test_verified_singletons_excludes_abnormal_but_keeps_employee(self):
        accounts = [
            _make_account("CRM:NORMAL", source_row=1),
            _make_account("CRM:ABNORMAL", source_row=2),
            _make_account("CRM:STAFF", source_row=3),
        ]
        materials = {
            "reference_date": "2026-09-01",
            "manifest": {"sha256": {"crm_member_export.csv": "h1"}},
            "coverage": {
                "account_review": {
                    "scope_files": ["crm_member_export.csv"],
                    "file_sha256": {"crm_member_export.csv": "h1"},
                    "exceptions_file": "operational_verification.csv",
                }
            },
            "business_basis.csv": [
                {"document_id": "DOC-ABN", "source_accounts": "CRM:ABNORMAL"},
                {"document_id": "DOC-EMP", "source_accounts": "CRM:STAFF"},
            ],
            "operational_verification.csv": [
                {
                    "record_id": "OP-1",
                    "source_id": "CRM:ABNORMAL",
                    "kind": "abnormal_identity",
                    "conclusion": "confirmed",
                    "status": "current",
                    "scope": "account",
                    "valid_from": "2026-08-31",
                    "valid_until": "2026-09-02",
                    "basis_file": "business_basis.csv",
                    "basis_row": "1",
                    "basis_document_id": "DOC-ABN",
                },
                {
                    "record_id": "OP-2",
                    "source_id": "CRM:STAFF",
                    "kind": "employee",
                    "conclusion": "confirmed",
                    "status": "current",
                    "scope": "member",
                    "valid_from": "2026-08-31",
                    "valid_until": "2026-09-02",
                    "basis_file": "business_basis.csv",
                    "basis_row": "2",
                    "basis_document_id": "DOC-EMP",
                },
            ],
        }
        res = solution.identity_evidence(accounts, materials)
        self.assertEqual(res["verified_singletons"], ["CRM:NORMAL", "CRM:STAFF"])


class TestMemberAttributes(unittest.TestCase):
    def test_missing_markers_are_not_treated_as_conflicts(self):
        records = [
            _make_account("CRM:C1", source_row=1, registered_store="1203", raw={"nm": "张三", "mobile": "138****0001", "lv": "金卡", "reg_shop": "1203"}),
            _make_account("CRM:C2", source_row=2, registered_store="1203", raw={"nm": "NULL", "mobile": "-", "lv": "金卡", "reg_shop": "1203"}),
            _make_account("CRM:C3", source_row=3, registered_store="1203", raw={"nm": "无", "mobile": "", "lv": "金卡", "reg_shop": "1203"}),
        ]
        attrs = solution.member_attributes("U-TEST", records)
        self.assertEqual(attrs["display_name"], "张三")
        self.assertEqual(attrs["names"], ["张三"])
        self.assertEqual(attrs["tier"], "金卡")
        self.assertEqual(attrs["conflicts"], [])
        self.assertEqual(attrs["registered_stores"], ["1203"])

    def test_real_name_and_tier_conflicts_set_representative_none(self):
        records = [
            _make_account("CRM:C1", source_row=1, registered_store="1203", raw={"nm": "张浩慧", "mobile": "138****0001", "lv": "银卡", "reg_shop": "1203"}),
            _make_account("CRM:C2", source_row=2, registered_store="1004", raw={"nm": "张慧", "mobile": "139****0002", "lv": "金卡", "reg_shop": "1004"}),
        ]
        attrs = solution.member_attributes("U-CONFLICT", records)
        self.assertIsNone(attrs["display_name"])
        self.assertIsNone(attrs["tier"])
        self.assertEqual(attrs["names"], ["张浩慧", "张慧"])
        self.assertEqual(attrs["registered_stores"], ["1004", "1203"])
        conflict_fields = {c["field"]: c["values"] for c in attrs["conflicts"]}
        self.assertEqual(conflict_fields["name"], ["张浩慧", "张慧"])
        self.assertEqual(conflict_fields["tier"], ["银卡", "金卡"])
        self.assertEqual(conflict_fields["masked_mobile"], ["138****0001", "139****0002"])

    def test_pos_only_has_empty_registered_stores(self):
        records = [
            _make_account(
                "POS:P1",
                system="POS",
                source_file="pos_member_export.csv",
                source_row=5,
                registered_store=None,
                raw={"name": "李四", "mobile": "137****9999"},
            )
        ]
        attrs = solution.member_attributes("U-POS", records)
        self.assertEqual(attrs["display_name"], "李四")
        self.assertIsNone(attrs["tier"])
        self.assertEqual(attrs["registered_stores"], [])
        self.assertEqual(attrs["source_ids"], ["POS:P1"])


if __name__ == "__main__":
    unittest.main()
