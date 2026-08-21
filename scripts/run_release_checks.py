#!/usr/bin/env python3
"""Run Manju release metadata checks and deterministic mechanical regressions.

This gate deliberately does not judge semantic, cinematic, or generated-video
quality. Those decisions remain with the structured oracle review and real model
forward tests described by the evaluation suite.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


MIN_CASES = 9
MIN_MUTATIONS = 20
MIN_VALIDITY_CONTROLS = 2
ORACLE_LIST_FIELDS = (
    "must_preserve",
    "must_not_invent",
    "critical_failures",
    "allowed_variants",
)
P0_SEVERITIES = {"p0", "critical"}
ALLOWED_MUTATION_SEVERITIES = {"p0", "p1", "p2", "p3", "critical", "major", "minor"}
QUALITY_DIMENSIONS = {"A", "B", "C", "D", "E", "F", "G"}
SCOPE_NOTE = (
    "This gate checks release metadata structure and deterministic mechanical "
    "regressions only; it does not judge semantic, cinematic, or generated-video quality."
)


@dataclass
class ManifestResult:
    path: str
    ok: bool = False
    case_count: int = 0
    mutation_count: int = 0
    validity_control_count: int = 0
    canonical_response_count: int = 0
    p0_mutation_count: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class RegressionResult:
    command: list[str]
    ok: bool = False
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    error: str | None = None


class DuplicateJSONKeyError(ValueError):
    """Raised when a JSON object repeats a key and would silently overwrite data."""


def reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise DuplicateJSONKeyError(f"JSON 对象存在重复键：{key}")
        value[key] = item
    return value


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def require_keys(
    value: dict[str, Any], keys: tuple[str, ...], location: str, errors: list[str]
) -> None:
    for key in keys:
        if key not in value:
            errors.append(f"{location} 缺少必填字段：{key}")


def validate_string_list(
    value: Any, location: str, errors: list[str], *, allow_empty: bool = False
) -> None:
    if not isinstance(value, list):
        errors.append(f"{location} 必须是字符串数组")
        return
    if not allow_empty and not value:
        errors.append(f"{location} 不得为空")
        return
    for index, item in enumerate(value):
        if not nonempty_string(item):
            errors.append(f"{location}[{index}] 必须是非空字符串")


def validate_manifest(path: Path) -> ManifestResult:
    result = ManifestResult(path=str(path))
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicate_json_keys,
        )
    except OSError as exc:
        result.errors.append(f"无法读取 manifest：{exc}")
        return result
    except json.JSONDecodeError as exc:
        result.errors.append(
            f"manifest JSON 无法解析：第 {exc.lineno} 行第 {exc.colno} 列：{exc.msg}"
        )
        return result
    except DuplicateJSONKeyError as exc:
        result.errors.append(f"manifest JSON 无法解析：{exc}")
        return result

    if not isinstance(payload, dict):
        result.errors.append("manifest 顶层必须是 JSON 对象")
        return result

    errors = result.errors
    require_keys(
        payload,
        (
            "schema_version",
            "suite_id",
            "purpose",
            "evaluation_contract",
            "canonical_responses",
            "cases",
            "mutations",
            "validity_controls",
        ),
        "manifest",
        errors,
    )
    for key in ("schema_version", "suite_id", "purpose"):
        if key in payload and not nonempty_string(payload[key]):
            errors.append(f"manifest.{key} 必须是非空字符串")
    if "canonical_responses" in payload and not nonempty_string(
        payload["canonical_responses"]
    ):
        errors.append("manifest.canonical_responses 必须是非空字符串")

    contract = payload.get("evaluation_contract")
    if not isinstance(contract, dict):
        errors.append("manifest.evaluation_contract 必须是对象")
    else:
        require_keys(
            contract,
            ("candidate_artifact", "source_resolution_rules", "shared_pass_gate", "oracle_fields"),
            "manifest.evaluation_contract",
            errors,
        )
        if "candidate_artifact" in contract and not nonempty_string(
            contract["candidate_artifact"]
        ):
            errors.append("manifest.evaluation_contract.candidate_artifact 必须是非空字符串")
        for key in ("source_resolution_rules", "shared_pass_gate"):
            if key in contract:
                validate_string_list(
                    contract[key], f"manifest.evaluation_contract.{key}", errors
                )
        oracle_fields = contract.get("oracle_fields")
        if not isinstance(oracle_fields, dict):
            errors.append("manifest.evaluation_contract.oracle_fields 必须是对象")
        else:
            require_keys(
                oracle_fields,
                ORACLE_LIST_FIELDS,
                "manifest.evaluation_contract.oracle_fields",
                errors,
            )
            for key in ORACLE_LIST_FIELDS:
                if key in oracle_fields and not nonempty_string(oracle_fields[key]):
                    errors.append(
                        f"manifest.evaluation_contract.oracle_fields.{key} 必须是非空字符串"
                    )

    cases = payload.get("cases")
    case_ids: set[str] = set()
    duplicate_case_ids: set[str] = set()
    expected_outcomes: set[str] = set()
    case_outcomes: dict[str, str] = {}
    operations: set[str] = set()
    task_kinds: set[str] = set()
    diagnostic_bases: set[str] = set()
    if not isinstance(cases, list):
        errors.append("manifest.cases 必须是数组")
        cases = []
    result.case_count = len(cases)
    if len(cases) < MIN_CASES:
        errors.append(f"manifest.cases 至少需要 {MIN_CASES} 项，当前为 {len(cases)} 项")

    for index, case in enumerate(cases):
        location = f"manifest.cases[{index}]"
        if not isinstance(case, dict):
            errors.append(f"{location} 必须是对象")
            continue
        require_keys(case, ("id", "title", "operation", "task_kind", "input", "oracle"), location, errors)
        case_id = case.get("id")
        if not nonempty_string(case_id):
            errors.append(f"{location}.id 必须是非空字符串")
        elif case_id in case_ids:
            duplicate_case_ids.add(case_id)
        else:
            case_ids.add(case_id)
        for key in ("title", "operation", "task_kind"):
            if key in case and not nonempty_string(case[key]):
                errors.append(f"{location}.{key} 必须是非空字符串")
        operation = case.get("operation")
        normalized_operation = ""
        if nonempty_string(operation):
            normalized_operation = operation.strip().lower()
            operations.add(normalized_operation)
            if normalized_operation not in {"compile", "diagnose", "revise"}:
                errors.append(f"{location}.operation 必须是 compile、diagnose 或 revise")
        if nonempty_string(case.get("task_kind")):
            task_kinds.add(case["task_kind"].strip().lower())
            if case["task_kind"].strip().lower() not in {"generation", "extension"}:
                errors.append(f"{location}.task_kind 必须是 generation 或 extension")
        if "input" in case and (not isinstance(case["input"], dict) or not case["input"]):
            errors.append(f"{location}.input 必须是非空对象")
        if normalized_operation == "diagnose" and isinstance(case.get("input"), dict):
            diagnostic_basis = case["input"].get("diagnostic_basis")
            normalized_basis = (
                diagnostic_basis.strip() if isinstance(diagnostic_basis, str) else ""
            )
            if normalized_basis not in {"prompt_preflight", "observed_failure"}:
                errors.append(
                    f"{location}.input.diagnostic_basis 必须是 prompt_preflight 或 observed_failure"
                )
            else:
                diagnostic_bases.add(normalized_basis)

        oracle = case.get("oracle")
        if not isinstance(oracle, dict):
            errors.append(f"{location}.oracle 必须是对象")
            continue
        require_keys(oracle, ("expected_outcome", *ORACLE_LIST_FIELDS), f"{location}.oracle", errors)
        outcome = oracle.get("expected_outcome")
        if not nonempty_string(outcome) or outcome.upper() not in {"PROMPT", "BLOCK", "REPORT"}:
            errors.append(f"{location}.oracle.expected_outcome 必须是 PROMPT、BLOCK 或 REPORT")
        else:
            normalized_outcome = outcome.upper()
            expected_outcomes.add(normalized_outcome)
            if nonempty_string(case_id):
                case_outcomes[case_id] = normalized_outcome
            allowed_outcomes = {
                "compile": {"PROMPT", "BLOCK"},
                "diagnose": {"REPORT", "BLOCK"},
                "revise": {"PROMPT", "BLOCK"},
            }
            if (
                normalized_operation in allowed_outcomes
                and normalized_outcome not in allowed_outcomes[normalized_operation]
            ):
                allowed = " 或 ".join(sorted(allowed_outcomes[normalized_operation]))
                errors.append(
                    f"{location} 的 operation={normalized_operation} 只允许 expected_outcome={allowed}"
                )
        for key in ORACLE_LIST_FIELDS:
            if key in oracle:
                validate_string_list(oracle[key], f"{location}.oracle.{key}", errors)

    for case_id in sorted(duplicate_case_ids):
        errors.append(f"case id 重复：{case_id}")
    if cases and "PROMPT" not in expected_outcomes:
        errors.append("manifest.cases 至少需要一个 expected_outcome=PROMPT 的案例")
    if cases and "BLOCK" not in expected_outcomes:
        errors.append("manifest.cases 至少需要一个 expected_outcome=BLOCK 的案例")
    if cases and "REPORT" not in expected_outcomes:
        errors.append("manifest.cases 至少需要一个 expected_outcome=REPORT 的案例")
    if cases and "extension" not in task_kinds:
        errors.append("manifest.cases 至少需要一个 task_kind=extension 的案例")
    for required_operation in ("compile", "diagnose", "revise"):
        if cases and required_operation not in operations:
            errors.append(f"manifest.cases 至少需要一个 operation={required_operation} 的案例")
    for required_basis in ("prompt_preflight", "observed_failure"):
        if cases and required_basis not in diagnostic_bases:
            errors.append(
                "manifest.cases 至少需要一个 diagnose 案例使用 "
                f"diagnostic_basis={required_basis}"
            )

    canonical_reference = payload.get("canonical_responses")
    if nonempty_string(canonical_reference):
        eval_root = path.parent.resolve()
        canonical_path = (path.parent / canonical_reference).resolve()
        if canonical_path != eval_root and eval_root not in canonical_path.parents:
            errors.append("manifest.canonical_responses 必须位于 evals 目录内")
        elif not canonical_path.is_file():
            errors.append(
                f"manifest.canonical_responses 文件不存在：{canonical_reference}"
            )
        else:
            try:
                canonical_text = canonical_path.read_text(encoding="utf-8")
            except OSError as exc:
                errors.append(f"无法读取 canonical responses：{exc}")
            else:
                heading_matches = list(
                    re.finditer(
                        r"(?m)^# (C\d{2}_[A-Za-z0-9_]+)[ \t]*$",
                        canonical_text,
                    )
                )
                canonical_ids = [match.group(1) for match in heading_matches]
                result.canonical_response_count = len(canonical_ids)
                expected_order = [
                    case.get("id")
                    for case in cases
                    if isinstance(case, dict) and nonempty_string(case.get("id"))
                ]
                if canonical_ids != expected_order:
                    errors.append(
                        "canonical responses 的 case 顺序必须与 manifest.cases 一致"
                    )
                for case_id in sorted(case_ids):
                    count = canonical_ids.count(case_id)
                    if count != 1:
                        errors.append(
                            "canonical responses 中 "
                            f"{case_id} 应出现一次，当前为 {count} 次"
                        )
                for unknown_id in sorted(set(canonical_ids) - case_ids):
                    errors.append(
                        f"canonical responses 含未知 case 标题：{unknown_id}"
                    )
                for index, match in enumerate(heading_matches):
                    case_id = match.group(1)
                    body_start = match.end()
                    body_end = (
                        heading_matches[index + 1].start()
                        if index + 1 < len(heading_matches)
                        else len(canonical_text)
                    )
                    body = canonical_text[body_start:body_end]
                    fence_count = len(
                        re.findall(r"(?m)^```(?:text)?[ \t]*$", body)
                    )
                    expected_outcome = case_outcomes.get(case_id)
                    if expected_outcome == "PROMPT" and fence_count != 2:
                        errors.append(
                            f"canonical response {case_id} 必须恰有一个代码块"
                        )
                    if expected_outcome in {"REPORT", "BLOCK"} and fence_count != 0:
                        errors.append(
                            f"canonical response {case_id} 不得包含代码块"
                        )

    mutations = payload.get("mutations")
    mutation_ids: set[str] = set()
    duplicate_mutation_ids: set[str] = set()
    if not isinstance(mutations, list):
        errors.append("manifest.mutations 必须是数组")
        mutations = []
    result.mutation_count = len(mutations)
    if len(mutations) < MIN_MUTATIONS:
        errors.append(
            f"manifest.mutations 至少需要 {MIN_MUTATIONS} 项，当前为 {len(mutations)} 项"
        )

    for index, mutation in enumerate(mutations):
        location = f"manifest.mutations[{index}]"
        if not isinstance(mutation, dict):
            errors.append(f"{location} 必须是对象")
            continue
        require_keys(
            mutation,
            (
                "id",
                "base_case",
                "single_defect",
                "expected_dimensions",
                "oracle_hooks",
                "expected_detection",
                "severity",
            ),
            location,
            errors,
        )
        mutation_id = mutation.get("id")
        if not nonempty_string(mutation_id):
            errors.append(f"{location}.id 必须是非空字符串")
        elif mutation_id in mutation_ids:
            duplicate_mutation_ids.add(mutation_id)
        else:
            mutation_ids.add(mutation_id)
        for key in ("base_case", "single_defect", "expected_detection", "severity"):
            if key in mutation and not nonempty_string(mutation[key]):
                errors.append(f"{location}.{key} 必须是非空字符串")
        expected_dimensions = mutation.get("expected_dimensions")
        validate_string_list(
            expected_dimensions,
            f"{location}.expected_dimensions",
            errors,
        )
        if isinstance(expected_dimensions, list):
            string_dimensions = [
                item for item in expected_dimensions if isinstance(item, str)
            ]
            invalid_dimensions = sorted(
                {
                    item
                    for item in string_dimensions
                    if item not in QUALITY_DIMENSIONS
                }
            )
            if invalid_dimensions:
                errors.append(
                    f"{location}.expected_dimensions 含未知维度：{', '.join(invalid_dimensions)}"
                )
            if len(set(string_dimensions)) != len(string_dimensions):
                errors.append(f"{location}.expected_dimensions 不得重复")
        oracle_hooks = mutation.get("oracle_hooks")
        validate_string_list(oracle_hooks, f"{location}.oracle_hooks", errors)
        if isinstance(oracle_hooks, list):
            string_hooks = [item for item in oracle_hooks if isinstance(item, str)]
            invalid_hooks = sorted(
                {
                    item
                    for item in string_hooks
                    if item not in ORACLE_LIST_FIELDS
                }
            )
            if invalid_hooks:
                errors.append(
                    f"{location}.oracle_hooks 含未知 oracle 字段：{', '.join(invalid_hooks)}"
                )
            if len(set(string_hooks)) != len(string_hooks):
                errors.append(f"{location}.oracle_hooks 不得重复")
        base_case = mutation.get("base_case")
        if nonempty_string(base_case) and base_case not in case_ids:
            errors.append(f"{location}.base_case 引用了不存在的 case：{base_case}")
        severity = mutation.get("severity")
        if nonempty_string(severity):
            normalized_severity = severity.strip().lower()
            if normalized_severity not in ALLOWED_MUTATION_SEVERITIES:
                errors.append(
                    f"{location}.severity 不受支持：{severity}；应使用 P0-P3 或 critical/major/minor"
                )
            if normalized_severity in P0_SEVERITIES:
                result.p0_mutation_count += 1

    for mutation_id in sorted(duplicate_mutation_ids):
        errors.append(f"mutation id 重复：{mutation_id}")
    for overlapping_id in sorted(case_ids & mutation_ids):
        errors.append(f"case 与 mutation 共用了同一 id：{overlapping_id}")
    if mutations and result.p0_mutation_count == 0:
        errors.append("manifest.mutations 至少需要一个 P0/critical mutation")

    validity_controls = payload.get("validity_controls")
    control_ids: set[str] = set()
    duplicate_control_ids: set[str] = set()
    if not isinstance(validity_controls, list):
        errors.append("manifest.validity_controls 必须是数组")
        validity_controls = []
    result.validity_control_count = len(validity_controls)
    if len(validity_controls) < MIN_VALIDITY_CONTROLS:
        errors.append(
            "manifest.validity_controls 至少需要 "
            f"{MIN_VALIDITY_CONTROLS} 项，当前为 {len(validity_controls)} 项"
        )

    for index, control in enumerate(validity_controls):
        location = f"manifest.validity_controls[{index}]"
        if not isinstance(control, dict):
            errors.append(f"{location} 必须是对象")
            continue
        require_keys(
            control,
            (
                "id",
                "base_case",
                "valid_variant",
                "protected_dimensions",
                "expected_outcome",
                "expected_acceptance",
            ),
            location,
            errors,
        )
        control_id = control.get("id")
        if not nonempty_string(control_id):
            errors.append(f"{location}.id 必须是非空字符串")
        elif control_id in control_ids:
            duplicate_control_ids.add(control_id)
        else:
            control_ids.add(control_id)
        for key in (
            "base_case",
            "valid_variant",
            "expected_outcome",
            "expected_acceptance",
        ):
            if key in control and not nonempty_string(control[key]):
                errors.append(f"{location}.{key} 必须是非空字符串")
        if control.get("expected_outcome") != "PASS":
            errors.append(f"{location}.expected_outcome 必须是 PASS")
        base_case = control.get("base_case")
        if nonempty_string(base_case) and base_case not in case_ids:
            errors.append(f"{location}.base_case 引用了不存在的 case：{base_case}")
        protected_dimensions = control.get("protected_dimensions")
        validate_string_list(
            protected_dimensions,
            f"{location}.protected_dimensions",
            errors,
        )
        if isinstance(protected_dimensions, list):
            string_dimensions = [
                item for item in protected_dimensions if isinstance(item, str)
            ]
            invalid_dimensions = sorted(
                {
                    item
                    for item in string_dimensions
                    if item not in QUALITY_DIMENSIONS
                }
            )
            if invalid_dimensions:
                errors.append(
                    f"{location}.protected_dimensions 含未知维度：{', '.join(invalid_dimensions)}"
                )
            if len(set(string_dimensions)) != len(string_dimensions):
                errors.append(f"{location}.protected_dimensions 不得重复")

    for control_id in sorted(duplicate_control_ids):
        errors.append(f"validity control id 重复：{control_id}")
    for overlapping_id in sorted((case_ids | mutation_ids) & control_ids):
        errors.append(f"case、mutation 或 validity control 共用了同一 id：{overlapping_id}")

    result.ok = not errors
    return result


def run_regressions(repo_root: Path) -> RegressionResult:
    runner = repo_root / "scripts" / "run_regression_tests.py"
    command = [sys.executable, "-B", "-X", "utf8", str(runner)]
    result = RegressionResult(command=command)
    try:
        completed = subprocess.run(
            command,
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=180,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        result.error = str(exc)
        return result
    result.returncode = completed.returncode
    result.stdout = completed.stdout.strip()
    result.stderr = completed.stderr.strip()
    result.ok = completed.returncode == 0
    return result


def json_payload(manifest: ManifestResult, regression: RegressionResult) -> dict[str, Any]:
    return {
        "ok": manifest.ok and regression.ok,
        "gate_kind": "release_metadata_and_mechanical",
        "semantic_quality_evaluated": False,
        "scope_note": SCOPE_NOTE,
        "manifest": {
            "path": manifest.path,
            "ok": manifest.ok,
            "case_count": manifest.case_count,
            "mutation_count": manifest.mutation_count,
            "validity_control_count": manifest.validity_control_count,
            "canonical_response_count": manifest.canonical_response_count,
            "p0_mutation_count": manifest.p0_mutation_count,
            "errors": manifest.errors,
        },
        "regression": {
            "command": regression.command,
            "ok": regression.ok,
            "returncode": regression.returncode,
            "stdout": regression.stdout,
            "stderr": regression.stderr,
            "error": regression.error,
        },
    }


def print_human(manifest: ManifestResult, regression: RegressionResult) -> None:
    ok = manifest.ok and regression.ok
    print(f"RELEASE CHECKS: {'PASS' if ok else 'FAIL'}")
    print(SCOPE_NOTE)
    print(
        "Manifest metadata: "
        f"{'PASS' if manifest.ok else 'FAIL'} "
        f"({manifest.case_count} cases, {manifest.mutation_count} mutations, "
        f"{manifest.validity_control_count} validity controls, "
        f"{manifest.canonical_response_count} canonical responses, "
        f"{manifest.p0_mutation_count} P0/critical mutations)"
    )
    for error in manifest.errors:
        print(f"  - {error}")
    print(f"Mechanical regressions: {'PASS' if regression.ok else 'FAIL'}")
    if regression.stdout:
        for line in regression.stdout.splitlines():
            print(f"  {line}")
    if regression.stderr:
        for line in regression.stderr.splitlines():
            print(f"  stderr: {line}")
    if regression.error:
        print(f"  - 无法运行回归测试：{regression.error}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Manju release metadata and run mechanical regressions."
    )
    parser.add_argument(
        "--json", action="store_true", help="以 JSON 输出汇总结果"
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    manifest = validate_manifest(repo_root / "evals" / "manifest.json")
    regression = run_regressions(repo_root)

    if args.json:
        print(json.dumps(json_payload(manifest, regression), ensure_ascii=False, indent=2))
    else:
        print_human(manifest, regression)
    return 0 if manifest.ok and regression.ok else 1


if __name__ == "__main__":
    sys.exit(main())
