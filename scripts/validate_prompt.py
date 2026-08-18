#!/usr/bin/env python3
"""Deterministic validator for manju-video-prompt outputs.

Semantic story, asset-image, and continuity review remains the agent's job. This
script checks single-prompt and per-segment batch mechanical contracts.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


HEADING_RE = re.compile(r"(?m)^(主体|场景|风格|情节)：[ \t]*$")
STANDALONE_HEADING_RE = re.compile(
    r"(?m)^[ \t]*([^\s：:\r\n][^：:\r\n]{0,30})[：:][ \t]*$"
)
ASSET_STANDALONE_RE = re.compile(r"(?:图片|音频|视频)\d+：")
FIXED_TAIL = "不添加字幕，不添加背景音乐。"
SHOT_RE = re.compile(
    r"(?m)^[ \t]*镜头\s*(\d+)\s*（\s*(\d+(?:\.\d+)?)\s*"
    r"[\-–—]\s*(\d+(?:\.\d+)?)\s*秒\s*）\s*[：:]"
)
SHOT_HEADER_CANDIDATE_RE = re.compile(
    r"""
    ^[ \t]*
    (?:
        镜头[ \t]*
        (?:
            (?:
                (?:[#＃_＿·•\-－][ \t]*|第[ \t]*)?\d+
                | [#＃_＿·•\-－][ \t]*[一二三四五六七八九十百]+(?=[ \t]*[（(:：])
                | (?:No\.?|NO\.?|№)[ \t]*\d+
                | 第[ \t]*[一二三四五六七八九十百]+(?=[ \t]*[（(:：])
                | [①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]
                | [A-Za-z]+(?=[ \t]*[（(:：])
                | [一二三四五六七八九十百]+(?=[ \t]*[（(:：])
            )
            [^\r\n]*
            | [（(:：][^\r\n]*
        )
        | 第[ \t]*(?:\d+|[一二三四五六七八九十百]+|[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳])
          [ \t]*(?:号[ \t]*)?镜头[^\r\n]*
    )
    """,
    re.MULTILINE | re.VERBOSE,
)
ASSET_LABEL_RE = re.compile(r"(图片|音频|视频)(\d+)(?!\d)")

BANNED_PATTERNS = (
    (re.compile(r"@image\d+", re.IGNORECASE), "不得输出 @image 平台句柄"),
    (
        re.compile(r"<(?:Subject|Picture|Video|Audio)\s+\d+>", re.IGNORECASE),
        "不得输出 H3 私有引用标签",
    ),
    (
        re.compile(
            r"(?:subject_definitions|retention_analysis|detailed_description|"
            r"overall_soundscape|non_diegetic_music)\s*[：:]",
            re.IGNORECASE,
        ),
        "不得输出 H3 Context-IR 字段",
    ),
    (re.compile(r"\[Shot\s+\d+\]", re.IGNORECASE), "不得输出英文平台镜头标签"),
    (re.compile(r"<d>.*?</d>", re.IGNORECASE | re.DOTALL), "不得输出 H3 私有对白标签"),
    (re.compile(r"生成一段\s*\d+(?:\.\d+)?\s*秒"), "不要以生成一段X秒开头"),
    (
        re.compile(r"(?m)^[ \t]*(?:分辨率|画幅|宽高比|帧率|积分|平台参数)[ \t]*[：:]"),
        "UI参数不得进入提示词",
    ),
    (
        re.compile(
            r"(?:输出)?(?:分辨率|宽高比|帧率|平台参数)|"
            r"(?:画面比例|横纵比例|屏幕比例|画幅比例|画面尺寸)|"
            r"(?:横屏|竖屏)[ \t]*(?:画幅|比例|输出|视频|画面)|"
            r"(?:采用|使用|设为|设置为)[^。！？；;\r\n]{0,10}(?:横屏|竖屏)|"
            r"画幅[ \t]*(?:设为|设置为|采用|为|[：:]|\d|"
            r"[一二三四五六七八九十百]+[ \t]*比)|"
            r"(?:画面|视频|画幅|横纵|屏幕)[ \t]*(?:比例)?[ \t]*"
            r"(?:设为|设置为|采用|为|[：:])?[ \t]*\d{1,2}[ \t]*[：:∶][ \t]*\d{1,2}|"
            r"(?:采用|使用|按)[ \t]*\d{1,2}[ \t]*[：:∶][ \t]*\d{1,2}"
            r"[ \t]*(?:比例)?[ \t]*(?:输出|画幅|画面)|"
            r"(?:\d+(?:\.\d+)?|[一二三四五六七八九十百]+)[ \t]*比[ \t]*"
            r"(?:\d+(?:\.\d+)?|[一二三四五六七八九十百]+)[^。！？；;\r\n]{0,10}"
            r"(?:画幅|画面比例|横纵比例|屏幕比例|横屏|竖屏)|"
            r"(?<![A-Za-z0-9])(?:4K|8K|1080[Pp]?|720[Pp]?)(?![A-Za-z0-9])|"
            r"(?<![A-Za-z0-9])\d+(?:\.\d+)?[ \t]*fps(?![A-Za-z0-9])|"
            r"每秒[ \t]*\d+(?:\.\d+)?[ \t]*帧|"
            r"\d+(?:\.\d+)?[ \t]*帧[ \t]*(?:/|每)[ \t]*秒|"
            r"\d{2,5}[ \t]*[xX×][ \t]*\d{2,5}|"
            r"积分[ \t]*(?:设为|设置为|采用|为|[：:])[ \t]*\d+",
            re.IGNORECASE,
        ),
        "UI参数不得进入提示词",
    ),
    (
        re.compile(
            r"(?m)^[ \t]*(?:风险(?:评分)?|自检(?:结果)?|资产确认|位置确认|员工说明)"
            r"[ \t]*[：:]"
        ),
        "不得暴露内部审查或员工说明",
    ),
    (
        re.compile(
            r"(?i)(?<![A-Za-z0-9_])(?:storyboard_status|duration_source|"
            r"compiled_segment_id|source_cut_ids|source_cut_count|version_state|"
            r"source_cut_scope|SegmentMap|SceneState|ShotRecord|NarrativeMap)"
            r"(?![A-Za-z0-9_])"
        ),
        "不得输出内部追踪词",
    ),
)

VOICE_MODIFIER_RE = (
    r"(?:轻声|低声|小声|高声|大声|厉声|颤声|平静地|冷静地|急促地|缓慢地|"
    r"压低声音|接着|继续|画外)*"
)
VOICE_PREDICATE_RE = (
    r"(?:说道|说|问道|问|喊道|喊|叫道|叫|答道|回答|开口|低语|耳语|念道|"
    r"(?:画外声音|画外音|旁白)(?:继续|响起|说道|说|问道|问|喊道|喊)?)"
)
TRANSITION_ONLY_RE = re.compile(
    r"^(?:(?:随后|然后|接着|随即|紧接着|直接)[，,]?[ \t]*)?(?:"
    r"硬切(?:(?:至|到)(?:镜头\d+|下一镜)|转场)?|"
    r"反打(?:镜头|切|(?:切)?(?:至|到)(?:镜头\d+|下一镜))?|"
    r"(?:切至|切到|切换至|切换到)(?:镜头\d+|下一镜)|切镜|不切镜|"
    r"声音桥(?:接)?(?:(?:至|到)(?:镜头\d+|下一镜))?|"
    r"(?:动作|视线|构图)匹配切(?:(?:至|到)(?:镜头\d+|下一镜))?|"
    r"遮挡转场(?:(?:至|到)(?:镜头\d+|下一镜))?|"
    r"淡入|淡出|叠化|(?:交叉)?溶解|(?:无缝)?转场|跳切|闪切|黑场|白场|切)[。.]?$"
)


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def merge(self, other: "ValidationResult", prefix: str = "") -> None:
        self.errors.extend(f"{prefix}{item}" for item in other.errors)
        self.warnings.extend(f"{prefix}{item}" for item in other.warnings)


@dataclass(frozen=True)
class ShotSpan:
    number: int
    start: Decimal
    end: Decimal
    text_start: int
    text_end: int
    text: str
    body: str


@dataclass(frozen=True)
class AssetOccurrence:
    label: str
    position: int
    section: str | None


def decimal(value: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(value) from exc
    if not parsed.is_finite():
        raise ValueError(value)
    return parsed


def on_half_second_grid(value: Decimal) -> bool:
    return value >= 0 and (value * 2) == (value * 2).to_integral_value()


def strict_int(
    value: Any,
    *,
    field_name: str,
    minimum: int,
    result: ValidationResult,
) -> int | None:
    if isinstance(value, bool):
        result.errors.append(f"{field_name} 必须是整数，不能是布尔值")
        return None
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value.strip()):
        try:
            parsed = int(value)
        except ValueError:
            result.errors.append(f"{field_name} 整数位数过长")
            return None
    else:
        result.errors.append(f"{field_name} 必须是整数")
        return None
    if parsed < minimum:
        if minimum == 1:
            result.errors.append(f"{field_name} 必须大于0")
        else:
            result.errors.append(f"{field_name} 必须大于等于{minimum}")
        return None
    return parsed


def extract_code_blocks(response: str) -> tuple[list[str], str, list[str]]:
    """Parse only standalone ```/```text/```plaintext fenced blocks."""
    blocks: list[str] = []
    outside_lines: list[str] = []
    errors: list[str] = []
    active_lines: list[str] | None = None

    for raw_line in response.splitlines(keepends=True):
        stripped = raw_line.strip()
        lowered = stripped.lower()
        is_fence_token = stripped.startswith("```")

        if active_lines is None:
            if lowered in {"```", "```text", "```plaintext"}:
                active_lines = []
            elif is_fence_token:
                info = stripped[3:].strip() or "（空）"
                errors.append(
                    f"不支持的代码块类型：{info}；仅支持 ```、```text、```plaintext"
                )
                active_lines = []
            elif "```" in raw_line:
                errors.append("Markdown围栏必须独立成行")
                outside_lines.append(raw_line)
            else:
                outside_lines.append(raw_line)
        else:
            if stripped == "```":
                blocks.append("".join(active_lines).strip())
                active_lines = None
            elif is_fence_token:
                errors.append("Markdown闭合围栏必须以 ``` 独立成行")
                blocks.append("".join(active_lines).strip())
                active_lines = None
            elif "```" in raw_line:
                errors.append("Markdown围栏必须独立成行")
                active_lines.append(raw_line)
            else:
                active_lines.append(raw_line)

    if active_lines is not None:
        errors.append("Markdown代码块未闭合")

    return blocks, "".join(outside_lines).strip(), errors


def is_batch_contract(contract: dict[str, Any] | None) -> bool:
    return bool(contract) and (
        "expected_blocks" in contract or "segments" in contract
    )


def contract_duration(
    contract: dict[str, Any] | None, result: ValidationResult
) -> Decimal | None:
    if not contract or "expected_duration" not in contract:
        return None
    if isinstance(contract["expected_duration"], bool):
        result.errors.append("expected_duration 必须是有效数字，不能是布尔值")
        return None
    try:
        return decimal(str(contract["expected_duration"]))
    except (TypeError, ValueError):
        result.errors.append("expected_duration 必须是有效数字")
        return None


def find_shots(
    prompt: str,
    *,
    plot_start: int | None,
    plot_end: int | None,
    result: ValidationResult,
) -> list[ShotSpan]:
    valid_matches = list(SHOT_RE.finditer(prompt))

    for candidate in SHOT_HEADER_CANDIDATE_RE.finditer(prompt):
        if SHOT_RE.match(prompt, candidate.start()) is None:
            line = candidate.group(0).strip()
            result.errors.append(f"无法解析的镜头头：{line}")

    if plot_start is None or plot_end is None:
        if valid_matches:
            result.errors.append("镜头时间轴不在情节栏目内")
        return []

    inside: list[re.Match[str]] = []
    for match in valid_matches:
        if match.start() < plot_start or match.start() >= plot_end:
            result.errors.append(
                f"镜头{match.group(1)}时间轴不在情节栏目内"
            )
        else:
            inside.append(match)

    shots: list[ShotSpan] = []
    for index, match in enumerate(inside):
        text_end = inside[index + 1].start() if index + 1 < len(inside) else plot_end
        number_text = match.group(1)
        if len(number_text) > 9:
            result.errors.append(f"镜头编号过长：{len(number_text)}位数字")
            number = -1
        else:
            try:
                number = int(number_text)
            except ValueError:
                result.errors.append(f"镜头编号无法解析：{number_text!r}")
                number = -1
        body = prompt[match.end():text_end]
        meaningful_lines = [
            line
            for raw_line in body.splitlines()
            if (line := raw_line.strip())
            and line != FIXED_TAIL
            and TRANSITION_ONLY_RE.fullmatch(line) is None
            and re.search(r"[A-Za-z0-9_\u3400-\u9fff]", line)
        ]
        if not meaningful_lines:
            result.errors.append(f"镜头{match.group(1)}正文为空")
        shots.append(
            ShotSpan(
                number=number,
                start=decimal(match.group(2)),
                end=decimal(match.group(3)),
                text_start=match.start(),
                text_end=text_end,
                text=prompt[match.start():text_end],
                body=body,
            )
        )
    return shots


def dialogue_positions(prompt: str, text: str) -> list[int]:
    positions: list[int] = []
    offset = 0
    while True:
        position = prompt.find(text, offset)
        if position < 0:
            return positions
        positions.append(position)
        offset = position + max(len(text), 1)


def has_explicit_speaker_attribution(
    shot_text: str, *, speaker: str, dialogue: str, dialogue_offset: int
) -> bool:
    """Require a direct speaker -> speech predicate -> exact line construction."""
    clause_lead = (
        r"(?:^|[\r\n。！？；;：:,，”’\"'）)】\]])[ \t]*[”’\"'）)】\]]*[ \t]*"
        r"(?:(?:随后|接着|此时|同时|然后|而后|随即)[ \t]*[，,]?[ \t]*)?"
    )
    target_listener = (
        r"(?:[ \t]*(?:对|向|朝|朝着|冲|冲着)[ \t]*"
        r"[^，,。！？；;：:\r\n]{1,24}?)?"
    )
    pre_speech_action = (
        r"(?:[ \t]*(?:看着|望着|看向|望向|面对|面向|转身面向|转头看向)"
        r"[ \t]*[^，,。！？；;：:\r\n]{1,24}[ \t]*[，,]?[ \t]*)?"
    )
    direct_core = (
        VOICE_MODIFIER_RE
        + r"[ \t]*"
        + target_listener
        + r"[ \t]*"
        + VOICE_MODIFIER_RE
        + r"[ \t]*"
        + VOICE_PREDICATE_RE
    )
    object_core = (
        VOICE_MODIFIER_RE
        + r"[ \t]*(?:回答|问|告诉)[ \t]*"
        + r"[^，,。！？；;：:\r\n]{1,24}?"
    )
    attribution = (
        clause_lead
        + re.escape(speaker)
        + r"(?:的)?[ \t]*"
        + pre_speech_action
        + r"(?:"
        + object_core
        + r"|"
        + direct_core
        + r")"
        + r"[ \t]*[：:,，]?[ \t]*[“\"‘']?[ \t]*"
        + r"(?P<dialogue>"
        + re.escape(dialogue)
        + r")"
    )
    pattern = re.compile(r"(?=(" + attribution + r"))")
    return any(
        match.start("dialogue") == dialogue_offset
        for match in pattern.finditer(shot_text)
    )


def validate_contract(
    prompt: str,
    contract: dict[str, Any],
    *,
    assets: list[str],
    asset_occurrences: list[AssetOccurrence],
    shots: list[ShotSpan],
    has_subject: bool,
) -> ValidationResult:
    result = ValidationResult()

    has_expected_assets = "expected_assets" in contract
    has_expected_asset_sections = "expected_asset_sections" in contract
    if has_expected_assets != has_expected_asset_sections:
        result.errors.append(
            "expected_assets 与 expected_asset_sections 必须成对出现"
        )

    expected_assets = contract.get("expected_assets")
    valid_expected_assets: list[str] | None = None
    if has_expected_assets:
        if not isinstance(expected_assets, list) or not all(
            isinstance(item, str) for item in expected_assets
        ):
            result.errors.append("expected_assets 必须是字符串数组")
        elif any(ASSET_LABEL_RE.fullmatch(item) is None for item in expected_assets):
            result.errors.append("expected_assets 每项必须是图片N、音频N或视频N")
        elif len(expected_assets) != len(set(expected_assets)):
            result.errors.append("expected_assets 不得包含重复素材标签")
        else:
            valid_expected_assets = expected_assets
            if assets != expected_assets:
                result.errors.append(
                    f"素材职责不符：期望 {expected_assets}，实际 {assets}"
                )

    expected_asset_sections = contract.get("expected_asset_sections")
    if has_expected_asset_sections:
        valid_sections = {"主体", "场景", "风格", "情节"}
        if not isinstance(expected_asset_sections, dict):
            result.errors.append("expected_asset_sections 必须是标签到栏目的映射")
        else:
            if valid_expected_assets is not None:
                expected_keys = set(valid_expected_assets)
                actual_keys = set(expected_asset_sections)
                missing_keys = [
                    label for label in valid_expected_assets if label not in actual_keys
                ]
                extra_keys = [
                    label
                    for label in expected_asset_sections
                    if label not in expected_keys
                ]
                if missing_keys or extra_keys:
                    details: list[str] = []
                    if missing_keys:
                        details.append(f"缺少 {missing_keys}")
                    if extra_keys:
                        details.append(f"多出 {extra_keys}")
                    result.errors.append(
                        "expected_asset_sections 必须覆盖 expected_assets 的全部且仅有素材："
                        + "；".join(details)
                    )
            for label, expected_section in expected_asset_sections.items():
                if (
                    not isinstance(label, str)
                    or ASSET_LABEL_RE.fullmatch(label) is None
                    or not isinstance(expected_section, str)
                    or expected_section not in valid_sections
                ):
                    result.errors.append(
                        "expected_asset_sections 每项必须是素材标签到主体/场景/风格/情节的映射"
                    )
                    continue
                actual_sections = [
                    occurrence.section
                    for occurrence in asset_occurrences
                    if occurrence.label == label
                ]
                if not actual_sections:
                    result.errors.append(
                        f"素材栏目不符：{label} 期望位于{expected_section}，实际未出现"
                    )
                    continue
                wrong_sections = [
                    section for section in actual_sections if section != expected_section
                ]
                if wrong_sections:
                    actual = ", ".join(
                        section if section is not None else "栏目外"
                        for section in actual_sections
                    )
                    result.errors.append(
                        f"素材栏目不符：{label} 期望位于{expected_section}，实际位于{actual}"
                    )

    if "subject_required" not in contract:
        result.errors.append("contract 必须包含布尔字段 subject_required")
    else:
        subject_required = contract.get("subject_required")
        if not isinstance(subject_required, bool):
            result.errors.append("subject_required 必须是布尔值")
        else:
            if subject_required and not has_subject:
                result.errors.append("当前生成段要求主体标题，但提示词未包含主体：")
            if not subject_required and has_subject:
                result.errors.append("contract 声明无需主体标题，但提示词包含主体：")
            if not subject_required:
                exact_dialogue_value = contract.get("exact_dialogue", [])
                if isinstance(exact_dialogue_value, list) and exact_dialogue_value:
                    result.errors.append(
                        "subject_required=false 与非空 exact_dialogue 矛盾"
                    )
                if (
                    isinstance(expected_asset_sections, dict)
                    and "主体" in expected_asset_sections.values()
                ):
                    result.errors.append(
                        "subject_required=false 与主体栏目的素材绑定矛盾"
                    )

    expected_shot_count = contract.get("expected_shot_count")
    if "expected_shot_count" in contract:
        count = strict_int(
            expected_shot_count,
            field_name="expected_shot_count",
            minimum=1,
            result=result,
        )
        if count is not None and len(shots) != count:
            result.errors.append(
                f"镜头数量不符：期望 {count}，实际 {len(shots)}"
            )

    exact_dialogue = contract.get("exact_dialogue", [])
    if not isinstance(exact_dialogue, list):
        result.errors.append("exact_dialogue 必须是数组")
        return result

    for item in exact_dialogue:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            result.errors.append("exact_dialogue 每项必须包含字符串 text")
            continue

        text = item["text"]
        if not text.strip():
            result.errors.append("exact_dialogue 的 text 必须是非空字符串")
            continue
        expected_count = strict_int(
            item.get("count", 1),
            field_name=f"对白 {text!r} 的 count",
            minimum=0,
            result=result,
        )
        if expected_count is None:
            continue

        positions = dialogue_positions(prompt, text)
        if len(positions) != expected_count:
            result.errors.append(
                f"对白原文次数不符：{text!r} 期望 {expected_count} 次，实际 {len(positions)} 次"
            )

        speaker = item.get("speaker")
        if not isinstance(speaker, str) or not speaker.strip():
            result.errors.append(f"对白 {text!r} 的 speaker 必须是非空字符串")
            continue

        for position in positions:
            owning_shot = next(
                (
                    shot
                    for shot in shots
                    if shot.text_start <= position < shot.text_end
                ),
                None,
            )
            if owning_shot is None:
                result.errors.append(f"对白 {text!r} 不在可解析镜头内")
            elif not has_explicit_speaker_attribution(
                owning_shot.text,
                speaker=speaker,
                dialogue=text,
                dialogue_offset=position - owning_shot.text_start,
            ):
                result.errors.append(
                    f"对白说话人不符：镜头{owning_shot.number}中的 {text!r} "
                    f"没有由 {speaker!r} 通过发声谓词直接引出"
                )

    return result


def validate_prompt(
    prompt: str,
    *,
    expected_duration: Decimal | None = None,
    contract: dict[str, Any] | None = None,
) -> ValidationResult:
    result = ValidationResult()
    prompt = prompt.strip()

    if not prompt:
        result.errors.append("提示词为空")
        return result

    if contract is not None and not isinstance(contract, dict):
        result.errors.append("contract 必须是JSON对象")
        contract = None
    elif is_batch_contract(contract):
        result.errors.append("批量合同只能用于 --response 校验")
        contract = None

    if "```" in prompt:
        result.errors.append("单条提示词正文不应包含Markdown围栏")

    headings = [
        (match.group(1), match.start(), match.end())
        for match in HEADING_RE.finditer(prompt)
    ]
    names = [item[0] for item in headings]

    if headings and headings[0][1] != 0:
        result.errors.append("正文标题前不得有前言或说明文字")

    required = {"场景", "风格", "情节"}
    missing = sorted(required - set(names))
    if missing:
        result.errors.append(f"缺少必需标题：{', '.join(missing)}")

    if len(names) != len(set(names)):
        result.errors.append("同一标题重复出现")

    expected_order = [
        name for name in ("主体", "场景", "风格", "情节") if name in names
    ]
    if names != expected_order:
        result.errors.append(f"标题顺序错误：实际 {names}，应为 {expected_order}")

    canonical_headings = {"主体：", "场景：", "风格：", "情节："}
    for match in STANDALONE_HEADING_RE.finditer(prompt):
        line = match.group(0).strip()
        if (
            line in canonical_headings
            or ASSET_STANDALONE_RE.fullmatch(line)
            or SHOT_RE.match(prompt, match.start()) is not None
        ):
            continue
        result.errors.append(f"未知独立栏目：{line}")

    plot_start: int | None = None
    plot_end: int | None = None
    for index, (name, _start, end) in enumerate(headings):
        next_start = headings[index + 1][1] if index + 1 < len(headings) else len(prompt)
        body = prompt[end:next_start].strip()
        if not body:
            result.errors.append(f"标题 {name} 内容为空")
        if name == "情节" and plot_start is None:
            plot_start = end
            plot_end = next_start

    if not prompt.endswith(FIXED_TAIL):
        result.errors.append("提示词必须以“不添加字幕，不添加背景音乐。”收尾")

    for pattern, message in BANNED_PATTERNS:
        if pattern.search(prompt):
            result.errors.append(message)

    if re.search(r"\[[^\]\n]+\]", prompt):
        result.errors.append("提示词仍含方括号占位文本或控制标签")

    asset_occurrences: list[AssetOccurrence] = []
    for match in ASSET_LABEL_RE.finditer(prompt):
        section: str | None = None
        for index, (name, _start, end) in enumerate(headings):
            next_start = (
                headings[index + 1][1]
                if index + 1 < len(headings)
                else len(prompt)
            )
            if end <= match.start() < next_start:
                section = name
                break
        asset_occurrences.append(
            AssetOccurrence(
                label=f"{match.group(1)}{match.group(2)}",
                position=match.start(),
                section=section,
            )
        )
    assets = [occurrence.label for occurrence in asset_occurrences]
    duplicates = sorted({label for label in assets if assets.count(label) > 1})
    if duplicates:
        result.errors.append(f"素材标签重复出现：{', '.join(duplicates)}")

    shots = find_shots(
        prompt, plot_start=plot_start, plot_end=plot_end, result=result
    )

    if not shots:
        result.errors.append("情节中没有可解析的镜头时间段")
    else:
        shot_numbers = [shot.number for shot in shots]
        expected_numbers = list(range(1, len(shots) + 1))
        if shot_numbers != expected_numbers:
            result.errors.append(
                f"镜头编号不连续：实际 {shot_numbers}，应为 {expected_numbers}"
            )

        if shots[0].start != Decimal("0"):
            result.errors.append(
                f"时间轴必须从0.0秒开始，实际从{shots[0].start}秒开始"
            )

        previous_end: Decimal | None = None
        for shot in shots:
            if not on_half_second_grid(shot.start) or not on_half_second_grid(shot.end):
                result.errors.append(
                    f"镜头{shot.number}不在0.5秒网格：{shot.start}–{shot.end}"
                )
            if shot.end <= shot.start:
                result.errors.append(
                    f"镜头{shot.number}持续时间必须为正：{shot.start}–{shot.end}"
                )
            if previous_end is not None and shot.start != previous_end:
                result.errors.append(
                    f"镜头{shot.number}与上一镜时间不连续：上一镜结束{previous_end}，"
                    f"本镜开始{shot.start}"
                )
            previous_end = shot.end

    contract_expected_duration = contract_duration(contract, result)
    if (
        expected_duration is not None
        and contract_expected_duration is not None
        and expected_duration != contract_expected_duration
    ):
        result.errors.append(
            "命令行 expected_duration 与 contract.expected_duration 不一致"
        )
    effective_duration = (
        expected_duration
        if expected_duration is not None
        else contract_expected_duration
    )
    if effective_duration is not None and shots and shots[-1].end != effective_duration:
        result.errors.append(
            f"总时长不符：期望{effective_duration}秒，实际结束于{shots[-1].end}秒"
        )

    if contract is not None:
        result.merge(
            validate_contract(
                prompt,
                contract,
                assets=assets,
                asset_occurrences=asset_occurrences,
                shots=shots,
                has_subject="主体" in names,
            )
        )

    return result


def validate_response(
    response: str,
    *,
    expected_duration: Decimal | None = None,
    contract: dict[str, Any] | None = None,
) -> ValidationResult:
    result = ValidationResult()
    blocks, outside, fence_errors = extract_code_blocks(response)

    result.errors.extend(fence_errors)

    if outside:
        result.errors.append("最终回复在代码块外仍含文字")
    if not blocks:
        result.errors.append("最终回复没有独立Markdown代码块")

    if contract is not None and not isinstance(contract, dict):
        result.errors.append("contract 必须是JSON对象")
        contract = None

    if is_batch_contract(contract):
        assert contract is not None
        expected_blocks = contract.get("expected_blocks")
        segments = contract.get("segments")

        expected_blocks = strict_int(
            expected_blocks,
            field_name="批量合同 expected_blocks",
            minimum=1,
            result=result,
        )
        if not isinstance(segments, list):
            result.errors.append("批量合同 segments 必须是数组")
            segments = []

        if expected_blocks is not None and len(blocks) != expected_blocks:
            result.errors.append(
                f"代码块数量不符：期望 {expected_blocks}，实际 {len(blocks)}"
            )
        if expected_blocks is not None and len(segments) != expected_blocks:
            result.errors.append(
                f"批量合同段数不符：expected_blocks={expected_blocks}，"
                f"segments={len(segments)}"
            )
        if expected_duration is not None:
            result.errors.append(
                "批量回复不能使用单一 expected_duration；请写入各 segment"
            )

        for index, block in enumerate(blocks, start=1):
            segment: dict[str, Any] | None = None
            if index <= len(segments):
                raw_segment = segments[index - 1]
                if isinstance(raw_segment, dict):
                    segment = raw_segment
                else:
                    result.errors.append(f"segment {index} 必须是JSON对象")
            child = validate_prompt(block, contract=segment)
            result.merge(child, prefix=f"代码块{index}：")
        return result

    if len(blocks) > 1 and contract:
        result.errors.append(
            "单段 contract 不能用于多代码块；请使用 expected_blocks + segments"
        )
    if len(blocks) > 1 and expected_duration is not None:
        result.errors.append(
            "多代码块不能使用单一 expected_duration；请使用批量逐段合同"
        )

    for index, block in enumerate(blocks, start=1):
        child_contract = contract if len(blocks) == 1 else None
        child_duration = expected_duration if len(blocks) == 1 else None
        child = validate_prompt(
            block,
            expected_duration=child_duration,
            contract=child_contract,
        )
        result.merge(child, prefix=f"代码块{index}：")

    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate a manju-video-prompt draft or final response"
    )
    parser.add_argument(
        "path", type=Path, help="UTF-8 text file containing one prompt or a Markdown response"
    )
    parser.add_argument(
        "--response", action="store_true", help="Require code-block-only final response"
    )
    parser.add_argument(
        "--expected-duration", type=str, help="Expected total seconds for a single prompt"
    )
    parser.add_argument(
        "--contract",
        type=Path,
        help="Optional single-segment contract or batch expected_blocks + segments JSON",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    return parser


def emit_result(result: ValidationResult, *, as_json: bool) -> None:
    payload = {"ok": result.ok, "errors": result.errors, "warnings": result.warnings}
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("PASS" if result.ok else "FAIL")
        for item in result.errors:
            print(f"ERROR: {item}")
        for item in result.warnings:
            print(f"WARN: {item}")


def main() -> int:
    args = build_parser().parse_args()
    setup_result = ValidationResult()

    try:
        input_text = args.path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        setup_result.errors.append(f"无法读取提示词文件：{exc}")
        input_text = None

    expected_duration: Decimal | None = None
    if args.expected_duration is not None:
        try:
            expected_duration = decimal(args.expected_duration)
        except (TypeError, ValueError):
            setup_result.errors.append("--expected-duration 必须是有效有限数字")

    contract: Any = None
    if args.contract is not None:
        try:
            contract_text = args.contract.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            setup_result.errors.append(f"无法读取合同文件：{exc}")
        else:
            try:
                contract = json.loads(contract_text)
            except json.JSONDecodeError as exc:
                setup_result.errors.append(
                    f"合同JSON无法解析：第{exc.lineno}行第{exc.colno}列"
                )
            except ValueError as exc:
                setup_result.errors.append(f"合同JSON无法解析：{exc}")
        if contract is None and not setup_result.errors:
            setup_result.errors.append("contract 必须是JSON对象，不能是 null")

    if setup_result.errors or input_text is None:
        emit_result(setup_result, as_json=args.json)
        return 1

    if args.response:
        result = validate_response(
            input_text, expected_duration=expected_duration, contract=contract
        )
    else:
        result = validate_prompt(
            input_text, expected_duration=expected_duration, contract=contract
        )

    emit_result(result, as_json=args.json)

    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
