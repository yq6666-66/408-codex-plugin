# GPT-6 实际回答验收 harness

**已发布基线：v2.5.1。** 旧验收包含 17 条用例，结果为 17/17、60/60 checkpoint，并通过严格 `regressionGate`；历史摘要见 [`results-v2.5.1.md`](results-v2.5.1.md)。当前候选 `v2.5.2` 尚未发布，本目录增加了 3 条多轮状态用例，完整清单现为 20 条。v2.5.2 的真实模型验收仍待完成，不能用工程测试代替。

## 目的

把“工程质量”和“GPT-6 实际回答质量”分开验收：

- 工程测试：`python scripts/check.py`、unittest —— 验证代码、契约与脚本。
- GPT-6 验收：本目录的用例在真实宿主上运行并记录回答 —— 验证教学行为。

## 测试材料

- [`cases.json`](cases.json)：20 个用例，覆盖数学、英语、408、政治、真题/招生信息、模考、便携记录、工具降级和多轮教学状态。前 17 条是 v2.5.1 已发布基线；18—20 条增加提示续接、多题续讲和题面修正后重算。

## 运行步骤（新旧版本对比）

1. **同一宿主、同一模型、同一推理档位**：新旧两版必须条件一致。
2. 历史发布对照：可用固定 tag 安装旧版 v2.4.0，与已发布 v2.5.1 做历史比较。
3. 当前候选验收：使用 `codex/reliability-hardening` 分支打包的 v2.5.2 候选；记录精确 manifest 版本、包哈希和安装来源。该候选尚未发布，不应把正式安装切换到候选版本。比较新增 18—20 条时，旧版也须在完全相同的输入与 followUps 上重新运行；发布前完整比较必须包含相同的 20 条用例。
4. 每版逐条运行 `cases.json` 的用例；图片类用例使用 `materials/` 中的固定材料（或按 input 描述自备并记入 `inputMaterial`）。
5. 每条用例把模型真实回答、实际工具调用与逐条 checkpoint 判分记入一份 record JSON（模板见 [`record-template.json`](record-template.json)）。**必须粘贴模型真实输出，禁止编造或模拟回答。**
   原始运行是 Codex CLI JSONL 时，先提取可审计证据；输出只保留回答、工具事件、错误、完成状态、用量和原文件 SHA-256，不采纳模型文字自证工具调用：
   ```powershell
   python scripts/gpt6_capture.py --input run.jsonl --case-id gpt6-01-detailed-408 --input-material-file actual-turns.txt --artifact prompt-image.png=materials/prompt-image.png --output capture.json
   ```
   提取结果的 `recordCase` 可合入完整 record；`sourceEvidence` 保留原始 JSONL 哈希，`inputArtifacts` 绑定图片/材料摘要。`complete: false` 的记录不能参与判分；`errors` 需人工区分非阻塞警告与无效环境。只有 `toolCalls[].success: true` 且原始输出存在时，才能在 record 中声明工具成功。
6. 校验并出报告：
   ```powershell
   python scripts/gpt6_acceptance.py --record record-v2.4.0.json
   python scripts/gpt6_acceptance.py --record record-v2.5.1.json
   python scripts/gpt6_acceptance.py --record record-v2.5.2.json
   python scripts/gpt6_acceptance.py --compare record-v2.4.0.json record-v2.5.2.json
   ```

## 判分规则

- 每条用例的 `checkpoints` 是判分依据；`verdict` 必须引用回答原文或工具输出作为 evidence。
- 原始 JSONL 的 `sourceSha256` 用于绑定证据文件；它证明判分引用的是哪组事件，不证明回答正确。提取工具不读取 reasoning 文本，也不自动判定 checkpoint。
- **不得只因回答中出现指定关键词就判 pass**；checkpoint 要求的是行为与正确性。
- 对比验收标准：正确性不得回退、关键教学能力不得回退、新流程必须真正完成。
- harness 会拒绝空白和明显占位文本（如 `TODO`、`模拟回答`）；它不能证明输出来自真实模型，也不能自动核实 evidence 是否支持判分。真实性和判分正确性仍须人工复核。

## 记录要求

每份 record 必须保存：插件版本、模型版本、推理档位、宿主、输入材料、模型实际回答、工具调用结果、每条 checkpoint 的判分依据。


## 完整性与退出码

- `--record` 默认要求 `cases.json` 中全部 20 个用例各出现一次，缺失、重复或未知用例均退出 1；单用例记录不能代表完整验收。更新清单后，旧的 17 条记录只适用于原 v2.5.1 历史基线，不能直接用于新清单比较。
- 必填元数据必须是非空字符串且不能保留填写提示；`pluginVariant` 为 `old` 或 `new`，`runAt` 为带时区的 ISO 8601 时间。
- `inputMaterial` 和 `modelOutput` 必须是非空的非占位文本（简洁题允许如 `1/2` 的短回答）。`toolCalls` 必须存在；没有调用时用 `[]`。每次调用须记录非空字符串 `tool`、`input`、`output`；实际无输出时明确写“实际无输出”，不要省略字段或编造结果。
- 每个 checkpoint 必须逐字匹配目录、只判一次且全部覆盖。`verdict` 只允许 `pass`、`partial`、`fail`；`evidence` 必须是非空文本，不能用 `null`、数字或对象。若记录 `overall`，它必须与逐项判分一致。
- 结构或完整性错误退出 1；记录有效但含 `partial` 或 `fail` 也退出 1。只有完整记录的所有 checkpoint 均为 `pass`，`--record` 才退出 0。
- `--compare OLD NEW` 先独立校验两份完整记录，再核对 `pluginName`、`host`、`model`、`reasoningEffort` 一致，以及 `pluginVariant` 的 old/new 顺序。按用例和 checkpoint 检查 `pass > partial > fail` 的下降；任意下降退出 1，其他项目的改善不能抵消它。
- 同条件比较还要求按用例 ID 对应的 `inputMaterial` 完全一致，记录顺序可以不同。该字段应完整记录同一道题、附带材料和后续轮次输入；可选的 `inputArtifacts` 可保存图片或材料摘要，任一方提供时另一方必须提供相同值。两边均未提供该字段的旧记录仍可比较；脚本不会自行核实材料文件内容或摘要真实性。
- **比较退出 0 只表示未发现回退，不等于新版全部通过。** 必须同时检查新版的 `--record` 结果。报告中的 `regressions` 给出具体用例、checkpoint 和新旧判分。
- 单元测试中的 `synthetic` 数据仅用于验证校验器行为，不是实际 GPT-6 回答、验收记录或质量证据。

## 固定输入材料（2026-09-11）

`cases.json` 已补齐实际输入，图片路径相对本目录，材料位于 `materials/` 并提供 SHA-256。两张图片均为原创测试题，不冒充真题；院校材料是匿名虚构聚合数据。模考须按 `followUps` 在同一会话实际执行三轮，不能让模型一次模拟全部对话。检查点不提供给受测模型。

此次纠正了原目录的极限题分子描述矛盾、2027 招生年度与考试日期混淆、计算结果表达含混及简洁题强制解释；这些口径在新旧两版判分前统一。第14条固定选择无记录分支，不代表已覆盖有记录恢复。第16条是显式受限工具条件，不能据此声称真实宿主缺少 Python。
