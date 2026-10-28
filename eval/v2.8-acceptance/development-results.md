# v2.8.0-dev.1 开发验证

日期：2026-10-18。测试源码提交 `6a3bb47d973aaa9c545b65e55262c9f6e9e629a8`，开发分支 `codex/v280-host-validation`。工程检查、包完整性及原生清单检查已完成；原生客户端会话与自动路由出口条件仍有缺口，未推送、合并、打标签或发布。用户已明确选择继续保留 v2.6.1 候选。

## 已实现

- 新增插件内 Claude 原生清单；Codex、Claude、ZCode、WorkBuddy 复用同一份 14 Skill 树。共享 Claude/ZCode marketplace 移除两条重复中文的 i18n 扩展，基础中文展示值保留。
- Claude 清单与 Codex 共享元数据独立校验，禁止 interface、hooks、MCP 等非 Skill 能力。发布白名单从 50 增为 51 文件。
- Codex 清单是唯一插件版本源；六处派生消费者均为必需项。只读版本检查进入 `check.py`，由现有 Windows/Linux CI 入口覆盖；版本生成不改写官方验证器证据。
- 增加 [分层平台表](../../docs/platform-support.md)、10 组 A/B 路由输入和只导出模型输入的工具。9 项数据投影测试进入现有门禁；评分、期望入口及笔记准备配置不随正常投影输出。

## 工程与产物

| 检查 | 实际结果 |
| --- | --- |
| Windows / Python 3.14.0 | 421 tests，552.796 秒，通过，无跳过 |
| 本地 WSL Ubuntu 原生临时克隆 / Python 3.12.3 | 421 tests，56.923 秒，通过，1 项 Windows 专用跳过 |
| Linux Semgrep 1.162.0 | 8 条规则、154 个目标、0 findings |
| 固定来源官方插件/Skill 验证器 | 核对四项来源摘要后实际运行通过，14/14 Skill |
| Claude Code 2.1.167 | marketplace、插件目录两条 strict 均退出 0，无 warning |
| Claude Code 2.1.167 原生隔离安装 | 正常 marketplace add / plugin install --scope user / list 成功，enabled、版本和提交正确；51 文件缓存逐字节匹配 |
| Codex CLI 0.163.0-alpha.10.2 原生安装 | 固定提交、新 home 的 marketplace add / plugin add / list 成功，installed/enabled；51 文件缓存与指定树相同 |
| Windows/Linux ZIP | 51 文件、351052 字节，逐字节和校验和一致 |
| verify-release / 隔离 verify-tree | 固定版本和指定摘要通过 |
| 隔离包健康检查 | status ok，14/14 Skill、4/4 脚本；明确使用不存在的夹具配置，不代表用户笔记配置状态 |

插件树 SHA-256：`f7d13515ad4e6246f9140206880dd21defe4d90bf8f3346730362249dcabb959`。

ZIP SHA-256：`c50f277acc41e00be3687844956c6793ca4d8d2b2c87155e609a8c515d76808a`。两套产物及完整日志在 `dist/v280-dev1-check-20261018/`；机器记录见 [development-validation.json](development-validation.json)。本地 WSL 结果不冒称 GitHub Actions。Claude 原生验证的源码、输入前后摘要、命令和日志绑定见 [native-manifest-validation.json](native-manifest-validation.json)。

Codex CLI 使用实际 `plugin add` 安装命令；先试 `plugin install --help` 的不支持错误保留为准备记录。原生安装没有请求模型、登录或复制凭据，只检查新独立 profile 与显式写入路径，未做系统级写入审计；详细绑定见 [安装证据](codex-native-install-validation.json)。

Claude 原生安装在核对本版 CLI 的配置/注册表/缓存路径实现后进行，使用全新隔离 profile 和固定本地检出，无需登录即可完成。真实 registry/list 与 consumer 校验已回读，详见 [Claude 安装证据](claude-native-install-validation.json)。它仍不证明新会话 Skill 发现或模型行为；没有改稳定用户安装或守卫设置，也未作系统级写入审计。

## 行为与客户端

在应用内子 Agent 的正常权限环境，20 条知识点定向请求和另列 1 条随包脚本请求已完成采集与主 Agent/独立 Agent 复核，详见 [定向行为记录](directed-model-results.md)。原始捕获仍保留 captured-ungraded，逐项评级另存；没有把采集器返回值自动当作通过。

这不是原生插件安装、自动发现或自动路由测试。20 条知识点输入来自 2.7 验收集，绑定本次 2.8 树，不改绑旧版本；十组路由对照依然 fixture-only。CLI workspace-write 读取失败也没有被应用内样本“修复”或替代。

Claude 登录后的注册与对话、Cursor 本机来源和版本确认、ZCode 显式 tutor 对照及共同市场 UI 复测、WorkBuddy 新会话仍需完成。第 9 组 Notion fake store 后续已补本地服务，见下文；仍未具备已验证的完整隔离宿主环境，不连接真实笔记补测。

下一步按 [原生补测提示](native-followup.md)收集相应客户端原始材料，再运行十组自然路由对照。确认实际失败后修复、重测；旧 14 入口收敛与迁移仍保留原规划的评估和确认条件。

## 2026-10-19 验收准备补齐

新增 [G09 虚构笔记服务](NOTES_FIXTURE.md)：固定种子、5 个工具、真实可用的创建/更新、失败调用审计和不覆盖旧状态的快照。服务不进入插件包，插件 51 文件树及既有产物摘要未变。

Windows 与本地 WSL Ubuntu 的 21 项受影响测试均通过（12 项新服务测试、9 项原输入测试），官方 MCP Python SDK 1.23.3 实际完成 stdio 初始化、发现、读写和失败审计互通；Linux Semgrep 1.162.0 对该验证快照检查 8 条规则、167 个文件，0 findings。源文件与日志摘要见 [工程记录](notes-fixture-validation-20261019.json)。这不是重新运行全部工程测试，也不是 G09 模型判分。

默认用户配置的 Codex CLI 只读探针在额度恢复后实际运行，普通文件绝对路径读取仍拒绝访问，见 [原始记录绑定](codex-read-probe-20261019.json)。它没有安装或绑定候选插件，不能当作插件失败，也不能根据进程退出 0 宣称读取成功。用户暂时不方便做原生新会话验收，相关项目继续保留未测。

独立代码复核发现并复现一次异常 Unicode 导致请求审计漏记的问题；修复后新增真实 stdio 回归，创建与更新的非法输入均有失败审计、状态不变且服务继续可用。上述 21 项、SDK 与扫描结果绑定修复后文件摘要，原始准备结果另保留，没有混用。
