# 模型可行性与证据等级

## 使用条件

仅在以下情况读取本文件：

- 用户要求针对具体模型判断能力；
- 素材数量、音频、时长或多镜头接近平台边界；
- 平台拒绝当前输入组合；
- 需要声称某项能力已经实测。

提示词继续使用同一套自然中文事实合同；平台选择只改变输入模式、时长和素材能力判断。

## 证据等级

- `live_cross_tested`：已在实际平台生成并人工检查；
- `official_documented`：当前官方资料明确支持；
- `static_compatible`：静态格式兼容，尚无同类生成验证；
- `unverified`：当前资料不足，需要重新核验。

## 项目证据快照

- Seedance 2.5：截至 2026-08-17，角色与场景绑定、对白、道具交接和多镜头结构完成项目实测。
- Hailuo H3：截至 2026-08-17，对应三类任务完成交叉实测。
- Wan 3.0：截至 2026-08-17，采用官方资料与静态兼容依据，尚未完成同规模付费多镜头交叉实测。

快照只用于标注证据等级。版本、素材数量、时长、分辨率和音频能力属于易变信息，执行硬性可行性判断时重新核验官方资料。

## 官方入口

- Seedance：<https://bytedance.larkoffice.com/wiki/RXh5ww6EqighMdkVTMccm2d4n7e>
- 火山引擎 Seedance：<https://www.volcengine.com/docs/82379/2222480?lang=zh>
- MiniMax H3：<https://github.com/MiniMax-AI/MiniMax-H3>
- H3 API：<https://platform.minimax.io/docs/api-reference/video-generation-v2-create>
- Wan：<https://wan.video/features>
- Wan 开源仓库：<https://github.com/Wan-Video>

## 能力检查

按当前平台依次核对：

1. 可选总时长和时间粒度；
2. 角色、场景、道具图片数量；
3. 音频输入、音色参考和对白能力；
4. 首尾帧或全能参考模式的素材职责；
5. 平台自动音频行为；
6. 当前模式的多镜头能力。

能力不足时优先拆段、切换输入模式或更换模型，保留锁定镜头、对白和故事事实。
