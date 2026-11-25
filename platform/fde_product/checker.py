"""Public objective precheck; semantic judgement and final gates stay with tutors."""

import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker
from . import CONTRACT_VERSION


def schemas(root):
    return {name: json.loads((root / "contracts/w01" / (name + ".schema.json")).read_text())
            for name in ("environment_check", "product_fit_gap")}


def dry_run(root):
    for schema in schemas(root).values():
        Draft202012Validator.check_schema(schema)
    return {"status": "pass", "code": "SCHEMAS_LOADABLE", "scope": "schema_only_not_assignment"}


def precheck(root, submission):
    root, submission = Path(root), Path(submission).resolve()
    issues = []
    loaded = {}

    def issue(path, code, instruction):
        issues.append({"path": path, "code": code, "instruction": instruction})

    def read(relative):
        path = (submission / relative).resolve()
        if not path.is_relative_to(submission):
            issue(relative, "PATH_OUTSIDE_SUBMISSION", "将产出物保存在本次提交目录内。")
            return None
        if not path.is_file():
            issue(relative, "FILE_MISSING", "按任务书路径提供该文件。")
            return None
        if path.stat().st_size > 1_000_000:
            issue(relative, "FILE_TOO_LARGE", "W1 文本产出物应小于 1 MB。")
            return None
        try:
            return path.read_text(encoding="utf-8")
        except (UnicodeError, OSError):
            issue(relative, "FILE_UNREADABLE", "使用 UTF-8 保存文本，并确认文件可读。")
            return None

    for name, schema in schemas(root).items():
        rel = f"artifacts/w01/{name}.json"
        raw = read(rel)
        if raw is None:
            continue
        try:
            data = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except ValueError:
            issue(rel, "INVALID_JSON", "修正 JSON 语法；不接受 NaN 或 Infinity。")
            continue
        errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(data))
        for err in errors:
            # Do not echo student values (possibly pasted secrets) in error output.
            at = "/" + "/".join(map(str, err.absolute_path))
            issue(rel + at, "SCHEMA_" + err.validator.upper(), "对照版本化 schema 检查此字段的类型、取值或必填要求。")
        if not errors:
            loaded[name] = data

    env = loaded.get("environment_check")
    if env:
        for name, check in env["checks"].items():
            if check["status"] != "pass":
                issue("artifacts/w01/environment_check.json/checks/" + name, "ENV_NOT_READY", "完成该项实测；离线自检不代替真实模型接入。")
        if env["model_mode"] != "live":
            issue("artifacts/w01/environment_check.json/model_mode", "LIVE_MODEL_UNVERIFIED", "配置模型后执行带 --live 的自检。")

    fit = loaded.get("product_fit_gap")
    if fit:
        known = {c["id"] for c in json.loads((root / "product/capabilities.json").read_text())["capabilities"]}
        seen = set()
        for index, item in enumerate(fit["items"]):
            at = f"artifacts/w01/product_fit_gap.json/items/{index}"
            if item["id"] in seen:
                issue(at + "/id", "DUPLICATE_ID", "每条判断使用独立 ID。")
            seen.add(item["id"])
            if set(item["capability_ids"]) - known:
                issue(at + "/capability_ids", "UNKNOWN_CAPABILITY", "引用本版本能力矩阵中的 CAP ID；没有对应能力时留空并说明待核项。")
            if item["evidence_status"] != "unknown" and not item["evidence"]:
                issue(at + "/evidence", "EVIDENCE_REQUIRED", "已核实、转述或冲突状态应给出可定位依据。")
        if env and fit["product_version"] != env["product_version"]:
            issue("artifacts/w01/product_fit_gap.json/product_version", "VERSION_MISMATCH", "能力判断与环境自检应针对同一产品版本。")

    report = read("docs/w01/project_assessment.md")
    if report is not None and not report.strip():
        issue("docs/w01/project_assessment.md", "EMPTY_REPORT", "填写实际立项分析，内容质量由助教判读。")
    return {"contract_version": CONTRACT_VERSION, "scope": "public_precheck",
            "status": "needs_revision" if issues else "precheck_passed", "issues": issues,
            "human_review_required": ["fit-gap 分类与证据是否成立", "角色转述是否被误认作事实", "立项判断与承诺边界"],
            "final_gate": "not_determined"}
