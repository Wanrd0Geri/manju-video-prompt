# Manju Semantic Release V3

日期：2026-08-21
状态：`text-validated`，不是 `video-validated`

## 结果

- 旧版与候选版八案匿名盲评：旧版 110/168，仅 1/8 通过；候选版两名独立评审分别给出 167/168 与 168/168，均为 8/8 通过，逐案例、逐维度无回退。
- 新增路由靶向评测：最终 C02 视频延长 21/21；C09 生成前提示词预检 21/21。
- 语义 mutation 门禁：25/25 `CAUGHT`；其中 19 项为 `critical`，0 `MISSED`，0 `BLOCKED`。
- 合法变体门禁：3/3 `ACCEPTED`，0 `FALSE POSITIVE`，0 `BLOCKED`。
- 确定性发布检查：9 cases、25 mutations、3 validity controls、9 canonical responses；221 项机械回归全部通过。

## 可复现依据

- 输入、oracle、mutations 与合法变体：[manifest.json](manifest.json)
- 评分与发布门槛：[semantic-rubric.md](semantic-rubric.md)
- 唯一 clean baseline：[fixtures/clean-responses.md](fixtures/clean-responses.md)
- 机械与元数据入口：`python3 -B -X utf8 scripts/run_release_checks.py`

所有 mutation 均从仓库内 canonical response 出发，只执行 manifest 中的确定替换或插入。`expected_dimensions` 是必须降分的最小集合，`oracle_hooks` 是至少必须引用的 oracle 字段；额外有证据的直接影响可以补充，但不能代替合同要求。

## 边界

本报告验证提示词文本、诊断路由、延长接缝、空间几何、素材/声音绑定、完整序列交付及评测器特异性。尚未在 Seedance 2.5、Wan 3.0 或 Hailuo H3 对 V3 进行真实生成，因此不证明人物一致性、口型、多人站位或视频接缝的实际成片表现。

系统 `quick_validate.py` 因本机 Python 缺少 PyYAML 未运行；未为此新增运行依赖。Frontmatter 已用系统 Ruby YAML 解析验证，Markdown 引用、JSON、Python 编译、`git diff --check` 与发布脚本另行通过。
