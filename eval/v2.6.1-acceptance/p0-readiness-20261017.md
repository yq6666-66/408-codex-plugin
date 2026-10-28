# v2.6.1 P0 发布准备核对

2026-10-18 用户明确选择“先保留候选，继续完成行为验收”。因此本记录保留固定发布对象与准备结果，不执行标签或 Release；后续开发和验收继续。

核对日期：2026-10-17（Asia/Shanghai）。状态：固定候选的发布准备完成，等待用户确认打标签/发布，尚未发布或宣布冻结。下表的本地 HEAD 和 345 项检查是首次准备时的快照；后续新增维护工具和文档的交付另行记录，不改变此处锁定的发布提交。

## 发布对象

- 仓库：`yq6666-66/408-codex-plugin`。
- 远端 `main`：`c1d632a2059ff1bce26eb5643fa5c95d12b92edc`，本轮以 `git ls-remote` 及 GitHub API 独立核对。
- 拟发布版本/标签：`2.6.1` / `v2.6.1`。本轮查询时标签不存在，最新 Release 仍为 v2.6.0。
- 本地分支：`codex/408-agent-skills-design`，HEAD `b3810987876263cdf90b1917079b78c1b4f635bf`。相对发布目标只多此前设计文档提交；插件、脚本、测试、CI 和依赖文件无提交差异或工作区修改。未提交内容为规划与本次发布准备文档。
- 本地 HEAD 与发布目标的 Git 插件树对象均为 `f3cbef4ae1f9754a0499595fb6ed11cf581311d7`。发布对象锁定远端提交，不把本地文档分支作为标签目标。

## 本轮检查

| 检查 | 结果 | 证据范围 |
| --- | --- | --- |
| `python -B scripts/check.py --verify-system-evidence` | 退出 0，345 tests，360.102 秒，无跳过 | Windows / Python 3.14.0；仓库六项检查通过 |
| 官方验证器证据核对 | 当前树匹配 | 复核已生成的官方插件及 14/14 Skill 证据；本轮没有重新生成或改写证据 |
| 构建候选 ZIP | 47 文件，哈希符合预期 | 从本地 HEAD 的 Git blobs 构建；插件树与候选提交相同 |
| `install_local.py verify-release` | 通过 | 固定版本 2.6.1、指定 ZIP SHA-256 |
| 隔离解压后 `verify-tree` | 通过 | 固定版本与指定树 SHA-256 |
| 隔离插件 `health_check.py` | `status: ok` | 14/14 Skill、4/4 运行脚本，无结构问题；Obsidian 未配置 |
| `ci/release_metadata.py --expect-tag v2.6.1` | 通过 | 标签与 manifest-derived 元数据一致 |

复核 [CI run 38777023828](https://github.com/yq6666-66/408-codex-plugin/actions/runs/38777023828)，其 head 为上述发布目标：`validate`、`windows`、`reproducible` 成功，`release` 跳过。Ubuntu 日志为 345 tests、1 项 Windows 专用跳过；Semgrep 8 条规则、111 个目标、0 findings。Windows 本地不运行 Semgrep，复用同一代码提交的 Linux CI 结果。

CI 日志中的 ZIP 哈希与本地重建一致。两次下载 CI artifact 遇到连接 EOF，未完成本轮下载后独立逐字节比对；跨系统一致性依据为该提交已通过的 `reproducible` 作业，不能称本轮在本机重新完成了两套远端 ZIP 比对。

## 已准备资产

交付目录为仓库下 `dist/p0-v2.6.1-20261017-175938/`，包含 ZIP、校验和、完整本地检查日志及 CI 作业元数据。该目录被 Git 忽略，不修改已发布资产。

- `kaoyan-408-2.6.1.zip`，47 文件，304736 字节。
- ZIP SHA-256：`e70877b6dcdd1e86a6ede9ca5b552285bd8fab1f5d0631af106f8137aa2c2e8d`。
- 插件树 SHA-256：`17e514cb484449485eb846fc55d93220a9ec1a8f9d14ab62934a577b2b2dbcea`。
- [发布说明草案](release-notes-draft.md)已准备，仍标注待发布。

## 待确认动作及执行条件

待用户确认的对象是：在上述远端 `main` 提交创建 `v2.6.1` 标签，发布对应 ZIP 和校验和，随后更新发布状态并冻结 2.6.1 功能范围。

确认后先复核远端提交与标签状态；对象仍一致才使用既有 CI 发布流程。若 `main`、插件树或资产变化，核查差异及受影响证据，不能悄悄改用新提交。README/CHANGELOG 的“已发布”状态在实际发布成功后更新，本轮保持候选状态。

后续时间安排已按用户要求取消固定日期，2.7 功能在独立开发分支推进。知识点依据、Claude Code 支持和平台实测不混入本次补丁发布。

## 保留限制

10 月 17 日追加报告复核：ZCode 本地安装和 WorkBuddy 内置 CLI 安装进客户端存储有证据，两者的 47 文件安装缓存均通过指定树摘要校验。ZCode 四个普通请求未调用 Skill，显式引用插件的 planner 调用成功；tutor 驱动脚本仍待补测。WorkBuddy 四项会话行为未执行；Cursor 云端样本与本机安装尚未绑定。不能声明三个宿主完整验收通过，详见 [原生宿主报告复核](native-host-review-20261017.md)。

Claude Code 尚无支持证明。旧树行为样本继续保留旧绑定，新树模拟样本不外推为真实客户端通过。完整新旧行为配对、真实笔记写入及完整安全审计未完成。工程准备结果保持有效，最终发布确认仍待用户给出；建议先补 ZCode 显式 tutor 计算和 WorkBuddy 新会话计算两条关键链路。
