# 宿主维护优化本地交付

日期：2026-10-17。本轮交付 README 安装/触发说明、原生验收复核与补测步骤、只读 ZCode 调用核对工具和对应测试，并固定后续分阶段计划。未发布，插件运行文件未变更。

## 最终检查

执行 `python -B scripts/check.py --verify-system-evidence`，Windows / Python 3.14.0：**359 项测试全部通过，374.038 秒，无跳过，退出 0**。仓库六项检查通过；官方验证器的已有证据与当前插件树匹配，本轮没有重生成或伪造证据。

完整日志位于仓库的 `dist/host-maintenance-20261017-204014/check.log`，日志哈希、源码哈希及机器可读结果见 [验证元数据](maintenance-validation-20261017.json)。Windows 按项目规则跳过 Semgrep；新维护提交的 Linux/Windows GitHub CI 尚未运行，不沿用旧提交 CI 冒称新提交已通过。

## 调用核对工具

`scripts/audit_host_trace.py` 仅分析已导出的 ZCode role/part JSONL，统计插件 Skill 调用及状态，绑定输入 SHA-256。它不会执行日志里的命令，不输出对话正文和工具输出，不判断讲解正确性。

14 项测试覆盖普通回答、内联 Python、失败与未知状态、用户引用、其他插件同名技能、重复状态、部分完成快照、调用身份冲突、非法格式及输入不被修改。审查发现的两项问题已先用失败用例复现再修复：完成快照省略 input 时保留已知技能，同 callID 改换技能时明确报冲突。

重新分析原五份真实轨迹后，[归档统计](native-host-audit-20261017.json)与修复前完全一致：四个普通请求没有记录 Skill 调用，对照会话有一次显式 planner 调用。这个结果不证明 tutor 自动触发已修复，也没有增加客户端执行轮次。

## 包与发布状态

插件树 SHA-256 仍为 `17e514cb484449485eb846fc55d93220a9ec1a8f9d14ab62934a577b2b2dbcea`，候选 ZIP SHA-256 仍为 `e70877b6dcdd1e86a6ede9ca5b552285bd8fab1f5d0631af106f8137aa2c2e8d`。新增维护工具在仓库 scripts 中，不属于 47 文件插件包。

原固定发布候选为 `c1d632a2059ff1bce26eb5643fa5c95d12b92edc`。本轮本地维护提交与该对象分开，若要改用新提交发布，必须明确新的发布对象并完成相应远端检查。按用户要求，打标签和 Release 保留最终确认步骤。

## 下一步

先依 [补测步骤](native-host-followup.md)取得 ZCode 显式 tutor 计算与 WorkBuddy 新会话计算，再补 Cursor 本机版本/来源和调用记录。可访问的约定证据目录本轮未发现新增补测材料。

2.7 自 2026-10-25 起优先补知识点大纲依据，2.8 做版本单源和正式平台验收，之后评估三场景的 3.0。任务、分支处理条件和验收要求见 [后续执行安排](../../docs/superpowers/plans/2026-10-17-host-fixes-and-next-steps.md)。
