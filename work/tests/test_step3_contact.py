"""Unit tests for Step 3: contact_constraints (synthetic small samples)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "platform"), str(ROOT / "customer/w05")]

import solution  # noqa: E402


def _cov_materials(**extra) -> dict:
    base = {
        "reference_date": "2026-09-01",
        "manifest": {"sha256": {"crm_member_export.csv": "h_crm", "pos_member_export.csv": "h_pos"}},
        "coverage": {
            "operational_verification": {
                "checked_topics": ["employee", "abnormal_identity"],
                "scope_files": ["crm_member_export.csv", "pos_member_export.csv"],
                "file_sha256": {"crm_member_export.csv": "h_crm", "pos_member_export.csv": "h_pos"},
            }
        },
        "business_basis.csv": [],
        "operational_verification.csv": [],
        "contact_scope_confirmation.csv": [],
        "小林工作账_勿扰名单.csv": [],
        "小林工作账_回访名单.csv": [],
        "crm_member_export.csv": [],
        "pos_member_export.csv": [],
    }
    base.update(extra)
    return base


def _crm_record(hy_id: str, row: int = 1, tag: str = "-") -> dict:
    return {
        "source_id": f"CRM:{hy_id}",
        "system": "CRM",
        "source_file": "crm_member_export.csv",
        "source_row": row,
        "registered_store": "1203",
        "raw": {"hy_id": hy_id, "nm": "测试", "mobile": "138****0000", "lv": "金卡", "reg_shop": "1203", "tag": tag},
    }


class TestContactConstraints(unittest.TestCase):
    def test_crm_space_and_slash_separated_tags_block_matching_channel_only(self):
        recs = [_crm_record("QH1", row=10, tag="生鲜偏好 勿打电话-投诉过/联系状态-周末才方便")]
        mat = _cov_materials()
        policy = solution.contact_constraints("U1", recs, mat, None)
        self.assertEqual(policy["status"], "ok")
        self.assertEqual(policy["channels"], {"telephone": "blocked", "sms": "no_known_restriction"})
        self.assertFalse(policy["actual_contact_authorized"])
        self.assertTrue(policy["verification_coverage_complete"])

    def test_dnd_pending_confirmation_marks_both_channels_unknown(self):
        recs = [_crm_record("QH2", row=2, tag="-")]
        mat = _cov_materials(
            **{
                "小林工作账_勿扰名单.csv": [{"会员号": "QH2", "原因": "其他", "登记日期": "2024-11-13"}],
                "business_basis.csv": [{"document_id": "DOC-PEND", "source_accounts": "CRM:QH2"}],
                "contact_scope_confirmation.csv": [
                    {
                        "record_id": "CS-PEND",
                        "source_id": "CRM:QH2",
                        "original_file": "小林工作账_勿扰名单.csv",
                        "original_row": "1",
                        "original_quote": "其他",
                        "channel_scope": "unknown",
                        "status": "pending",
                        "valid_from": "2026-08-31",
                        "valid_until": "2026-09-02",
                        "basis_file": "小林工作账_勿扰名单.csv",
                        "basis_row": "1",
                        "basis_document_id": "DOC-PEND",
                        "summary": "原条目未明确渠道，不能仅从原因推定",
                    }
                ],
            }
        )
        policy = solution.contact_constraints("U2", recs, mat, None)
        self.assertEqual(policy["status"], "unknown")
        self.assertEqual(policy["channels"], {"telephone": "unknown", "sms": "unknown"})
        self.assertEqual(policy["restriction_evidence"][0]["scope"], "unknown")
        self.assertFalse(policy["actual_contact_authorized"])

    def test_explicit_block_never_downgraded_by_unknown_on_other_source(self):
        recs = [
            _crm_record("QH3A", row=1, tag="勿打电话-本人要求"),
            _crm_record("QH3B", row=2, tag="-"),
        ]
        mat = _cov_materials(
            **{
                "小林工作账_勿扰名单.csv": [{"会员号": "QH3B", "原因": "投诉", "登记日期": "2024-12-01"}],
            }
        )
        policy = solution.contact_constraints("U3", recs, mat, None)
        self.assertEqual(policy["status"], "unknown")
        # telephone stays blocked; sms becomes unknown (never no_known_restriction)
        self.assertEqual(policy["channels"], {"telephone": "blocked", "sms": "unknown"})

    def test_followup_refuse_contact_blocks_all_channels(self):
        recs = [_crm_record("QH4", row=1, tag="-")]
        mat = _cov_materials(
            **{
                "小林工作账_回访名单.csv": [{"会员号": "QH4", "回访结果": "要求不再联系", "备注": "别再打"}],
            }
        )
        policy = solution.contact_constraints("U4", recs, mat, None)
        self.assertEqual(policy["channels"], {"telephone": "blocked", "sms": "blocked"})
        self.assertEqual(policy["status"], "ok")

    def test_employee_excludes_member_while_abnormal_excludes_only_account(self):
        recs = [_crm_record("QH5A", row=1), _crm_record("QH5B", row=2)]
        mat_emp = _cov_materials(
            **{
                "business_basis.csv": [{"document_id": "DOC-EMP", "source_accounts": "CRM:QH5A"}],
                "operational_verification.csv": [
                    {
                        "record_id": "OP-EMP",
                        "source_id": "CRM:QH5A",
                        "kind": "employee",
                        "conclusion": "confirmed",
                        "status": "current",
                        "scope": "member",
                        "valid_from": "2026-08-31",
                        "valid_until": "2026-09-02",
                        "basis_file": "business_basis.csv",
                        "basis_row": "1",
                        "basis_document_id": "DOC-EMP",
                        "summary": "员工登记复核结论",
                    }
                ],
            }
        )
        p_emp = solution.contact_constraints("U5", recs, mat_emp, None)
        self.assertTrue(p_emp["member_excluded"])
        self.assertEqual(p_emp["account_exclusions"], [])
        self.assertFalse(p_emp["all_source_accounts_excluded"])

        mat_abn = _cov_materials(
            **{
                "business_basis.csv": [{"document_id": "DOC-ABN", "source_accounts": "CRM:QH5A"}],
                "operational_verification.csv": [
                    {
                        "record_id": "OP-ABN",
                        "source_id": "CRM:QH5A",
                        "kind": "abnormal_identity",
                        "conclusion": "confirmed",
                        "status": "current",
                        "scope": "account",
                        "valid_from": "2026-08-31",
                        "valid_until": "2026-09-02",
                        "basis_file": "business_basis.csv",
                        "basis_row": "1",
                        "basis_document_id": "DOC-ABN",
                        "summary": "账户登记授权复核确认异常",
                    }
                ],
            }
        )
        p_abn = solution.contact_constraints("U5", recs, mat_abn, None)
        self.assertFalse(p_abn["member_excluded"])
        self.assertEqual(p_abn["account_exclusions"], ["CRM:QH5A"])
        self.assertFalse(p_abn["all_source_accounts_excluded"])

        p_abn_single = solution.contact_constraints("X5A", [recs[0]], mat_abn, None)
        self.assertFalse(p_abn_single["member_excluded"])
        self.assertEqual(p_abn_single["account_exclusions"], ["CRM:QH5A"])
        self.assertTrue(p_abn_single["all_source_accounts_excluded"])

    def test_missing_coverage_marks_status_unknown(self):
        recs = [_crm_record("QH6", row=1)]
        policy = solution.contact_constraints("U6", recs, {"reference_date": "2026-09-01"}, None)
        self.assertFalse(policy["verification_coverage_complete"])
        self.assertEqual(policy["status"], "unknown")
        self.assertFalse(policy["actual_contact_authorized"])


if __name__ == "__main__":
    unittest.main()
