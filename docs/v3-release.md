# 可选三场景包的发布准备与复验

2026-10-24 范围更正：本文仅对应保留的三个独立新增场景及其 `skillset.json`，不代表完整插件收缩为三技能。完整 14 技能主插件继续走 `scripts/build_release.py` 和原 CI/发布链；未经重新批准不移除旧入口。

新产品版本只读取 `skillset.json`。使用 `skills-v<version>` 标签命名空间，例如 `skills-v3.0.0-dev.3`，避免触发现存旧插件的 `v*` 发布流程。开发版本在发布元数据中保留 `prerelease: true`。准备工具不会创建标签、推送或调用 GitHub 发布接口。

## 本地准备

先在目标提交完成安全、知识依据、专项测试及跨平台构建。Windows/Ubuntu 的导出目录均须包含本版本 Claude、Codex、Cursor 三份 ZIP；不能用同版本号或双方同样的文件名代替内容比较。

```text
python -I -B ci/skills_release.py prepare --windows <Windows产物目录> --ubuntu <Ubuntu产物目录> --output <不存在的新目录> --tag skills-v<skillset版本> --commit <完整40位提交SHA>
python -I -B ci/skills_release.py verify --directory <刚生成的目录> --tag skills-v<skillset版本> --commit <同一提交SHA>
```

该入口要求 Python 隔离模式。先核对源码和构建实现的字节与指定提交一致，再从核对过的 Git 文件字节创建临时快照并构建，按确切文件加载实现；不执行仓库中的包初始化文件或复用不受信任的字节码缓存。当前 `src` 文件集合发生变化也会拒绝。两端下载的三包必须各自与快照重新生成的三包字节相同，否则准备失败。

新输出目录含六个文件：三份平台 ZIP、`release.json`、`SHA256SUMS.txt`、`RELEASE_NOTES.md`。JSON 记录版本、标签、完整源码提交、预发布状态及三包哈希；校验和覆盖三包、JSON 和说明。复验重新生成整组六文件并逐字节比较，拒绝缺失、多余、篡改和链接路径。已有输出目录及输入目录中的文件不会覆盖。

此过程验证产物与源码的绑定，不执行模型、查询大纲或替代真实客户端验收。安装/导出工具的标准库要求不变；开发门禁按 `requirements-dev.txt` 安装依赖。

## 工作流

`skills-ci.yml` 可以独立运行或被复用，默认只有读权限。它获取完整历史，运行新源码/历史扫描、知识依据校验、专项测试和 Linux Semgrep，在两系统构建，并比对三包字节。

`skills-release.yml` 只支持手动触发：

1. 默认 `publish=false`。复用完整 Skills CI，然后从同一次运行下载两系统产物，以当前工作流提交重新构建和准备六文件候选；仅上传 Actions artifact 供审阅。
2. 发布必须明确选择 `publish=true`，且运行分支为 `main`。发布 job 再次检出同一提交、下载候选并逐字节复验；要求该提交仍为远端当前 `main`、GitHub 报告 `main` 已受保护，且已有标签指向同一提交。
3. 只有最终发布 job 有 `contents: write`。调用 `gh release create --verify-tag`，不会自动生成或替换标签，不覆盖既有 Release。开发版本使用预发布标记，且不自动替代仓库 latest。

工作流定义或本地准备成功不等于远端运行或发布完成。实际创建标签、触发发布，以及其他破坏性操作仍遵守用户已有的明确批准要求。没有远端运行证据时，记录为本地检查和工作流静态验证；客户端未验收状态随发布说明保留。

依据：GitHub 官方 [工作流复用](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows)和 [gh release create](https://cli.github.com/manual/gh_release_create)。
