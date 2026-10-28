# 离线质量门禁

完整 `kaoyan-408` 插件是维护主线，14 个既有技能继续优化并可增加新入口。完整主线运行 `python -B scripts/check.py --verify-system-evidence`，发现全部 `test_*.py`；附加三场景的专项不能代替主插件门禁。主插件版本源与独立三场景版本源分开。

本仓库的自动发布检查不调用模型，也不要求安装或登录 Codex CLI。所有门禁都可以在干净仓库、Windows 与 Ubuntu GitHub Actions 中重复执行。
离线工程门禁无需准备 Codex CLI 会话、模型额度或在线评测凭据；v2.6.0 定向真实抽查另需实际宿主和相应工具，两类证据分别报告。


## 自动阻塞项

- Codex、ZCode、WorkBuddy 与 Claude 四份插件清单、各 marketplace、17 个 Skill frontmatter 与 17 个 `agents/openai.yaml` 的真实 YAML/JSON 解析。宿主清单须与 Codex 元数据一致；Claude 清单不含 Codex interface 或执行能力，共享 Claude/ZCode 市场仅保留两端交集字段。
- `sync_plugin_versions.py --check` 在仓库检查和测试之前运行，六处派生消费者缺失或版本漂移均失败；生成版本不改写官方证据、市场级版本或历史发布状态。
- Cursor 根目录导入入口：marketplace source 指向仓库根、插件版本与 Codex 一致、Skill 与 logo 路径存在，拒绝 commands、agents、MCP、hooks 等非 Skill 组件。
- WorkBuddy 适配面：插件内 `.codebuddy-plugin/plugin.json` 与仓库根 `.codebuddy-plugin/marketplace.json` 的存在性、字段与 Codex 清单的一致性、`skills` 相对路径、版本/分类/作者同步，以及该清单在发布允许列表内的精确位置。
- 完整路径发布允许列表、UTF-8/LF、符号链接、路径穿越、重复 ZIP 成员和脏插件树检查。
- 便携学习记录 Schema 1.2/1.1 输出、1.0/1.1 兼容输入、正确率数值关系、掌握证据语义（独立/迁移证据之外不构成掌握）与 SessionCheckpoint 形状验证。
- 路由场景的唯一 ID、主责 Skill、最近邻冲突、每 Skill 至少一例的全覆盖校验（不再固定场景总数，避免脆弱断言）。
- 行为场景的唯一 ID、会话输入、主责 Skill 和逐条 rubric 完整性（含既有教学模式、检查点恢复、到期错题、题面缺损、模考零泄露，以及招生口径、网友证据、调研降级、模考有效性和详细选项分析）。
- 单元测试、变异测试、Linux CI 中固定版本的 Semgrep、完整 Git 历史密钥/旧系统残留扫描。Windows 本地与 Windows CI 运行其余离线门禁，避免依赖 Semgrep 在 Windows 上的系统证书实现。
- 官方插件 validator、17 个 `quick_validate.py` 结果及其与最终插件树哈希的绑定；插件树有改动后须刷新证据，不沿用旧树结果。
- Windows 与 Ubuntu 生成字节一致的 ZIP 与 SHA-256。
- 消费者固定版本验证（`verify-release`/`verify-tree`）与发布时长无关：31 天、一年后哈希正确仍通过；维护者完整门禁继续保留且两者不混用。
- 新增 `records.py`、`study_simulator.py`、安装器与 GPT-6 验收 harness 的单元测试全部通过。
- 2.8 路由输入投影测试拒绝向模型输出评分字段、预期 Skill、知识点 ID 或准备配置；这只验证输入隔离，十组真实路由与行为仍按 [验收说明](eval/v2.8-acceptance/README.md)单独采集、判分。平台状态按 [产品和版本](docs/platform-support.md)分别记录。

## v2.6.0 定向真实抽查

固定宿主、模型、推理档位和输入，保留原始工具事件、真实回答及逐项判断，覆盖以下 10 类场景：

1. 指定 408 院校的当期完整招生调研。
2. 未指定院校时发现候选，并逐校确认考试科目。
3. 最近两个已完成招生年度的数据比较，区分校线、院线和录取分数。
4. 专业代码变化、人数口径不符及官方来源冲突。
5. 多平台网友评价，核对去重、亲历声明、推广迹象、相反意见与样本范围。
6. 登录限制、失效链接、不可读附件和仅有搜索摘要时的降级。
7. 用户指定非计算机硕士专业时的检索与路由。
8. 读取旧调研报告后重新核验；未授权保存时无写入。
9. SJF 等原创单选模考的题目有效性、冻结和计分。
10. 真题详细讲解的题面保真、独立复核及可见 A/B/C/D 逐项分析。

