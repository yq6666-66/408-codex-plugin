# v2.6.0 定向真实模型抽查

此目录定义 10 类新版本定向抽查，不替代旧版 20 条完整配对门禁，不沿用旧通过率。`cases.json` 中 `live` 场景使用实时网页；`synthetic` 场景使用明确虚构的固定材料，检验口径、降级与教学行为，不能证明真实院校数据或平台访问能力。判分条目不提供给受测模型。

## 宿主与证据

使用独立 `CODEX_HOME` 和每场景独立工作目录。候选通过官方 CLI 在隔离目录安装；确认 manifest、文件数和安装树摘要与冻结候选一致后运行。模型及推理档位固定为用户当前可用配置，运行前实际确认 CLI 版本；不得修改稳定安装或把 auth/config 内容写入仓库。

`run_cases.py` 调用真实 `codex exec --json`，多轮使用同一会话 `exec resume`；逐轮保存输入、stdout JSONL、stderr、工具 capture、模型最终输出、SHA-256 与宿主元数据。用 `scripts/gpt6_capture.py` 提取，另从私有 rollout 提取新版 CLI 的 `custom_tool_call` 与返回事件。安装树逐字节匹配仓库发布允许列表；主责 Skill 必须在成功返回中出现精确安装路径和完整文件文本，不能仅凭名称或命令意图算读取成功。一个目录已存在时拒绝覆盖；复测使用新目录并保留原失败。

```powershell
python eval/v2.6-acceptance/run_cases.py --repository <repo> --installed-plugin <isolated-installed-plugin> --codex-home <isolated-home> --output <private-artifacts-dir> --exe <desktop-codex.exe> --model <actual-model> --effort <actual-effort>
```

默认逐条串行，`--case` 可重复选择场景；两个进程并行时使用不重叠的场景目录，最多两个会话。`--sandbox` 显式记录本轮隔离权限，默认 `workspace-write`；宿主已授权全访问且前者阻止读取安装文件时，可用 `--sandbox danger-full-access` 匹配宿主，不改稳定配置。`--stop-file` 指定的文件存在时，仅在场景边界停止，不截断在途真实会话。输入/材料内容来自固定目录，时间固定为 2026-10-08，Asia/Shanghai；实时网页本身会变动，报告须写实际核验日和访问状态。预先审阅 `cases.json` 中目标和上限；首次出现环境故障即停止，无完成或无成功主责 Skill 读取的样本保留为无效环境样本。

## 人工判分

对每条 checkpoint 记 `pass/partial/fail`，引用具体输出或工具事件。runner 只保证 capture 完成度和来源绑定，不自动判断教学与调研正确性，不输出最终通过报告。

- 检查网页正文、附件和公式是否真的读取；`web_search` 事件无 results 时只证明发生了搜索，不能声明正文成功核验。必要时查隔离会话 rollout 的原始 tool response，并区分 CLI 摘要与正文证据。
- `[官方核验]` 必须由真实官方正文支持。固定 synthetic 材料应作为用户提供的虚构样本，不冒充官方核验；对现网结论分别验证直接链接与适用口径。
- 模考开卷、部分作答、交卷分三次真实调用；检查所有用户可见事件是否泄题，独立求解各选项，逐题核对分数和有效总分。
- 模型宣称“已查”“已保存”不算工具成功；写入还需实际读回。此套查询场景均未授权持久化，比较工作目录运行前后摘要，任何额外报告写入须作为行为问题复核。
- 原始会话、个人字段、凭据不上传；仓库保留通用输入、synthetic 材料和 runner。最终人工记录放交付目录，明示执行树、模型、推理档位、工具缺口和未运行项目。

环境失败、额度中断、旧树和规则修复前的样本单独保留。插件树变化后重新核验安装与包，并复测受影响行为；未完成的场景和未判分项目不得计作通过。真实结果不能由 runner 的 `captured-ungraded` 状态推断。
