# 离线质量门禁

本仓库的自动发布检查不调用模型，也不要求安装或登录 Codex CLI。所有门禁都可以在干净仓库、Windows 与 Ubuntu GitHub Actions 中重复执行。
因此，维护者无需准备 Codex CLI 会话、模型额度或在线评测凭据。

## 自动阻塞项

- 插件 manifest、marketplace、13 个 Skill frontmatter 与 13 个 `agents/openai.yaml` 的真实 YAML/JSON 解析。
- 完整路径发布允许列表、UTF-8/LF、符号链接、路径穿越、重复 ZIP 成员和脏插件树检查。
- 便携学习记录 Schema 1.2/1.1 输出、1.0/1.1 兼容输入、正确率数值关系、掌握证据语义（独立/迁移证据之外不构成掌握）与 SessionCheckpoint 形状验证。
- 路由场景的唯一 ID、主责 Skill、最近邻冲突、每 Skill 至少一例的全覆盖校验（不再固定场景总数，避免脆弱断言）。
- 行为场景的唯一 ID、会话输入、主责 Skill 和逐条 rubric 完整性（含教学模式、检查点恢复、到期错题、题面缺损、模考零泄露等 v2.5.0 用例）。
- 单元测试、变异测试、Linux CI 中固定版本的 Semgrep、完整 Git 历史密钥/旧系统残留扫描。Windows 本地与 Windows CI 运行其余离线门禁，避免依赖 Semgrep 在 Windows 上的系统证书实现。
- 官方插件 validator、13 个 `quick_validate.py` 结果及其与当前插件树哈希的绑定。
- Windows 与 Ubuntu 生成字节一致的 ZIP 与 SHA-256。
- 消费者固定版本验证（`verify-release`/`verify-tree`）与发布时长无关：31 天、一年后哈希正确仍通过；维护者完整门禁继续保留且两者不混用。
- 新增 `records.py`、`study_simulator.py`、安装器与 GPT-6 验收 harness 的单元测试全部通过。

## 非阻塞人工抽查

维护者可在任意支持 Skills 的 ChatGPT 或 Codex 新任务中抽查复合路由、简洁输出、学科推导、模考零泄露、Obsidian 与 Notion 降级行为。人工结果用于发现体验问题，不生成可伪装成确定性证明的“模型通过率”，也不阻塞安装或 Release。

## 发布含义

通过自动门禁表示插件文件、规则、测试资产、安全边界和发布包满足仓库声明；不表示任何特定模型对所有自然语言输入都能稳定选择同一 Skill 或产生相同答案。模型行为仍受宿主版本、可用工具、上下文和用户输入影响。

GPT-6 教学质量验收独立于本文件：使用 `eval/gpt6-acceptance/` 的固定用例在真实宿主上运行新旧两版并记录回答与判分依据；该验收截至 v2.5.0 尚未实际运行，本文件所述门禁不构成对模型教学效果的声明。

发布既可由与 manifest 版本一致的 `v*` 标签触发，也可在无法使用本地 GitHub/Codex CLI 登录时，从 GitHub Actions 的 `CI` 工作流对最新 `main` 手动输入该标签。手动入口不会绕过检查：`validate`、`windows` 和 `reproducible` 必须全部成功，且标签必须严格等于 `plugin.json.version` 派生值，之后工作流才创建标签和 Release。