使用固定材料验证统计口径与降级规则，使用实时页面验证实际检索能力，分别报告结果。固定材料不能证明访问过真实网页，静态规则不能代替模型回答。关键抽查失败时须修复并重测受影响场景，未运行、工具失败、无输出或未完成判分均不得写为通过；本轮抽查是 v2.6.0 行为验收要求，当前发布版本尚未完成该验收，不沿用旧版的通过率。

一般体验抽查仍可按需用于发现复合路由、简洁输出和知识库降级问题，但不得替代上述定向验收或生成确定性的模型质量保证。

## 宿主兼容性报告（不阻塞）

`python scripts/simulate_workbuddy_host.py` 静态检查 WorkBuddy 声明的加载链（市场描述 → 插件清单 → Skill 树及 Markdown 相对引用），不启动客户端、不执行随包脚本，也不模拟裁剪安装，输出带文件与证据的宿主兼容性条目：插件根目录标记、用户配置命名空间、`agents/openai.yaml`、frontmatter 字段白名单、Skill 目录外的相对链接。该脚本只作报告，默认退出码 `0`；`--fail-on high` 可把它变成门禁。条目描述的是宿主耦合现状，不是已修复或已验收结论。

原生客户端补测按 [固定版本补测步骤](eval/v2.6.1-acceptance/native-host-followup.md) 执行。分别记录安装树完整性、会话技能发现、普通请求自动选择、显式选择、随包脚本调用及回答表现。显式选择成功不能覆盖普通请求未选择的首次结果；文件系统层的 14/14 也不能替代会话注册证据。客户端无法运行、登录失败或原始轨迹缺失时保留未测/无法确认，不计通过或插件行为失败。

ZCode 已导出的 role/part JSONL 可用 `python scripts/audit_host_trace.py --trace <parts.jsonl> --mode ordinary` 只读统计；重复 callID 合并状态并保留已知参数，工具或 Skill 身份冲突时拒绝统计，调用状态与行为评分分开。统计退出 0 仅表示解析成功，不是新的发布通过门禁；不执行日志内命令，也不对 Cursor/WorkBuddy 的未知导出格式作兼容声明。

知识点索引按 `kp-408.schema.json` 校验年度、来源、日期及未知字段，另检查 ID 唯一、四科覆盖和 ID 前缀。待核年度不能标为已核，已核项须有大纲路径、来源定位和日期；结构检查不证明来源真实性或解题正确性。代表题与边界输入存放在 `eval/v2.7-acceptance/`，只有实际模型采集并评分后才能报告行为验收结果。

## 发布含义

v2.6.0 基于 v2.5.2 提交 `e31922383dfb3b24f33f77f04ffef1b0c28f97b6` 开发，PR #26 已合并至 `main`，合并提交为 `2d37c1a3e08ee8c1db1888d9c4f33833e1357a8a`。PR #27 合并了发布记录；正式标签 [`v2.6.0`](https://github.com/yq6666-66/408-codex-plugin/releases/tag/v2.6.0) 与 GitHub Release 已由 main 上的 `CI` workflow 发布，当前稳定版本为 v2.6.0，v2.5.1 保留作回退版本。发布前远端 `validate`、`windows`、`reproducible`、GitGuardian 均通过；官方插件 validator 与 14/14 Skill validators 通过，正式 ZIP SHA-256 为 `02c1494e47833b103f2060df207c0244e9c744ed0cef04878300ee9616b3eac5`。实时行为验收尚有检查点因 CLI 额度中断或未运行，最终树 0/40 个 checkpoint 已判分，完整新旧 20 类配对验收未运行，详见 [v2.6.0 验收记录](eval/v2.6-acceptance/results-v2.6.0-candidate.md)。Release 只代表工程与资产门禁通过，不表示未完成的模型行为验收通过。

2026-10-08，维护者将 v2.5.2 本次交付范围调整为简化验收与候选分支推送准备。插件提交 `2171696` 的本地工程门禁通过；完整行为验收尚未确认全通过，GitHub required checks 尚待推送后运行。此次准备不代表正式 Release 验收通过，当前稳定回退版本仍为 v2.5.1。具体证据和已知问题见 [v2.5.2 候选验收说明](eval/gpt6-acceptance/results-v2.5.2-candidate.md)。

通过自动门禁表示插件文件、规则、测试资产、安全边界和发布包满足仓库声明；不表示任何特定模型对所有自然语言输入都能稳定选择同一 Skill 或产生相同答案。模型行为仍受宿主版本、可用工具、上下文和用户输入影响。

候选打包须从已提交的干净插件树重复构建，核验 ZIP 字节一致、SHA-256 与隔离安装树，不修改稳定安装。Windows 本地验证不冒充 Ubuntu 或远端 CI；远端 CI 未运行时明确标注，插件树变动后使相应 validator、包和行为证据重新绑定最终版本。

