#!/usr/bin/env python3
"""Regression, batch-contract, and mutation tests for validate_prompt.py."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

from validate_prompt import validate_prompt, validate_response


MULTI = """主体：
图片1：沈清霜的外貌、发型与白色衣裙。图片2：墨尘的外貌、束发与深蓝长衫。图片3：合拢油纸伞的外形、竹骨与木柄。

场景：
图片4：雨夜石桥的建筑和空间布局。细雨持续落下，桥面湿润反光，水声和雨声贯穿全段。

风格：
3D渲染的国漫CG动画，冷灰色雨夜光线，写实材质。

情节：
镜头1（0.0–1.5秒）：全景平视，沈清霜站在桥中央，墨尘从右后方走近；镜头结束时他停在她身后三步处。
硬切。
镜头2（1.5–3.5秒）：沈清霜侧脸近景，她没有回头；沈清霜轻声说道：“你还是来了。”台词结束后闭嘴，视线仍朝向桥外。
反打切至镜头3。
镜头3（3.5–5.0秒）：墨尘中近景看着沈清霜，右手缓慢握紧伞柄；最终保持沉默，没有再次走近。

不添加字幕，不添加背景音乐。"""

SINGLE = """主体：
图片1：沈清霜的外貌、发型与白色衣裙。

场景：
图片2：雨夜石桥的建筑和空间布局。细雨与水声持续。

风格：
3D渲染的国漫CG动画，冷灰色雨夜光线。

情节：
镜头1（0.0–5.0秒）：同一连续镜头，不切镜。中近景固定机位，沈清霜站在桥面左侧；她先望向河面，随后缓慢转头看向画面右侧，最终停住并轻轻蹙眉。

不添加字幕，不添加背景音乐。"""

ENVIRONMENT = """场景：
图片1：清晨山谷、竹林小路和薄雾的空间布局。谷风推动薄雾向右缓移，竹叶分层轻晃。

风格：
3D渲染的国漫CG动画，低饱和晨雾和柔和侧逆光。

情节：
镜头1（0.0–2.0秒）：山谷大全景固定机位，薄雾沿山势向右缓移，前景竹叶轻晃，远处山脊逐渐从雾中显露。

不添加字幕，不添加背景音乐。"""

AUDIO_MULTI = MULTI.replace(
    "图片3：合拢油纸伞的外形、竹骨与木柄。",
    "图片3：合拢油纸伞的外形、竹骨与木柄。音频1只参考沈清霜的音色与克制的说话气质。",
)

GENERATION_PLOT_ONLY = """情节：
镜头1（0.0–1.0秒）：石桥空镜，固定机位，雨滴落在桥面后停住。

不添加字幕，不添加背景音乐。"""

GENERATION_SOUND = """声音：
音频1只参考沈清霜的音色与克制的说话气质。

情节：
镜头1（0.0–1.0秒）：沈清霜画外轻声说道：“停下。”随后恢复安静。

不添加字幕，不添加背景音乐。"""

EXTENSION_MINIMAL = """视频延长：
向后延长视频1；该视频讲述两人在雨夜石桥对峙。新增片段直接承接视频结尾两人保持静止的状态继续。

情节：
新增镜头1（0.0–1.5秒）：固定机位，沈清霜先抬眼看向桥外，镜头结束时保持沉默。
硬切至新增镜头2。
新增镜头2（1.5–3.0秒）：墨尘停在原位，右手松开伞柄，最终垂手站定。"""

EXTENSION_FULL = """视频延长：
向后延长视频1；该视频讲述沈清霜与墨尘在雨夜石桥相遇。新增片段直接承接视频结尾两人隔着三步对视、细雨持续的状态继续。

主体：
图片1：沈清霜与墨尘的身份、外貌、发型和服装。

场景：
图片2：雨夜石桥的建筑布局、湿润石面和栏杆位置。

风格：
延续冷灰色写实国漫动画质感。

声音：
音频1只参考沈清霜的音色与克制的说话气质。

