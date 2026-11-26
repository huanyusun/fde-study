"""Customer W05 rules: identity evidence, member attributes, and contact constraints."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date

from fde_product.w05.records import current_records, verify_basis

RULE_VERSION = "qinghe-w05-rules-20261008.1"
MISSING_MARKERS = {"", "-", "--", "NULL", "null", "None", "N/A", "无", "暂无"}
_TAG_SPLIT_RE = re.compile(r"[,，;；/\s]+")


def _clean_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text in MISSING_MARKERS:
        return None
    return text


def _has_account_review_coverage(accounts: list[dict], materials: dict) -> bool:
    coverage = materials.get("coverage")
    if not isinstance(coverage, dict):
        return False
    account_review = coverage.get("account_review")
    if not isinstance(account_review, dict):
        return False
    scope_files = set(account_review.get("scope_files") or [])
    if not scope_files:
        return False
    present_files = {a.get("source_file") for a in accounts if a.get("source_file")}
    if present_files and not present_files <= scope_files:
        return False
    manifest_sha = (materials.get("manifest") or {}).get("sha256") or {}
    cov_sha = account_review.get("file_sha256") or {}
    if manifest_sha:
        for fn in scope_files:
            if not cov_sha.get(fn) or cov_sha.get(fn) != manifest_sha.get(fn):
                return False
    return True


def identity_evidence(accounts, materials):
    """Return accepted same/different/unresolved edges with source rows and rule version.

    Names, masked phones and devices alone never establish verified identity.
    """
    account_ids = {a["source_id"] for a in accounts}
    ref_date = materials["reference_date"]

    evidence: list[dict] = []
    findings: list[dict] = []
    same_linked: set[str] = set()

    # 1. Migration records: only reference-date active 'success' records with verifiable basis
    mig_rows = materials.get("migration_records.csv", [])
    valid_mig, ignored_mig = current_records(mig_rows, ref_date, states=("success",))
    for item in ignored_mig:
        findings.append({
            "record_id": item["record_id"],
            "source_file": "migration_records.csv",
            "source_row": item["source_row"],
            "reason": item["reason"],
        })
    for row_no, rec in valid_mig:
        left = rec.get("pos_source_id", "")
        right = rec.get("crm_source_id", "")
        if left not in account_ids or right not in account_ids:
            findings.append({
                "record_id": rec["record_id"],
                "source_file": "migration_records.csv",
                "source_row": row_no,
                "reason": "OUT_OF_EXPORT_ACCOUNT",
                "left": left,
                "right": right,
                "missing_accounts": [x for x in (left, right) if x not in account_ids],
            })
            continue
        if left == right:
            findings.append({
                "record_id": rec["record_id"],
                "source_file": "migration_records.csv",
                "source_row": row_no,
                "reason": "SELF_REFERENCE",
            })
            continue
        if not verify_basis(rec, materials):
            findings.append({
                "record_id": rec["record_id"],
                "source_file": "migration_records.csv",
                "source_row": row_no,
                "reason": "UNVERIFIED_BASIS",
            })
            continue
        evidence.append({
            "left": left,
            "right": right,
            "relation": "same",
            "evidence_id": rec["record_id"],
            "source_file": "migration_records.csv",
            "source_row": row_no,
            "rule_version": RULE_VERSION,
        })
        same_linked.update((left, right))

    # 2. Account review records: reference-date active 'current' records with verifiable basis
    rev_rows = materials.get("account_review_records.csv", [])
    valid_rev, ignored_rev = current_records(rev_rows, ref_date, states=("current",))
    for item in ignored_rev:
        findings.append({
            "record_id": item["record_id"],
            "source_file": "account_review_records.csv",
            "source_row": item["source_row"],
            "reason": item["reason"],
        })
    for row_no, rec in valid_rev:
        left = rec.get("left_source_id", "")
        right = rec.get("right_source_id", "")
        conclusion = rec.get("conclusion", "")
        if left not in account_ids or right not in account_ids:
            findings.append({
                "record_id": rec["record_id"],
                "source_file": "account_review_records.csv",
                "source_row": row_no,
                "reason": "OUT_OF_EXPORT_ACCOUNT",
                "left": left,
                "right": right,
                "missing_accounts": [x for x in (left, right) if x not in account_ids],
            })
            continue
        if left == right:
            findings.append({
                "record_id": rec["record_id"],
                "source_file": "account_review_records.csv",
                "source_row": row_no,
                "reason": "SELF_REFERENCE",
            })
            continue
        if not verify_basis(rec, materials):
            findings.append({
                "record_id": rec["record_id"],
                "source_file": "account_review_records.csv",
                "source_row": row_no,
                "reason": "UNVERIFIED_BASIS",
            })
            continue
        if conclusion not in ("same", "different", "unresolved"):
            findings.append({
                "record_id": rec["record_id"],
                "source_file": "account_review_records.csv",
                "source_row": row_no,
                "reason": "UNKNOWN_CONCLUSION",
                "conclusion": conclusion,
            })
            relation = "unresolved"
        else:
            relation = conclusion
        evidence.append({
            "left": left,
            "right": right,
            "relation": relation,
            "evidence_id": rec["record_id"],
            "source_file": "account_review_records.csv",
            "source_row": row_no,
            "rule_version": RULE_VERSION,
        })
        if relation == "same":
            same_linked.update((left, right))

    # 3. Verified singletons: only when account_review coverage applies, excluding confirmed abnormal_identity
    verified_singletons: list[str] = []
    if _has_account_review_coverage(accounts, materials):
        exceptions_file = (
            materials["coverage"]["account_review"].get("exceptions_file")
            or "operational_verification.csv"
        )
        opv_rows = materials.get(exceptions_file, [])
        valid_opv, _ = current_records(opv_rows, ref_date, states=("current",))
        abnormal_ids = {
            rec["source_id"]
            for _, rec in valid_opv
            if rec.get("kind") == "abnormal_identity"
            and rec.get("conclusion") == "confirmed"
            and verify_basis(rec, materials)
        }
        verified_singletons = sorted(
            sid for sid in account_ids
            if sid not in abnormal_ids and sid not in same_linked
        )

    return {
        "rule_version": RULE_VERSION,
        "evidence": evidence,
        "verified_singletons": verified_singletons,
        "findings": findings,
    }


def member_attributes(member_id, source_records):
    """Return attributes/conflicts with provenance; preserve multi-store relationships.

    POS accounts without a registration store stay unknown (never backfilled from purchase stores).
    Missing placeholders ('', '-', 'NULL', '无') are treated as genuine missing values, not conflicts.
    """
    names: list[str] = []
    masked_mobiles: list[str] = []
    tiers: list[str] = []
    registered_stores: set[str] = set()
    sources: list[dict] = []

    ordered_records = sorted(source_records, key=lambda r: r["source_id"])
    for rec in ordered_records:
        sid = rec["source_id"]
        sys_name = rec["system"]
        sfile = rec["source_file"]
        srow = rec["source_row"]
        raw = rec.get("raw") or {}

        name_field = "nm" if sys_name == "CRM" else "name"
        raw_name = raw.get(name_field)
        sources.append({
            "source_id": sid,
            "source_file": sfile,
            "source_row": srow,
            "field": name_field,
            "raw_value": raw_name,
        })
        clean_name = _clean_text(raw_name)
        if clean_name and clean_name not in names:
            names.append(clean_name)

        raw_mobile = raw.get("mobile")
        sources.append({
            "source_id": sid,
            "source_file": sfile,
            "source_row": srow,
            "field": "mobile",
            "raw_value": raw_mobile,
        })
        clean_mobile = _clean_text(raw_mobile)
        if clean_mobile and clean_mobile not in masked_mobiles:
            masked_mobiles.append(clean_mobile)

        if sys_name == "CRM":
            raw_tier = raw.get("lv")
            sources.append({
                "source_id": sid,
                "source_file": sfile,
                "source_row": srow,
                "field": "lv",
                "raw_value": raw_tier,
            })
            clean_tier = _clean_text(raw_tier)
            if clean_tier and clean_tier not in tiers:
                tiers.append(clean_tier)

        reg_store = rec.get("registered_store")
        if reg_store:
            registered_stores.add(reg_store)
            sources.append({
                "source_id": sid,
                "source_file": sfile,
                "source_row": srow,
                "field": "reg_shop",
                "raw_value": raw.get("reg_shop"),
            })

    conflicts: list[dict] = []
    if len(names) == 1:
        display_name = names[0]
    else:
        display_name = None
        if len(names) > 1:
            conflicts.append({"field": "name", "values": names})

    if len(tiers) == 1:
        tier = tiers[0]
    else:
        tier = None
        if len(tiers) > 1:
            conflicts.append({"field": "tier", "values": tiers})

    if len(masked_mobiles) > 1:
        conflicts.append({"field": "masked_mobile", "values": masked_mobiles})

    return {
        "display_name": display_name,
        "names": names,
        "masked_mobiles": masked_mobiles,
        "tier": tier,
        "conflicts": conflicts,
        "source_ids": [r["source_id"] for r in ordered_records],
        "registered_stores": sorted(registered_stores),
        "sources": sources,
    }


def _has_operational_verification_coverage(source_records: list[dict], materials: dict) -> bool:
    coverage = materials.get("coverage")
    if not isinstance(coverage, dict):
        return False
    op_cov = coverage.get("operational_verification")
    if not isinstance(op_cov, dict):
        return False
    topics = set(op_cov.get("checked_topics") or [])
    if not {"employee", "abnormal_identity"} <= topics:
        return False
    scope_files = set(op_cov.get("scope_files") or [])
    if not scope_files:
        return False
    present_files = {r.get("source_file") for r in source_records if r.get("source_file")}
    if present_files and not present_files <= scope_files:
        return False
    manifest_sha = (materials.get("manifest") or {}).get("sha256") or {}
    cov_sha = op_cov.get("file_sha256") or {}
    if manifest_sha:
        for fn in scope_files:
            if not cov_sha.get(fn) or cov_sha.get(fn) != manifest_sha.get(fn):
                return False
    return True


def _build_contact_index(materials: dict) -> dict:
    ref_date = materials.get("reference_date") or "2026-09-01"
    opv_rows = materials.get("operational_verification.csv") or []
    csc_rows = materials.get("contact_scope_confirmation.csv") or []
    dnd_rows = materials.get("小林工作账_勿扰名单.csv") or []
    hf_rows = materials.get("小林工作账_回访名单.csv") or []

    cache_key = (ref_date, len(opv_rows), len(csc_rows), len(dnd_rows), len(hf_rows))
    cached = materials.get("_w05_contact_index")
    if cached and cached.get("key") == cache_key:
        return cached

    ref = date.fromisoformat(ref_date)

    # 1. Operational verification (confirmed vs pending/suspected)
    opv_by_source: dict[str, list[dict]] = defaultdict(list)
    active_opv, _ = current_records(opv_rows, ref_date, states=("current", "pending"))
    for row_no, rec in active_opv:
        sid = rec.get("source_id", "")
        if not sid:
            continue
        is_confirmed = (
            rec.get("status") == "current"
            and rec.get("conclusion") == "confirmed"
            and verify_basis(rec, materials)
        )
        verification = "confirmed" if is_confirmed else (
            "suspected" if rec.get("conclusion") == "suspected" else "unknown"
        )
        opv_by_source[sid].append({
            "source_id": sid,
            "kind": rec.get("kind") or "abnormal_identity",
            "verification": verification,
            "scope": rec.get("scope") or "account",
            "record_id": rec.get("record_id", ""),
            "source_file": "operational_verification.csv",
            "source_row": row_no,
            "quote": rec.get("summary") or f"{rec.get('kind')}:{rec.get('conclusion')}",
            "rule_version": RULE_VERSION,
        })

    # 2. Contact scope confirmation (active current & pending)
    csc_by_orig: dict[tuple[str, str, int], list[tuple[int, dict, bool]]] = defaultdict(list)
    csc_by_source: dict[str, list[tuple[int, dict, bool]]] = defaultdict(list)
    for row_no, rec in enumerate(csc_rows, 1):
        try:
            effective = date.fromisoformat(rec["valid_from"]) <= ref < date.fromisoformat(rec["valid_until"])
        except (ValueError, KeyError):
            effective = False
        if not effective:
            continue
        basis_ok = verify_basis(rec, materials)
        sid = rec.get("source_id", "")
        orig_file = rec.get("original_file", "")
        try:
            orig_row = int(rec.get("original_row", 0))
        except ValueError:
            orig_row = 0
        entry = (row_no, rec, basis_ok)
        if sid and orig_file and orig_row >= 1:
            csc_by_orig[(sid, orig_file, orig_row)].append(entry)
        if sid:
            csc_by_source[sid].append(entry)

    # 3. Xiao Lin DND workbook
    dnd_by_source: dict[str, list[tuple[int, dict]]] = defaultdict(list)
    for row_no, rec in enumerate(dnd_rows, 1):
        hid = (rec.get("会员号") or "").strip()
        if hid:
            dnd_by_source[f"CRM:{hid}"].append((row_no, rec))

    # 4. Xiao Lin follow-up workbook (only explicit "不再联系" / "请勿再联系")
    hf_by_source: dict[str, list[tuple[int, dict]]] = defaultdict(list)
    for row_no, rec in enumerate(hf_rows, 1):
        hid = (rec.get("会员号") or "").strip()
        res_text = (rec.get("回访结果") or "").strip()
        if hid and ("不再联系" in res_text or "请勿再联系" in res_text):
            hf_by_source[f"CRM:{hid}"].append((row_no, rec))

    index = {
        "key": cache_key,
        "opv_by_source": opv_by_source,
        "csc_by_orig": csc_by_orig,
        "csc_by_source": csc_by_source,
        "dnd_by_source": dnd_by_source,
        "hf_by_source": hf_by_source,
    }
    materials["_w05_contact_index"] = index
    return index


def contact_constraints(member_id, source_records, materials, channel):
    """Apply confirmed customer rules to structured evidence; unknown is not permission.

    - Employee exclusions (scope='member') apply to the unified member.
    - Abnormal identity exclusions (scope='account') apply only to the specified source account.
    - Contact restrictions from CRM notes, DND workbook + confirmation records, and follow-up
      records are merged across all source accounts; explicit block is never downgraded to unknown,
      and unknown is never treated as permission.
    - actual_contact_authorized is always False in this phase.
    """
    ordered_records = sorted(source_records, key=lambda r: r["source_id"])
    source_ids = [r["source_id"] for r in ordered_records]
    index = _build_contact_index(materials)
    coverage_ok = _has_operational_verification_coverage(ordered_records, materials)

    member_excluded = False
    account_exclusions: list[str] = []
    confirmed_exclusions: list[dict] = []
    pending_verifications: list[dict] = []

    for sid in source_ids:
        for item in index["opv_by_source"].get(sid, []):
            if item["verification"] == "confirmed":
                confirmed_exclusions.append(item)
                if item["scope"] == "member":
                    member_excluded = True
                else:
                    if sid not in account_exclusions:
                        account_exclusions.append(sid)
            else:
                pending_verifications.append(item)

    all_source_accounts_excluded = bool(source_ids) and all(
        sid in account_exclusions for sid in source_ids
    )

    restriction_evidence: list[dict] = []
    seen_evidence: set[tuple[str, str, int, str, str]] = set()

    def _add_restriction(
        source_id: str,
        scope: str,
        source_file: str,
        source_row: int,
        quote: str,
        confirmation_records: list[dict] | None = None,
    ) -> None:
        key = (source_id, source_file, source_row, scope, quote)
        if key in seen_evidence:
            return
        seen_evidence.add(key)
        entry = {
            "source_id": source_id,
            "scope": scope,
            "source_file": source_file,
            "source_row": source_row,
            "quote": quote,
            "rule_version": RULE_VERSION,
        }
        if confirmation_records:
            entry["confirmation_records"] = confirmation_records
        restriction_evidence.append(entry)

    # A. CRM tags/notes restrictions (explicit prefixes from W04 R7 + W05 contact rules)
    for rec in ordered_records:
        if rec.get("system") != "CRM":
            continue
        raw = rec.get("raw") or {}
        tag_text = (raw.get("tag") or "").strip()
        if not tag_text or tag_text in MISSING_MARKERS:
            continue
        for token in _TAG_SPLIT_RE.split(tag_text):
            tok = token.strip()
            if not tok:
                continue
            if "请勿再联系" in tok or "不再联系" in tok:
                _add_restriction(rec["source_id"], "all", rec["source_file"], rec["source_row"], tok)
            elif tok.startswith("勿打电话"):
                _add_restriction(rec["source_id"], "telephone", rec["source_file"], rec["source_row"], tok)
            elif tok.startswith("勿发短信"):
                _add_restriction(rec["source_id"], "sms", rec["source_file"], rec["source_row"], tok)

    # B. Xiao Lin DND workbook + contact_scope_confirmation.csv
    handled_csc_rows: set[int] = set()
    for sid in source_ids:
        for dnd_row_no, dnd_rec in index["dnd_by_source"].get(sid, []):
            reason = (dnd_rec.get("原因") or "").strip() or "勿扰登记"
            matches = index["csc_by_orig"].get((sid, "小林工作账_勿扰名单.csv", dnd_row_no), [])
            if not matches:
                _add_restriction(sid, "unknown", "小林工作账_勿扰名单.csv", dnd_row_no, reason)
                continue
            for csc_row_no, conf, basis_ok in matches:
                handled_csc_rows.add(csc_row_no)
                conf_ref = [{
                    "record_id": conf["record_id"],
                    "source_file": "contact_scope_confirmation.csv",
                    "source_row": csc_row_no,
                    "status": conf.get("status"),
                    "channel_scope": conf.get("channel_scope"),
                    "basis_file": conf.get("basis_file"),
                    "basis_row": conf.get("basis_row"),
                    "summary": conf.get("summary"),
                }]
                ch_scope = conf.get("channel_scope", "unknown")
                if conf.get("status") == "current" and basis_ok and ch_scope in {"all", "telephone", "sms"}:
                    _add_restriction(
                        sid,
                        ch_scope,
                        "小林工作账_勿扰名单.csv",
                        dnd_row_no,
                        conf.get("original_quote") or reason,
                        confirmation_records=conf_ref,
                    )
                else:
                    _add_restriction(
                        sid,
                        "unknown",
                        "小林工作账_勿扰名单.csv",
                        dnd_row_no,
                        conf.get("original_quote") or reason,
                        confirmation_records=conf_ref,
                    )

        # Any standalone confirmation records not linked to a DND row
        for csc_row_no, conf, basis_ok in index["csc_by_source"].get(sid, []):
            if csc_row_no in handled_csc_rows:
                continue
            conf_ref = [{
                "record_id": conf["record_id"],
                "source_file": "contact_scope_confirmation.csv",
                "source_row": csc_row_no,
                "status": conf.get("status"),
                "channel_scope": conf.get("channel_scope"),
                "basis_file": conf.get("basis_file"),
                "basis_row": conf.get("basis_row"),
                "summary": conf.get("summary"),
            }]
            ch_scope = conf.get("channel_scope", "unknown")
            orig_file = conf.get("original_file") or "contact_scope_confirmation.csv"
            try:
                orig_row = int(conf.get("original_row") or csc_row_no)
            except ValueError:
                orig_row = csc_row_no
            quote = conf.get("original_quote") or conf.get("summary") or "补充确认限制"
            if conf.get("status") == "current" and basis_ok and ch_scope in {"all", "telephone", "sms"}:
                _add_restriction(sid, ch_scope, orig_file, orig_row, quote, confirmation_records=conf_ref)
            else:
                _add_restriction(sid, "unknown", orig_file, orig_row, quote, confirmation_records=conf_ref)

        # C. Xiao Lin follow-up workbook explicit "要求不再联系"
        for hf_row_no, hf_rec in index["hf_by_source"].get(sid, []):
            res_text = (hf_rec.get("回访结果") or "").strip()
            _add_restriction(sid, "all", "小林工作账_回访名单.csv", hf_row_no, res_text)

    scopes = {e["scope"] for e in restriction_evidence}
    channels = {}
    for ch in ("telephone", "sms"):
        if "all" in scopes or ch in scopes:
            channels[ch] = "blocked"
        elif "unknown" in scopes:
            channels[ch] = "unknown"
        else:
            channels[ch] = "no_known_restriction"

    has_unknown_channel = any(v == "unknown" for v in channels.values()) if channel is None else (
        channels.get(channel) == "unknown" if channel in channels else any(v == "unknown" for v in channels.values())
    )
    status = "unknown" if (pending_verifications or has_unknown_channel or not coverage_ok) else "ok"

    return {
        "member_id": member_id,
        "status": status,
        "channels": channels,
        "restriction_evidence": restriction_evidence,
        "member_excluded": member_excluded,
        "account_exclusions": sorted(account_exclusions),
        "all_source_accounts_excluded": all_source_accounts_excluded,
        "confirmed_exclusions": confirmed_exclusions,
        "pending_verifications": pending_verifications,
        "verification_coverage_complete": coverage_ok,
        "actual_contact_authorized": False,
    }