GPT-6 教学质量验收独立于本文件：使用 `eval/gpt6-acceptance/` 的固定用例在真实宿主上运行新旧两版并记录回答与判分依据；v2.5.1 已完成 17 条真实新旧版本对照，候选版 17/17 用例、60/60 checkpoint 通过且逐 checkpoint 无回退。完整公开统计见 [`eval/gpt6-acceptance/results-v2.5.1.md`](eval/gpt6-acceptance/results-v2.5.1.md)。本文件所述静态门禁仍不替代逐条人工判分，也不把一次固定宿主实测外推为所有模型输入的确定性保证。

发布既可由与 manifest 版本一致的 `v*` 标签触发，也可在无法使用本地 GitHub/Codex CLI 登录时，从 GitHub Actions 的 `CI` 工作流对最新 `main` 手动输入该标签。手动入口不会绕过检查：`validate`、`windows` 和 `reproducible` 必须全部成功，且标签必须严格等于 `plugin.json.version` 派生值，之后工作流才创建标签和 Release。

## 可选新增三场景的附加门禁

`skillset.json` 仅为独立三场景分发的版本/依赖声明；旧 2.x 插件清单和验证证据继续绑定旧树，不改数字冒充 3.x 证据。

- 开发检查先按 `requirements-dev.txt` 安装固定依赖，再运行 `python -B tools/validate_knowledge.py`。它直接验证 `src/shared/references` 的知识点和规则卡，使用根 `schemas` 中的独立结构契约；不导入旧插件或 `scripts/validate_repository.py`。来源、年份、待核状态、日期、唯一 ID 和内部引用均需一致。规则卡保持项目整理身份；已读取来源只支持列出的部分规则，其余项目约定仍需按卡片边界说明。
- 知识依据校验离线执行，拒绝重复 JSON 键、非有限数值和无法本地解析的 schema 引用。通过只证明结构与内部引用一致，不新增来源实读或当年大纲核验声明。安装/导出工具仍只需 Python 标准库，此依赖用于开发门禁。
- 运行 `python -B -m unittest discover -s tests -p "test_v300_*.py" -v` 检查内容、计算、装配、安装恢复与三包可重复比较。
- `tools/skills.py export --platform all` 只装配三个新入口，公共内容跨平台相同，所有资源在各自 Skill 内，携带 MIT 许可。
- 独立 Skills CI 在 Windows/Ubuntu 构建三个 ZIP，再由 `ci/verify_skills_reproducible.py` 比较完整包名集合及原始字节；流程没有发布步骤。
- `tools/check_security.py` 独立扫描当前 `src`、版本清单与许可证，并扫描全部本地 refs 和 HEAD 可达的 Git 历史，包括已删除 blob、提交/tag 消息及旁支。浅克隆拒绝完整检查，禁用替换对象、graft 覆盖和延迟联网获取；失败只给规则标识及摘要，不回显匹配秘密或 Git 原始错误。旧有秘密类型和历史路径检查保留，旧移除标记豁免仍精确限定到原两个定义文件。
- Linux Semgrep 保留固定版本与阻塞模式；移除标记规则同时覆盖旧插件和新 `src`。完整历史抓取在 Skills CI 的两个系统矩阵中启用，不能把浅克隆扫描写成完整历史通过。
- `legacy/*.zip` 冻结快照只接受固定排序、时间、regular 0644 元数据的规范 ZIP_STORED 格式，限制 16 MiB/1024 成员，拒绝重复或越界名称、压缩/加密、嵌套 ZIP 和额外前后缀。扫描器不落盘解包，逐成员检查秘密、私有路径和移除标记；原两个定义文件的精确路径例外只作用于移除标记，秘密仍检查。归档文件本身不会整体跳过扫描。
- 三包准备与复验使用 `python -I -B ci/skills_release.py`，从指定提交的核对字节重建，并要求 Windows/Ubuntu 下载产物各自匹配；同篡改的双包也会失败。手动 `skills-release.yml` 默认只上传候选，发布另需显式选择、当前受保护 main 及已存在的匹配标签。详细命令与权限见 [三包发布说明](docs/v3-release.md)。
- 实际模型记录绑定新装配树，定向读取与原生发现分开评分。用户明确跳过的客户端材料/CLI 读文件标 `skipped-by-user`，不能写作通过；未运行的自然路由保持未运行。
- 不删除、归档旧 14 入口，不覆盖未知或用户修改内容，不迁移真实笔记。正式标签与 Release 仍需确认。

完整插件的门禁和发布产物仍单独保留，不相互改绑证据。
