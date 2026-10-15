# v2.6.1 多宿主适配集成记录

记录日期：2026-10-15。集成 PR [#30 Cursor](https://github.com/yq6666-66/408-codex-plugin/pull/30)、[#31 ZCode](https://github.com/yq6666-66/408-codex-plugin/pull/31)、[#32 WorkBuddy](https://github.com/yq6666-66/408-codex-plugin/pull/32)，包含 PR #31 携带的既有 v2.6.1 检查点修复。版本仍为开发候选 `2.6.1`，当前稳定版为 `2.6.0`；本次集成不创建发布标签或 Release。

## 集成与修复

- Cursor 根目录 `.cursor-plugin/` 使用仓库根作为 source，直接引用既有 14 Skill 目录；ZCode 的 `.claude-plugin/marketplace.json` 与 WorkBuddy 的 `.codebuddy-plugin/marketplace.json` 指向同一插件目录。三份宿主适配版本均同步为 2.6.1。
- 发布允许列表保留 Codex 清单，同时加入 `.zcode-plugin/plugin.json` 与 `.codebuddy-plugin/plugin.json`，共 47 个文件；没有复制或修改 Skill 正文、共享契约及随包运行脚本。
- 合并保留三种宿主各自的清单与 marketplace 校验，解决 README、QUALITY_GATES、release_payload 和 validate_repository 的重叠修改。
- Cursor 门禁原先会放过 commands/agents 等非 Skill 组件，现已拒绝，新增 5 项合法与变异测试；先复现错误放行，再修复通过。
- WorkBuddy 诊断原先可能忽略失效的 source/skills 并错误通过，现沿声明路径解析，畸形或缺失配置、无效路径、越界符号链接、空 Skill 树均报告 blocker。新增 13 项测试，包含不执行随包代码及 JSON/文本门禁输出；先复现失败，再修复通过。

## 工程与安装证据

`python scripts/check.py --verify-system-evidence` 在 Windows / Python 3.14 上通过：**340 项测试全部成功**（488.058 秒，无跳过）、仓库六项检查通过、官方验证器证据匹配。Windows 按既有规则跳过 Semgrep，由固定版本 Linux CI 承担该项。

本记录归档时 GitHub 集成检查尚待运行。`validate`、`windows`、`reproducible` 必须在集成 PR 最新 head 上通过后才合并；远端结果以该 PR 的实际检查记录为准，不把本地 Windows 结果写成 Ubuntu 或远端已通过。

官方插件验证器与 14/14 Skill 验证器已实际重跑，通过后的证据保存于 `tests/system-validator-evidence.json`，绑定插件树：

`5003420e7aa1b6ad0f02e1a0fa21aa1591f3a64c61b7e6b665d5ca2ec76080d3`

校验器固定来源与依赖哈希沿用 [来源说明](validator-provenance.md)，没有手改通过状态或树摘要。

- 当前候选：`kaoyan-408-2.6.1.zip`，47 文件。
- ZIP SHA-256：`a349f51ccd08dd14b07c014c1c02aad8f1e26b25b12fcf48623cb6ad4a47aa45`。
- Windows 构建及消费者 `verify-release` 通过。
- 官方 Codex CLI `0.162.0-alpha.17.2` 在独立、未复制登录凭据的配置目录完成本地 marketplace 添加、安装与列表查询；版本 2.6.1，installed/enabled 均为 true。实际缓存 `verify-tree` 为 47 文件、上述树哈希，通过。
- WorkBuddy 离线静态诊断：14 Skill、47 个相对链接解析成功、0 断链、0 加载错误，`--fail-on blocker` 退出 0。保留原有 high/high/medium/low/low 五项静态宿主耦合条目，这些不是实际客户端故障或行为验证。

## 行为证据与边界

与适配前归档 ZIP 逐文件比较：原有 **45 个文件全部逐字节相同**，仅新增 ZCode 与 WorkBuddy 两份原生清单；根目录 Cursor 入口不进入 Codex 插件 ZIP。旧 45 文件包及校验和已独立保留，没有覆盖旧证据。

[原候选 48 点模型验收](results.md) 与 [逐项判分索引](agent-grades.json) 仍绑定提交 `563e205`、45 文件树 `cf24e46494d0ed0ef154dcd828fa790569df90667947825d6f0948f9122019ed`。本轮没有把旧采集记录改绑 47 文件树，也没有重新宣称在三个新宿主运行过这些模型场景。内容未变化的比较证据仅说明继承了同一份教学与记录实现。

Cursor、ZCode、WorkBuddy 客户端的实际导入、Skill 发现、工具调用及三种教学模式端到端验收仍待完成。离线诊断不启动 WorkBuddy、不执行随包脚本、不模拟裁剪安装。安装要求完整插件目录；逐 Skill 扁平复制不受支持。Obsidian 配置仍使用既有 Codex 命名空间。完整新旧 20 类配对与真实用户 Obsidian/Notion 写入仍未验证。