情节：
新增镜头1（0.0–2.0秒）：中景平视，沈清霜位于左侧、墨尘位于右侧；她缓慢抬眼看向桥外。
硬切至新增镜头2。
新增镜头2（2.0–4.0秒）：切到墨尘中近景；他松开伞柄，右手垂下。"""


EXTENSION_CAMERA_CLOSURE = EXTENSION_FULL.replace(
    "新增镜头1（0.0–2.0秒）：中景平视，沈清霜位于左侧、墨尘位于右侧；她缓慢抬眼看向桥外。",
    "新增镜头1（0.0–2.0秒）：中景平视，摄影机位于桥侧，看见左侧的沈清霜和右侧的墨尘；冷灰雨光映在两人之间的湿桥面，沈清霜是画面内最清晰的主体，她缓慢抬眼看向桥外。",
).replace(
    "新增镜头2（2.0–4.0秒）：切到墨尘中近景；他松开伞柄，右手垂下。",
    "新增镜头2（2.0–4.0秒）：切到墨尘侧面中近景，冷灰雨光映出他的右手与伞柄，两者保持清晰；他仍停在原位，缓慢松开伞柄，右手自然垂下。",
)


def fenced(prompt: str) -> str:
    return f"```text\n{prompt}\n```"


def batch_response(*prompts: str) -> str:
    return "\n\n".join(fenced(prompt) for prompt in prompts)


def move_timeline_outside_plot(prompt: str) -> str:
    prefix, rest = prompt.split("情节：\n", 1)
    timeline, _tail = rest.rsplit("\n\n不添加字幕，不添加背景音乐。", 1)
    return (
        prefix
        + timeline
        + "\n\n情节：\n这里只保留占位说明。\n\n"
        + "不添加字幕，不添加背景音乐。"
    )


def main() -> int:
    cases: list[tuple[str, bool, bool]] = []

    def add(name: str, actual: bool, expected: bool = True) -> None:
        cases.append((name, actual, expected))

    def add_error(name: str, result: object, expected_error: str) -> None:
        errors = getattr(result, "errors", [])
        matched = not getattr(result, "ok", True) and any(
            expected_error in error for error in errors
        )
        cases.append((name, matched, True))

    def add_cli_error(
        name: str,
        completed: subprocess.CompletedProcess[str],
        expected_error: str,
        *,
        json_mode: bool = False,
    ) -> None:
        if json_mode:
            try:
                payload = json.loads(completed.stdout)
            except json.JSONDecodeError:
                matched = False
            else:
                matched = (
                    payload.get("ok") is False
                    and any(
                        expected_error in error
                        for error in payload.get("errors", [])
                    )
                )
        else:
            matched = "FAIL" in completed.stdout and expected_error in completed.stdout
        matched = (
            matched
            and completed.returncode == 1
            and "Traceback" not in completed.stdout
            and "Traceback" not in completed.stderr
        )
        cases.append((name, matched, True))

    legacy_contract = {
        "subject_required": True,
        "expected_assets": ["图片1", "图片2", "图片3", "图片4"],
        "expected_asset_sections": {
            "图片1": "主体",
            "图片2": "主体",
            "图片3": "主体",
            "图片4": "场景",
        },
        "exact_dialogue": [
            {"text": "你还是来了。", "count": 1, "speaker": "沈清霜"}
        ],
        "expected_shot_count": 3,
    }
    single_contract = {
        "subject_required": True,
        "expected_duration": "5.0",
        "expected_assets": ["图片1", "图片2"],
        "expected_asset_sections": {"图片1": "主体", "图片2": "场景"},
        "expected_shot_count": 1,
    }
    batch_contract = {
        "expected_blocks": 2,
        "segments": [
            {
                "subject_required": True,
                "expected_duration": "5.0",
                "expected_assets": ["图片1", "图片2", "图片3", "图片4"],
                "expected_asset_sections": {
                    "图片1": "主体",
                    "图片2": "主体",
                    "图片3": "主体",
                    "图片4": "场景",
                },
                "exact_dialogue": [
                    {
                        "text": "你还是来了。",
                        "count": 1,
                        "speaker": "沈清霜",
                    }
                ],
                "expected_shot_count": 3,
            },
            single_contract,
        ],
    }
    extension_contract = {
        "task_kind": "extension",
        "delivery_mode": "full_sequence",
        "expected_blocks": 1,
        "expected_headings": [
            "视频延长",
            "主体",
            "场景",
            "风格",
            "声音",
            "情节",
        ],
        "expected_duration": "4.0",
        "expected_assets": ["视频1", "图片1", "图片2", "音频1"],
        "expected_asset_sections": {
            "视频1": "视频延长",
            "图片1": "主体",
            "图片2": "场景",
            "音频1": "声音",
        },
        "expected_shot_count": 2,
        "tail_policy": "inherit_source",
    }
    full_sequence_generation_contract = {
        "task_kind": "generation",
        "delivery_mode": "full_sequence",
        "expected_blocks": 1,
        "expected_headings": ["情节"],
        "expected_duration": "1.0",
        "expected_shot_count": 1,
        "tail_policy": "generation_default",
    }

    add(
        "valid_multi_legacy_contract",
        validate_prompt(
            MULTI,
            expected_duration=Decimal("5.0"),
            contract=legacy_contract,
        ).ok,
    )
    add("valid_single", validate_prompt(SINGLE).ok)
    add("valid_environment_without_subject", validate_prompt(ENVIRONMENT).ok)
    add(
        "valid_generation_with_only_required_plot_heading",
        validate_prompt(GENERATION_PLOT_ONLY).ok,
    )
    add(
        "mechanical_validator_does_not_keyword_check_cinematography",
        validate_prompt(GENERATION_PLOT_ONLY).ok,
    )
    add(
        "valid_generation_sound_heading_with_audio_asset",
        validate_prompt(GENERATION_SOUND).ok,
    )
    add(
        "valid_generation_sound_asset_contract",
        validate_prompt(
            GENERATION_SOUND,
            contract={
                "task_kind": "generation",
                "expected_headings": ["声音", "情节"],
                "expected_assets": ["音频1"],
                "expected_asset_sections": {"音频1": "声音"},
                "expected_shot_count": 1,
            },
        ).ok,
    )
    add(
        "valid_extension_inferred_without_contract",
        validate_prompt(EXTENSION_MINIMAL).ok,
    )
    add(
        "valid_extension_full_prompt_contract",
        validate_prompt(EXTENSION_FULL, contract=extension_contract).ok,
    )
    add(
        "extension_fixture_avoids_empty_value_sentences",
        all(
            term not in EXTENSION_CAMERA_CLOSURE
            for term in ("前景无主体", "无运镜", "无明显虚焦", "本镜无对白")
        ) and validate_prompt(EXTENSION_CAMERA_CLOSURE, contract=extension_contract).ok,
    )
    add(
        "extension_fixture_retains_camera_closure_examples",
        all(
            term in EXTENSION_CAMERA_CLOSURE
            for term in ("中景平视", "摄影机位于", "冷灰雨光", "最清晰", "保持清晰")
        ),
    )
    add(
        "valid_extension_full_sequence_response",
        validate_response(
            fenced(EXTENSION_FULL), contract=extension_contract
        ).ok,
    )
    add(
        "valid_generation_full_sequence_contract_without_subject_required",
        validate_response(
            fenced(GENERATION_PLOT_ONLY),
            contract=full_sequence_generation_contract,
        ).ok,
    )
    extension_custom_tail = EXTENSION_MINIMAL + "\n\n保持源视频已有字幕。"
    add(
        "valid_extension_expected_tail_override",
        validate_prompt(
            extension_custom_tail,
            contract={
                "task_kind": "extension",
                "expected_headings": ["视频延长", "情节"],
                "expected_shot_count": 2,
                "tail_policy": "inherit_source",
                "expected_tail": "保持源视频已有字幕。",
            },
        ).ok,
    )
    environment_contract = {
        "subject_required": False,
        "expected_duration": "2.0",
        "expected_assets": ["图片1"],
        "expected_asset_sections": {"图片1": "场景"},
        "expected_shot_count": 1,
    }
    add(
        "valid_environment_contract_without_subject",
        validate_prompt(ENVIRONMENT, contract=environment_contract).ok,
    )
    add(
        "valid_shot_body_on_next_line",
        validate_prompt(
            SINGLE.replace(
                "镜头1（0.0–5.0秒）：同一连续镜头",
                "镜头1（0.0–5.0秒）：\n同一连续镜头",
            )
        ).ok,
    )
    add(
        "valid_response_legacy_contract",
        validate_response(fenced(MULTI), contract=legacy_contract).ok,
    )
    add(
        "multiple_blocks_without_contract_rejected",
        validate_response(batch_response(MULTI, SINGLE)).ok,
        False,
    )
    add(
        "valid_batch_per_segment_contract",
        validate_response(
            batch_response(MULTI, SINGLE), contract=batch_contract
        ).ok,
    )
    add(
        "valid_audio_binding_without_colon",
        validate_prompt(
            AUDIO_MULTI,
            contract={
                "subject_required": True,
                "expected_assets": [
                    "图片1",
                    "图片2",
                    "图片3",
                    "音频1",
                    "图片4",
                ],
                "expected_asset_sections": {
                    "图片1": "主体",
                    "图片2": "主体",
                    "图片3": "主体",
                    "音频1": "主体",
                    "图片4": "场景",
                },
                "expected_shot_count": 3,
            },
        ).ok,
    )
    add(
        "valid_contract_duration_and_shot_count",
        validate_prompt(
            MULTI,
            contract={
                "subject_required": True,
                "expected_duration": 5,
                "expected_shot_count": 3,
            },
        ).ok,
    )
    add(
        "valid_bare_fence",
        validate_response(f"```\n{MULTI}\n```").ok,
    )
    add(
        "valid_plaintext_fence",
        validate_response(f"```plaintext\n{MULTI}\n```").ok,
    )
    add(
        "valid_explicit_offscreen_speaker",
        validate_prompt(
            MULTI.replace("沈清霜轻声说道", "沈清霜的画外声音继续"),
            contract=legacy_contract,
        ).ok,
    )
    add(
        "valid_speaker_with_target_listener",
        validate_prompt(
            MULTI.replace("沈清霜轻声说道", "沈清霜对墨尘轻声说道"),
            contract=legacy_contract,
        ).ok,
    )
    adjacent_same_speaker = MULTI.replace(
        "沈清霜轻声说道：“你还是来了。”台词结束后闭嘴",
        "沈清霜轻声说道：“你还是来了。”沈清霜接着说道：“你还是来了。”随后闭嘴",
    )
    add(
        "valid_each_adjacent_occurrence_has_direct_speaker",
        validate_prompt(
            adjacent_same_speaker,
            contract={
                **legacy_contract,
                "exact_dialogue": [
                    {"text": "你还是来了。", "count": 2, "speaker": "沈清霜"}
                ],
            },
        ).ok,
    )
    speaker_form_replacements = {
        "valid_speaker_with_visible_listener_action": "沈清霜看着墨尘低声说道",
        "valid_speaker_with_orientation_action": "沈清霜转身面向墨尘，轻声说道",
        "valid_speaker_with_object_after_predicate": "沈清霜回答墨尘",
    }
    for name, replacement in speaker_form_replacements.items():
        add(
            name,
            validate_prompt(
                MULTI.replace("沈清霜轻声说道", replacement),
                contract=legacy_contract,
            ).ok,
        )

    mutations: list[tuple[str, str, dict[str, object] | None]] = [
        (
            "missing_tail",
            MULTI.replace("\n不添加字幕，不添加背景音乐。", ""),
            None,
        ),
        (
            "time_gap",
            MULTI.replace("镜头2（1.5–3.5秒）", "镜头2（2.0–3.5秒）"),
            None,
        ),
        (
            "time_overlap",
            MULTI.replace("镜头2（1.5–3.5秒）", "镜头2（1.0–3.5秒）"),
            None,
        ),
        (
            "off_grid",
            MULTI.replace("镜头2（1.5–3.5秒）", "镜头2（1.7–3.5秒）"),
            None,
        ),
        (
            "zero_duration",
            MULTI.replace("镜头2（1.5–3.5秒）", "镜头2（1.5–1.5秒）"),
            None,
        ),
        (
            "start_not_zero",
            MULTI.replace("镜头1（0.0–1.5秒）", "镜头1（0.5–1.5秒）"),
            None,
        ),
        (
            "wrong_number",
            MULTI.replace("镜头3（3.5–5.0秒）", "镜头4（3.5–5.0秒）"),
            None,
        ),
        (
            "duplicate_asset_colon",
            MULTI.replace("场景：\n", "场景：\n图片1：错误的重复职责。"),
            None,
        ),
        (
            "duplicate_asset_natural_reference",
            MULTI.replace("沈清霜侧脸近景", "图片1中的沈清霜侧脸近景"),
            None,
        ),
        (
            "duplicate_asset_after_chinese_text",
            MULTI.replace("沈清霜侧脸近景", "人物参考图片1的沈清霜侧脸近景"),
            None,
        ),
        (
            "duplicate_audio_natural_reference",
            AUDIO_MULTI.replace("墨尘中近景", "音频1只参考的墨尘中近景"),
            None,
        ),
        (
            "private_handle",
            MULTI.replace("图片1：", "@image1 图片1：", 1),
            None,
        ),
        (
            "h3_private_tag",
            MULTI.replace("沈清霜", "<Subject 1>", 1),
            None,
        ),
        (
            "empty_style",
            MULTI.replace(
                "风格：\n3D渲染的国漫CG动画，冷灰色雨夜光线，写实材质。",
                "风格：",
            ),
            None,
        ),
        (
            "duplicate_heading",
            MULTI.replace("风格：\n", "场景：\n重复场景。\n\n风格：\n", 1),
            None,
        ),
        (
            "wrong_heading_order",
            MULTI.replace("场景：\n", "TEMP：\n", 1)
            .replace("风格：\n", "场景：\n", 1)
            .replace("TEMP：\n", "风格：\n", 1),
            None,
        ),
        ("body_preamble", "这是最终结果：\n" + MULTI, None),
        (
            "unknown_standalone_heading",
            MULTI.replace("风格：\n", "声音：\n雨声持续。\n\n风格：\n", 1),
            None,
        ),
        ("timeline_outside_plot", move_timeline_outside_plot(MULTI), None),
        (
            "malformed_shot_header",
            MULTI.replace("镜头2（1.5–3.5秒）", "镜头X（1.5–3.5秒）"),
            None,
        ),
        (
            "truncated_shot_header",
            MULTI.replace(
                "镜头2（1.5–3.5秒）：沈清霜侧脸近景，她没有回头；沈清霜轻声说道：",
                "镜头2。沈清霜侧脸近景，她没有回头；沈清霜轻声说道：",
            ),
            None,
        ),
        (
            "negative_extra_shot_header",
            MULTI.replace(
                "硬切。", "镜头4（-1.0–0.0秒）：非法附加镜头。\n硬切。", 1
            ),
            None,
        ),
        (
            "duplicate_dialogue",
            MULTI.replace(
                "台词结束后闭嘴",
                "她重复说道：“你还是来了。”台词结束后闭嘴",
            ),
            legacy_contract,
        ),
        (
            "missing_dialogue",
            MULTI.replace("你还是来了。", "你终于来了。"),
            legacy_contract,
        ),
        (
            "wrong_dialogue_speaker",
            MULTI.replace(
                "沈清霜侧脸近景，她没有回头；沈清霜轻声说道",
                "桥外雨幕近景，墨尘画外说道",
            ),
            legacy_contract,
        ),
        (
            "asset_contract_wrong_order",
            MULTI,
            {
                **legacy_contract,
                "expected_assets": ["图片2", "图片1", "图片3", "图片4"]
            },
        ),
        (
            "shot_count_mismatch",
            MULTI,
            {**legacy_contract, "expected_shot_count": 2},
        ),
    ]

    for name, prompt, contract in mutations:
        add(name, validate_prompt(prompt, contract=contract).ok, False)

    for internal_term in (
        "operation",
        "task_kind",
        "sequence_scope",
        "AssetMap",
        "SeamState",
        "VisibilityState",
        "world_roster",
        "full_frame",
        "partial_frame",
        "offscreen",
        "source_cut_id",
        "EvidenceGraph",
        "SequencePlan",
        "PromptEmitter",
        "WorldState",
        "ShotPlan",
        "unique_derived",
        "unresolved",
    ):
        add_error(
            f"internal_tracker_{internal_term}_rejected",
            validate_prompt(
                GENERATION_PLOT_ONLY.replace(
                    "石桥空镜",
                    f"{internal_term}：石桥空镜",
                    1,
                )
            ),
            "不得输出内部追踪词",
        )

    add_error(
        "invalid_task_kind_rejected",
        validate_prompt(
            GENERATION_PLOT_ONLY,
            contract={"task_kind": "editing", "expected_shot_count": 1},
        ),
        "task_kind 必须是 generation 或 extension",
    )
    add_error(
        "boolean_task_kind_rejected",
        validate_prompt(
            GENERATION_PLOT_ONLY,
            contract={"task_kind": True, "expected_shot_count": 1},
        ),
        "task_kind 必须是 generation 或 extension",
    )
    add_error(
        "generation_rejects_extension_heading_when_explicit",
        validate_prompt(
            EXTENSION_MINIMAL,
            contract={"task_kind": "generation", "expected_shot_count": 2},
        ),
        "task_kind=generation 不允许栏目：视频延长",
    )
    add_error(
        "extension_requires_video_extension_heading",
        validate_prompt(
            "情节：" + EXTENSION_MINIMAL.split("\n\n情节：", 1)[1],
            contract={"task_kind": "extension", "expected_shot_count": 2},
        ),
        "缺少必需标题：视频延长",
    )
    add_error(
        "extension_requires_source_video_binding",
        validate_prompt(
            EXTENSION_MINIMAL.replace("视频1", "源视频", 1),
            contract={"task_kind": "extension", "expected_shot_count": 2},
        ),
        "视频延长栏目必须绑定源视频素材",
    )
    add_error(
        "generation_rejects_new_shot_prefix",
        validate_prompt(
            GENERATION_PLOT_ONLY.replace("镜头1", "新增镜头1", 1),
            contract={"task_kind": "generation", "expected_shot_count": 1},
        ),
        "与 task_kind=generation 不符；应使用 镜头N",
    )
    add_error(
        "extension_rejects_generation_shot_prefix",
        validate_prompt(
            EXTENSION_MINIMAL.replace("新增镜头", "镜头"),
            contract={"task_kind": "extension", "expected_shot_count": 2},
        ),
        "与 task_kind=extension 不符；应使用 新增镜头N",
    )
    add_error(
        "malformed_extension_shot_header_rejected",
        validate_prompt(
            EXTENSION_MINIMAL.replace("新增镜头1", "新增镜头X", 1)
        ),
        "无法解析的镜头头",
    )
    add(
        "natural_body_starting_with_new_shot_first_time_is_not_header",
        validate_prompt(
            EXTENSION_MINIMAL.replace(
                "新增镜头1（0.0–1.5秒）：固定机位",
                "新增镜头1（0.0–1.5秒）：\n新增镜头一开始保持固定机位",
                1,
            )
        ).ok,
    )
    extension_transition_only = EXTENSION_MINIMAL.replace(
        "新增镜头1（0.0–1.5秒）：固定机位，沈清霜先抬眼看向桥外，镜头结束时保持沉默。\n硬切至新增镜头2。",
        "新增镜头1（0.0–1.5秒）：\n硬切至新增镜头2。",
        1,
    )
    add_error(
        "extension_transition_only_shot_body_rejected",
        validate_prompt(extension_transition_only),
        "新增镜头1正文为空",
    )
    add_error(
        "extension_non_contiguous_number_rejected",
        validate_prompt(
            EXTENSION_MINIMAL.replace("新增镜头2", "新增镜头3")
        ),
        "镜头编号不连续",
    )

    add_error(
        "sound_heading_requires_audio_asset",
        validate_prompt(
            GENERATION_SOUND.replace(
                "音频1只参考沈清霜的音色与克制的说话气质。",
                "保持克制、低沉的声音。",
                1,
            )
        ),
        "声音栏目必须绑定至少一个音频素材",
    )
    add_error(
        "sound_heading_rejects_image_asset",
        validate_prompt(
            GENERATION_SOUND.replace(
                "音频1只参考沈清霜的音色与克制的说话气质。",
                "图片1：参考沈清霜的说话气质。",
                1,
            )
        ),
        "声音栏目只允许绑定音频素材",
    )
    add_error(
        "expected_headings_exact_mismatch_rejected",
        validate_prompt(
            EXTENSION_FULL,
            contract={
                "task_kind": "extension",
                "expected_headings": ["视频延长", "主体", "情节"],
            },
        ),
        "栏目不符",
    )
    add_error(
        "expected_headings_duplicate_rejected",
        validate_prompt(
            GENERATION_PLOT_ONLY,
            contract={
                "task_kind": "generation",
                "expected_headings": ["情节", "情节"],
            },
        ),
        "expected_headings 不得包含重复栏目",
    )
    add_error(
        "expected_headings_wrong_shape_rejected",
        validate_prompt(
            GENERATION_PLOT_ONLY,
            contract={
                "task_kind": "generation",
                "expected_headings": "情节",
            },
        ),
        "expected_headings 必须是字符串数组",
    )
    add_error(
        "expected_headings_route_mismatch_rejected",
        validate_prompt(
            GENERATION_PLOT_ONLY,
            contract={
                "task_kind": "generation",
                "expected_headings": ["视频延长", "情节"],
            },
        ),
        "expected_headings 含有 task_kind=generation 不允许的栏目",
    )

    generation_without_tail = GENERATION_PLOT_ONLY.replace(
        "\n不添加字幕，不添加背景音乐。", ""
    )
    add(
        "explicit_inherit_tail_policy_can_release_generation_default",
        validate_prompt(
            generation_without_tail,
            contract={"task_kind": "generation", "tail_policy": "inherit_source"},
        ).ok,
    )
    add_error(
        "extension_generation_default_tail_policy_requires_fixed_tail",
        validate_prompt(
            EXTENSION_MINIMAL,
            contract={
                "task_kind": "extension",
                "tail_policy": "generation_default",
            },
        ),
        "提示词必须以“不添加字幕，不添加背景音乐。”收尾",
    )
    add_error(
        "invalid_tail_policy_rejected",
        validate_prompt(
            EXTENSION_MINIMAL,
            contract={"task_kind": "extension", "tail_policy": "custom"},
        ),
        "tail_policy 必须是 generation_default 或 inherit_source",
    )
    add_error(
        "empty_expected_tail_rejected",
        validate_prompt(
            EXTENSION_MINIMAL,
            contract={"task_kind": "extension", "expected_tail": ""},
        ),
        "expected_tail 必须是非空字符串",
    )
    add_error(
        "expected_tail_mismatch_rejected",
        validate_prompt(
            EXTENSION_MINIMAL,
            contract={
                "task_kind": "extension",
                "expected_tail": "保持源视频已有字幕。",
            },
        ),
        "提示词必须以合同指定收尾",
    )

    speaker_decoy = MULTI.replace(
        "沈清霜侧脸近景，她没有回头；沈清霜轻声说道",
        "沈清霜站在画面左侧，墨尘画外说道",
    )
    add_error(
        "speaker_name_elsewhere_does_not_authorize_dialogue",
        validate_prompt(speaker_decoy, contract=legacy_contract),
        "对白说话人不符",
    )
    recipient_decoy = MULTI.replace(
        "沈清霜侧脸近景，她没有回头；沈清霜轻声说道",
        "沈清霜侧脸近景，她没有回头；墨尘对沈清霜轻声说道",
    )
    add_error(
        "dialogue_recipient_not_mistaken_for_speaker",
        validate_prompt(recipient_decoy, contract=legacy_contract),
        "对白说话人不符",
    )
    observed_speaker_decoy = MULTI.replace(
        "沈清霜侧脸近景，她没有回头；沈清霜轻声说道",
        "墨尘看着沈清霜轻声说道",
    )
    add_error(
        "observed_character_not_mistaken_for_speaker",
        validate_prompt(observed_speaker_decoy, contract=legacy_contract),
        "对白说话人不符",
    )
    mixed_speakers = MULTI.replace(
        "沈清霜轻声说道：“你还是来了。”台词结束后闭嘴",
        "沈清霜轻声说道：“你还是来了。”墨尘接着说道：“你还是来了。”随后两人闭嘴",
    )
    add_error(
        "each_dialogue_occurrence_needs_own_speaker_attribution",
        validate_prompt(
            mixed_speakers,
            contract={
                **legacy_contract,
                "exact_dialogue": [
                    {"text": "你还是来了。", "count": 2, "speaker": "沈清霜"}
                ]
            },
        ),
        "对白说话人不符",
    )

    empty_shot = MULTI.replace(
        "镜头2（1.5–3.5秒）：沈清霜侧脸近景，她没有回头；沈清霜轻声说道：“你还是来了。”台词结束后闭嘴，视线仍朝向桥外。\n反打切至镜头3。",
        "镜头2（1.5–3.5秒）：\n反打切至镜头3。",
    )
    add_error(
        "empty_shot_body_rejected",
        validate_prompt(empty_shot),
        "镜头2正文为空",
    )
    transition_only_lines = (
        "反打。",
        "反打切。",
        "反打镜头。",
        "随后硬切。",
        "硬切到下一镜。",
        "切镜。",
        "不切镜。",
        "跳切。",
        "交叉溶解。",
        "硬切转场。",
        "直接硬切。",
        "切换至下一镜。",
        "声音桥接至镜头3。",
        "动作匹配切至镜头3。",
        "动作匹配切到镜头2。",
        "视线匹配切。",
        "构图匹配切至下一镜。",
        "遮挡转场至下一镜。",
    )
    for index, transition in enumerate(transition_only_lines, start=1):
        transition_only_shot = empty_shot.replace(
            "反打切至镜头3。", transition, 1
        )
        add_error(
            f"transition_only_shot_body_{index}",
            validate_prompt(transition_only_shot),
            "镜头2正文为空",
        )
    add_error(
        "hash_shot_header_rejected",
        validate_prompt(
            MULTI.replace("镜头2（1.5–3.5秒）", "镜头#99（1.5–3.5秒）")
        ),
        "无法解析的镜头头",
    )
    add_error(
        "underscored_extra_shot_header_rejected",
        validate_prompt(
            MULTI.replace(
                "\n\n不添加字幕，不添加背景音乐。",
                "\n镜头_99（5.0–5.5秒）：非法附加镜头。\n\n不添加字幕，不添加背景音乐。",
            ),
            contract=legacy_contract,
        ),
        "无法解析的镜头头",
    )
    malformed_extra_headers = {
        "ordinal_prefix_extra_shot_rejected": "第99镜头（5.0–5.5秒）：非法附加镜头。",
        "ordinal_number_suffix_extra_shot_rejected": "第99号镜头（5.0–5.5秒）：非法附加镜头。",
        "middle_dot_extra_shot_rejected": "镜头·99（5.0–5.5秒）：非法附加镜头。",
        "circled_digit_extra_shot_rejected": "镜头①（5.0–5.5秒）：非法附加镜头。",
        "ordinal_after_word_extra_shot_rejected": "镜头第99（5.0–5.5秒）：非法附加镜头。",
        "number_prefix_extra_shot_rejected": "镜头No.99（5.0–5.5秒）：非法附加镜头。",
        "middle_dot_chinese_extra_shot_rejected": "镜头·九（5.0–5.5秒）：非法附加镜头。",
    }
    for name, extra_header in malformed_extra_headers.items():
        add_error(
            name,
            validate_prompt(
                MULTI.replace(
                    "\n\n不添加字幕，不添加背景音乐。",
                    f"\n{extra_header}\n\n不添加字幕，不添加背景音乐。",
                ),
                contract=legacy_contract,
            ),
            "无法解析的镜头头",
        )
    add(
        "natural_body_starting_with_jingtou_yi_is_not_header",
        validate_prompt(
            SINGLE.replace(
                "镜头1（0.0–5.0秒）：同一连续镜头，不切镜。",
                "镜头1（0.0–5.0秒）：\n镜头一开始保持固定机位，不切镜。",
            )
        ).ok,
    )
    add(
        "natural_body_starting_with_jingtou_first_time_is_not_header",
        validate_prompt(
            SINGLE.replace(
                "镜头1（0.0–5.0秒）：同一连续镜头，不切镜。",
                "镜头1（0.0–5.0秒）：\n镜头第一时间保持固定机位，不切镜。",
            )
        ).ok,
    )
    huge_shot_number = "9" * 5000
    add_error(
        "huge_shot_number_controlled_error",
        validate_prompt(
            MULTI.replace("镜头2（1.5–3.5秒）", f"镜头{huge_shot_number}（1.5–3.5秒）")
        ),
        "镜头编号过长",
    )

    add_error(
        "indented_ui_heading_ascii_colon_rejected",
        validate_prompt(MULTI.replace("风格：\n", "风格：\n  分辨率: 1080p\n", 1)),
        "UI参数不得进入提示词",
    )
    add_error(
        "ui_parameters_in_natural_sentence_rejected",
        validate_prompt(
            MULTI.replace(
                "3D渲染的国漫CG动画，冷灰色雨夜光线，写实材质。",
                "3D渲染的国漫CG动画。输出分辨率设为4K，画幅16:9，帧率24fps。",
            )
        ),
        "UI参数不得进入提示词",
    )
    ui_prose_leaks = {
        "ui_frames_per_second_chinese_rejected": "按每秒24帧输出。",
        "ui_chinese_aspect_ratio_rejected": "采用16比9的横向画面比例。",
        "ui_vertical_chinese_ratio_rejected": "使用九比十六的竖屏画幅。",
        "ui_pixel_dimensions_rejected": "画面尺寸设为2048×1152。",
        "ui_integral_parameter_rejected": "积分设为30。",
        "ui_plain_frame_ratio_rejected": "画面为16:9。",
        "ui_ratio_output_rejected": "采用16:9比例输出。",
        "ui_video_ratio_rejected": "视频比例为9:16。",
        "ui_frames_slash_second_rejected": "按24帧/秒输出。",
    }
    for name, leak in ui_prose_leaks.items():
        add_error(
            name,
            validate_prompt(
                MULTI.replace(
                    "3D渲染的国漫CG动画，冷灰色雨夜光线，写实材质。",
                    "3D渲染的国漫CG动画，冷灰色雨夜光线，写实材质。" + leak,
                )
            ),
            "UI参数不得进入提示词",
        )
    add(
        "story_clock_time_not_mistaken_for_aspect_ratio",
        validate_prompt(
            MULTI.replace(
                "细雨持续落下，桥面湿润反光",
                "墙上时钟停在10:30，倒计时牌显示8:05；细雨持续落下，桥面湿润反光",
            )
        ).ok,
    )
    add(
        "diegetic_screen_orientation_and_composition_not_ui",
        validate_prompt(
            MULTI.replace(
                "细雨持续落下，桥面湿润反光",
                "手机以竖屏显示来电，人物停在画幅边缘；细雨持续落下，桥面湿润反光",
            )
        ).ok,
    )
    add_error(
        "indented_internal_heading_chinese_colon_rejected",
        validate_prompt(MULTI.replace("风格：\n", "风格：\n  自检结果：通过\n", 1)),
        "不得暴露内部审查或员工说明",
    )
    add_error(
        "h3_field_chinese_colon_rejected",
        validate_prompt(
            MULTI.replace("风格：\n", "风格：\nsubject_definitions：内部值\n", 1)
        ),
        "不得输出 H3 Context-IR 字段",
    )
    internal_tokens = (
        "storyboard_status",
        "duration_source",
        "compiled_segment_id",
        "source_cut_ids",
        "source_cut_count",
        "version_state",
        "source_cut_scope",
        "SegmentMap",
        "SceneState",
        "ShotRecord",
        "NarrativeMap",
    )
    for token in internal_tokens:
        add_error(
            f"internal_tracking_token_{token}",
            validate_prompt(
                MULTI.replace("风格：\n", f"风格：\n{token}=internal\n", 1)
            ),
            "不得输出内部追踪词",
        )

    role_line = "图片1：沈清霜的外貌、发型与白色衣裙。"
    role_in_scene = MULTI.replace(role_line, "", 1).replace(
        "场景：\n", f"场景：\n{role_line}\n", 1
    )
    add_error(
        "role_asset_must_be_in_subject_section",
        validate_prompt(
            role_in_scene,
            contract={
                "subject_required": True,
                "expected_assets": ["图片2", "图片3", "图片1", "图片4"],
                "expected_asset_sections": {"图片1": "主体"},
            },
        ),
        "素材栏目不符：图片1 期望位于主体，实际位于场景",
    )
    add_error(
        "asset_section_contract_shape_rejected",
        validate_prompt(
            MULTI,
            contract={
                "subject_required": True,
                "expected_asset_sections": ["图片1", "主体"],
            },
        ),
        "expected_asset_sections 必须是标签到栏目的映射",
    )
    add_error(
        "asset_section_contract_must_cover_every_expected_asset",
        validate_prompt(
            MULTI,
            contract={
                "subject_required": True,
                "expected_assets": ["图片1", "图片2", "图片3", "图片4"],
                "expected_asset_sections": {"图片4": "场景"},
            },
        ),
        "expected_asset_sections 必须覆盖 expected_assets 的全部且仅有素材",
    )
    add_error(
        "asset_section_contract_rejects_extra_asset_key",
        validate_prompt(
            MULTI,
            contract={
                "subject_required": True,
                "expected_assets": ["图片1", "图片2", "图片3", "图片4"],
                "expected_asset_sections": {
                    "图片1": "主体",
                    "图片2": "主体",
                    "图片3": "主体",
                    "图片4": "场景",
                    "图片9": "场景",
                },
            },
        ),
        "expected_asset_sections 必须覆盖 expected_assets 的全部且仅有素材",
    )
    add_error(
        "expected_assets_requires_section_map",
        validate_prompt(
            MULTI,
            contract={
                "subject_required": True,
                "expected_assets": ["图片1", "图片2", "图片3", "图片4"],
            },
        ),
        "expected_assets 与 expected_asset_sections 必须成对出现",
    )
    add_error(
        "section_map_requires_expected_assets",
        validate_prompt(
            MULTI,
            contract={
                "subject_required": True,
                "expected_asset_sections": {
                    "图片1": "主体",
                    "图片2": "主体",
                    "图片3": "主体",
                    "图片4": "场景",
                },
            },
        ),
        "expected_assets 与 expected_asset_sections 必须成对出现",
    )
    add_error(
        "expected_assets_rejects_invalid_label",
        validate_prompt(
            MULTI,
            contract={
                "subject_required": True,
                "expected_assets": ["角色图1"],
                "expected_asset_sections": {"角色图1": "主体"},
            },
        ),
        "expected_assets 每项必须是图片N、音频N或视频N",
    )
    add_error(
        "expected_assets_rejects_duplicate_label",
        validate_prompt(
            MULTI,
            contract={
                "subject_required": True,
                "expected_assets": ["图片1", "图片1"],
                "expected_asset_sections": {"图片1": "主体"},
            },
        ),
        "expected_assets 不得包含重复素材标签",
    )

    environment_with_character = ENVIRONMENT.replace(
        "山谷大全景固定机位，薄雾沿山势向右缓移，前景竹叶轻晃，远处山脊逐渐从雾中显露。",
        "沈清霜从竹林小路走入山谷，最终停在画面中央。",
    )
    add_error(
        "character_segment_requires_subject_heading",
        validate_prompt(
            environment_with_character,
            contract={**environment_contract, "subject_required": True},
        ),
        "当前生成段要求主体标题",
    )
    add_error(
        "omitted_subject_requires_explicit_contract_flag",
        validate_prompt(
            ENVIRONMENT,
            contract={
                key: value
                for key, value in environment_contract.items()
                if key != "subject_required"
            },
        ),
        "contract 必须包含布尔字段 subject_required",
    )
    add_error(
        "present_subject_requires_true_contract_flag",
        validate_prompt(
            MULTI,
            contract={**legacy_contract, "subject_required": False},
        ),
        "contract 声明无需主体标题，但提示词包含主体",
    )
    add_error(
        "present_subject_still_requires_contract_flag",
        validate_prompt(
            MULTI,
            contract={
                key: value
                for key, value in legacy_contract.items()
                if key != "subject_required"
            },
        ),
        "contract 必须包含布尔字段 subject_required",
    )
    add_error(
        "subject_required_must_be_boolean",
        validate_prompt(
            ENVIRONMENT,
            contract={**environment_contract, "subject_required": "false"},
        ),
        "subject_required 必须是布尔值",
    )
    add_error(
        "subject_required_null_rejected",
        validate_prompt(
            MULTI,
            contract={**legacy_contract, "subject_required": None},
        ),
        "subject_required 必须是布尔值",
    )
    add_error(
        "null_asset_contract_fields_rejected",
        validate_prompt(
            MULTI,
            contract={
                "subject_required": True,
                "expected_assets": None,
                "expected_asset_sections": None,
            },
        ),
        "expected_assets 必须是字符串数组",
    )
    add_error(
        "subject_false_conflicts_with_dialogue",
        validate_prompt(
            ENVIRONMENT,
            contract={
                **environment_contract,
                "exact_dialogue": [
                    {"text": "你还是来了。", "count": 0, "speaker": "沈清霜"}
                ],
            },
        ),
        "subject_required=false 与非空 exact_dialogue 矛盾",
    )

    add_error(
        "shot_count_float_not_truncated",
        validate_prompt(
            MULTI,
            contract={"subject_required": True, "expected_shot_count": 3.7},
        ),
        "expected_shot_count 必须是整数",
    )
    add_error(
        "shot_count_bool_not_int",
        validate_prompt(
            MULTI,
            contract={"subject_required": True, "expected_shot_count": True},
        ),
        "不能是布尔值",
    )
    add_error(
        "shot_count_null_rejected",
        validate_prompt(
            MULTI,
            contract={"subject_required": True, "expected_shot_count": None},
        ),
        "expected_shot_count 必须是整数",
    )
    add_error(
        "dialogue_count_float_not_truncated",
        validate_prompt(
            MULTI,
            contract={
                "subject_required": True,
                "exact_dialogue": [
                    {"text": "你还是来了。", "count": 1.5, "speaker": "沈清霜"}
                ]
            },
        ),
        "对白 '你还是来了。' 的 count 必须是整数",
    )
    add_error(
        "dialogue_count_bool_not_int",
        validate_prompt(
            MULTI,
            contract={
                "subject_required": True,
                "exact_dialogue": [
                    {"text": "你还是来了。", "count": True, "speaker": "沈清霜"}
                ]
            },
        ),
        "不能是布尔值",
    )
    wrong_dialogue_owner = MULTI.replace(
        "沈清霜侧脸近景，她没有回头；沈清霜轻声说道",
        "墨尘侧脸近景，他没有回头；墨尘轻声说道",
    )
    add_error(
        "dialogue_item_missing_speaker_rejected",
        validate_prompt(
            wrong_dialogue_owner,
            contract={
                **legacy_contract,
                "exact_dialogue": [{"text": "你还是来了。", "count": 1}],
            },
        ),
        "speaker 必须是非空字符串",
    )
    add_error(
        "dialogue_item_null_speaker_rejected",
        validate_prompt(
            wrong_dialogue_owner,
            contract={
                **legacy_contract,
                "exact_dialogue": [
                    {"text": "你还是来了。", "count": 1, "speaker": None}
                ],
            },
        ),
        "speaker 必须是非空字符串",
    )
    add_error(
        "expected_duration_bool_rejected",
        validate_prompt(
            MULTI,
            contract={"subject_required": True, "expected_duration": True},
        ),
        "expected_duration 必须是有效数字，不能是布尔值",
    )
    for non_finite in ("NaN", "Infinity", "-Infinity"):
        add_error(
            f"expected_duration_non_finite_{non_finite}",
            validate_prompt(
                MULTI,
                contract={
                    "subject_required": True,
                    "expected_duration": non_finite,
                },
            ),
            "expected_duration 必须是有效数字",
        )
    add_error(
        "empty_exact_dialogue_text_rejected",
        validate_prompt(
            MULTI,
            contract={
                "subject_required": True,
                "exact_dialogue": [{"text": ""}],
            },
        ),
        "exact_dialogue 的 text 必须是非空字符串",
    )
    add_error(
        "batch_block_count_float_not_truncated",
        validate_response(
            batch_response(MULTI, SINGLE),
            contract={"expected_blocks": 2.0, "segments": [legacy_contract, single_contract]},
        ),
        "批量合同 expected_blocks 必须是整数",
    )
    add_error(
        "batch_block_count_bool_not_int",
        validate_response(
            batch_response(MULTI, SINGLE),
            contract={"expected_blocks": True, "segments": [legacy_contract, single_contract]},
        ),
        "不能是布尔值",
    )

    add_error(
        "unsupported_fence_info_string",
        validate_response(f"```python\n{MULTI}\n```"),
        "不支持的代码块类型：python",
    )
    add_error(
        "inline_opening_fence_rejected",
        validate_response(f"前言```text\n{MULTI}\n```"),
        "Markdown围栏必须独立成行",
    )
    add_error(
        "inline_closing_fence_rejected",
        validate_response(f"```text\n{MULTI}\n``` 后缀"),
        "Markdown闭合围栏必须以 ``` 独立成行",
    )
    add_error(
        "unclosed_fence_rejected",
        validate_response(f"```text\n{MULTI}"),
        "Markdown代码块未闭合",
    )

    add(
        "duration_mismatch",
        validate_prompt(MULTI, expected_duration=Decimal("6.0")).ok,
        False,
    )
    add(
        "contract_duration_conflicts_with_cli",
        validate_prompt(
            MULTI,
            expected_duration=Decimal("5.0"),
            contract={"subject_required": True, "expected_duration": "6.0"},
        ).ok,
        False,
    )
    add(
        "outside_codeblock",
        validate_response(f"这里是结果：\n{fenced(MULTI)}").ok,
        False,
    )
    add("missing_codeblock", validate_response(MULTI).ok, False)

    add_error(
        "full_sequence_rejects_multiple_code_blocks",
        validate_response(
            batch_response(EXTENSION_FULL, EXTENSION_FULL),
            contract=extension_contract,
        ),
        "代码块数量不符：期望 1，实际 2",
    )
    add_error(
        "full_sequence_requires_expected_blocks",
        validate_response(
            fenced(GENERATION_PLOT_ONLY),
            contract={
                "task_kind": "generation",
                "delivery_mode": "full_sequence",
                "expected_shot_count": 1,
            },
        ),
        "delivery_mode=full_sequence 必须包含 expected_blocks=1",
    )
    add_error(
        "full_sequence_requires_expected_shot_count",
        validate_response(
            fenced(GENERATION_PLOT_ONLY),
            contract={
                "task_kind": "generation",
                "delivery_mode": "full_sequence",
                "expected_blocks": 1,
            },
        ),
        "delivery_mode=full_sequence 必须包含 expected_shot_count",
    )
    add_error(
        "flat_expected_blocks_cannot_request_multiple_blocks",
        validate_response(
            batch_response(MULTI, SINGLE),
            contract={
                "task_kind": "generation",
                "expected_blocks": 2,
                "expected_shot_count": 3,
            },
        ),
        "非批量合同 expected_blocks 必须为1",
    )
    add_error(
        "flat_expected_blocks_float_rejected",
        validate_response(
            fenced(GENERATION_PLOT_ONLY),
            contract={
                "task_kind": "generation",
                "expected_blocks": 1.0,
                "expected_shot_count": 1,
            },
        ),
        "expected_blocks 必须是整数",
    )
    add_error(
        "invalid_delivery_mode_rejected",
        validate_response(
            fenced(GENERATION_PLOT_ONLY),
            contract={
                "task_kind": "generation",
                "delivery_mode": "per_shot",
                "expected_blocks": 1,
                "expected_shot_count": 1,
            },
        ),
        "delivery_mode 只支持 full_sequence",
    )
    add_error(
        "full_sequence_rejects_legacy_batch_segments",
        validate_response(
            batch_response(MULTI, SINGLE),
            contract={**batch_contract, "delivery_mode": "full_sequence"},
        ),
        "delivery_mode=full_sequence 不能与旧批量 segments 同时使用",
    )

    add(
        "batch_block_count_mismatch",
        validate_response(
            batch_response(MULTI), contract=batch_contract
        ).ok,
        False,
    )
    add(
        "batch_segment_count_mismatch",
        validate_response(
            batch_response(MULTI, SINGLE),
            contract={"expected_blocks": 2, "segments": [legacy_contract]},
        ).ok,
        False,
    )
    add(
        "batch_segment_duration_mismatch",
        validate_response(
            batch_response(MULTI, SINGLE),
            contract={
                "expected_blocks": 2,
                "segments": [
                    {**batch_contract["segments"][0], "expected_duration": 6},
                    single_contract,
                ],
            },
        ).ok,
        False,
    )
    add(
        "batch_segment_asset_mismatch",
        validate_response(
            batch_response(MULTI, SINGLE),
            contract={
                "expected_blocks": 2,
                "segments": [
                    {
                        **batch_contract["segments"][0],
                        "expected_assets": ["图片1"],
                        "expected_asset_sections": {"图片1": "主体"},
                    },
                    single_contract,
                ],
            },
        ).ok,
        False,
    )
    add(
        "batch_segment_speaker_mismatch",
        validate_response(
            batch_response(MULTI, SINGLE),
            contract={
                "expected_blocks": 2,
                "segments": [
                    {
                        **batch_contract["segments"][0],
                        "exact_dialogue": [
                            {
                                "text": "你还是来了。",
                                "count": 1,
                                "speaker": "不存在的说话人",
                            }
                        ],
                    },
                    single_contract,
                ],
            },
        ).ok,
        False,
    )
    add(
        "legacy_contract_rejected_for_batch",
        validate_response(
            batch_response(MULTI, SINGLE), contract=legacy_contract
        ).ok,
        False,
    )
    add(
        "global_duration_rejected_for_batch",
        validate_response(
            batch_response(MULTI, SINGLE), expected_duration=Decimal("5.0")
        ).ok,
        False,
    )
    add(
        "segments_without_expected_blocks",
        validate_response(
            batch_response(MULTI, SINGLE),
            contract={"segments": [legacy_contract, single_contract]},
        ).ok,
        False,
    )
    add(
        "batch_segment_must_be_object",
        validate_response(
            batch_response(MULTI, SINGLE),
            contract={"expected_blocks": 2, "segments": [legacy_contract, "bad"]},
        ).ok,
        False,
    )
    add(
        "batch_contract_rejected_for_prompt_mode",
        validate_prompt(MULTI, contract=batch_contract).ok,
        False,
    )

    validator_path = Path(__file__).with_name("validate_prompt.py")
    with tempfile.TemporaryDirectory(prefix="manju-validator-tests-") as temp_dir:
        temp_path = Path(temp_dir)
        prompt_path = temp_path / "prompt.txt"
        prompt_path.write_text(MULTI, encoding="utf-8")

        invalid_duration = subprocess.run(
            [
                sys.executable,
                "-B",
                "-X",
                "utf8",
                str(validator_path),
                str(prompt_path),
                "--expected-duration",
                "not-a-number",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        add_cli_error(
            "cli_invalid_expected_duration_controlled",
            invalid_duration,
            "--expected-duration 必须是有效有限数字",
        )

        bad_contract_path = temp_path / "bad-contract.json"
        bad_contract_path.write_text('{"expected_blocks":', encoding="utf-8")
        invalid_json = subprocess.run(
            [
                sys.executable,
                "-B",
                "-X",
                "utf8",
                str(validator_path),
                str(prompt_path),
                "--contract",
                str(bad_contract_path),
                "--json",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        add_cli_error(
            "cli_invalid_contract_json_controlled",
            invalid_json,
            "合同JSON无法解析",
            json_mode=True,
        )

        null_contract_path = temp_path / "null-contract.json"
        null_contract_path.write_text("null", encoding="utf-8")
        null_contract = subprocess.run(
            [
                sys.executable,
                "-B",
                "-X",
                "utf8",
                str(validator_path),
                str(prompt_path),
                "--contract",
                str(null_contract_path),
                "--json",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        add_cli_error(
            "cli_null_contract_rejected",
            null_contract,
            "contract 必须是JSON对象，不能是 null",
            json_mode=True,
        )

        missing_input = subprocess.run(
            [
                sys.executable,
                "-B",
                "-X",
                "utf8",
                str(validator_path),
                str(temp_path / "missing-prompt.txt"),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        add_cli_error(
            "cli_missing_input_file_controlled",
            missing_input,
            "无法读取提示词文件",
        )

        missing_contract = subprocess.run(
            [
                sys.executable,
                "-B",
                "-X",
                "utf8",
                str(validator_path),
                str(prompt_path),
                "--contract",
                str(temp_path / "missing-contract.json"),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        add_cli_error(
            "cli_missing_contract_file_controlled",
            missing_contract,
            "无法读取合同文件",
        )

    from run_release_checks import validate_manifest

    manifest_path = Path(__file__).resolve().parents[1] / "evals" / "manifest.json"
    add("release_manifest_current_schema_valid", validate_manifest(manifest_path).ok)
    with tempfile.TemporaryDirectory(prefix="manju-release-schema-tests-") as temp_dir:
        temp_path = Path(temp_dir)

        duplicate_key_path = temp_path / "duplicate-key.json"
        duplicate_key_path.write_text(
            '{"schema_version":"1.1","schema_version":"1.1"}',
            encoding="utf-8",
        )
        duplicate_result = validate_manifest(duplicate_key_path)
        add(
            "release_manifest_duplicate_key_rejected",
            not duplicate_result.ok
            and any("重复键" in error for error in duplicate_result.errors),
        )

        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_payload["mutations"][0]["expected_dimensions"] = [{"bad": True}]
        malformed_dimension_path = temp_path / "malformed-dimension.json"
        malformed_dimension_path.write_text(
            json.dumps(manifest_payload, ensure_ascii=False),
            encoding="utf-8",
        )
        malformed_result = validate_manifest(malformed_dimension_path)
        add(
            "release_manifest_nonstring_dimension_controlled",
            not malformed_result.ok
            and any(
                "expected_dimensions[0] 必须是非空字符串" in error
                for error in malformed_result.errors
            ),
        )

        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_payload.pop("validity_controls")
        missing_controls_path = temp_path / "missing-controls.json"
        missing_controls_path.write_text(
            json.dumps(manifest_payload, ensure_ascii=False),
            encoding="utf-8",
        )
        missing_controls_result = validate_manifest(missing_controls_path)
        add(
            "release_manifest_validity_controls_required",
            not missing_controls_result.ok
            and any(
                "validity_controls" in error
                for error in missing_controls_result.errors
            ),
        )

    failures = [
        f"{name}: expected {expected}, got {actual}"
        for name, actual, expected in cases
        if actual != expected
    ]
    if failures:
        print("FAIL")
        for failure in failures:
            print(failure)
        return 1

    print(f"PASS: {len(cases)} regression and mutation cases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
