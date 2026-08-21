# Manju 评测分层

- 仓库根目录的 `test-prompts.json` 是快速 smoke 输入，只检查常用路由，不代表发布通过。
- `manifest.json` 与 `semantic-rubric.md` 是发布语义套件：clean cases 检查能力，mutations 检查错误能否被发现，validity controls 检查合法变体不会被误杀。
- `fixtures/clean-responses.md` 固定唯一通过基线；`release-report-v3.md` 记录当前已完成的文本发布证据与边界。
- `scripts/run_release_checks.py` 只验证评测元数据和确定性机械合同；它不会判断叙事、摄影语义或真实成片质量。
- 盲评 clean cases、实际 mutation/validity-control 结果和真实平台成片测试必须分别记录，不能互相替代。

运行确定性门禁：

```bash
python3 -B -X utf8 scripts/run_release_checks.py
```

状态标签：

- `mechanically-validated`：发布脚本通过；
- `text-validated`：clean cases、mutations 与 validity controls 的语义评测全部通过；
- `video-validated`：还需在指定平台、模型版本和输入模式完成真实生成并人工检查。
