# 安装与恢复

完整插件包含 17 个技能，必须保留整个插件目录及其共享引用。各宿主的插件入口和权限不同；以下说明不代表当前版本已在每个客户端完成新会话行为验收。版本和实际客户端证据见[平台支持表](platform-support.md)。

## 固定版本

已发布的预发布版为 [v2.8.0-dev.3](https://github.com/yq6666-66/408-codex-plugin/releases/tag/v2.8.0-dev.3)，既有稳定版为 [v2.6.0](https://github.com/yq6666-66/408-codex-plugin/releases/tag/v2.6.0)。安装前选择所需版本；仓库默认分支可能继续变化。

正式版发布后可在同一命令中将 `v2.8.0-dev.3` 替换为 `v2.8.0`；是否已发布以 [Release 页面](https://github.com/yq6666-66/408-codex-plugin/releases/tag/v2.8.0)为准。正式版候选 ZIP 的 SHA-256 为 `bb0dd4439a621d5842e10b23f289cd1f0e7ca33d9c6df328a9891dc1c3b9a407`，发布后应与附件及校验文件核对。

在支持插件命令的 Codex CLI 运行：

```powershell
codex plugin marketplace add yq6666-66/408-codex-plugin --ref v2.8.0-dev.3
codex plugin add kaoyan-408@kaoyan-408
```

已存在同名市场时先检查它的来源及当前宿主的命令提示，避免覆盖其他来源。要准备固定本地仓库，在终端执行：

```powershell
git clone --branch v2.8.0-dev.3 --depth 1 https://github.com/yq6666-66/408-codex-plugin.git
```

## 其他宿主

- **Claude Code**：仓库根包含市场清单，插件目录 `plugins/kaoyan-408` 包含原生清单。可在已克隆仓库的根目录，用 `claude --plugin-dir "<此仓库的 plugins/kaoyan-408 绝对路径>"` 启动会话级插件；将占位符替换为实际绝对路径。历史版本曾在隔离配置中安装；当前版本的会话发现和对话尚未验收。
- **Cursor**：使用 Customize 的仓库导入入口，历史报告使用 `github.com/yq6666-66/408-codex-plugin`；该报告未绑定本机版本。固定版本需先检出对应标签并按客户端支持的本地入口安装。
- **ZCode**：历史实测入口为设置 → Plugin Management → Discover → `+` → Local directory，选择固定检出的仓库根目录。旧版普通请求未触发技能，显式选择插件曾调用 planner；当前版本需自行确认。
- **WorkBuddy**：仓库根与插件内均有原生清单。历史 CLI 安装使用 WorkBuddy 配置目录，新会话技能注册和使用未验证；按客户端提供的市场入口安装并检查来源、版本与启用状态。

安装后重新加载并新建对话；若宿主没有自动选择技能，使用它提供的插件选择入口。不要把旧版安装结果或基础模型答对题目当成当前插件行为验收。

## 校验与回退

在检出 `v2.8.0-dev.3` 的仓库根目录，使用实际下载的 ZIP 路径：

```powershell
python scripts/install_local.py verify-release --zip <下载的ZIP路径> --version 2.8.0-dev.3 --sha256 b4af664a1660f1c0c4e4aa11cfe327a685cc171ea7a068d0a780493b056cae04
```

回退前备份学习记录，通过宿主正常入口移除当前插件与其市场，再使用所需稳定版标签重新安装。记录格式兼容范围以目标版本的契约为准；不要假设旧版能完整处理新版字段。Obsidian 和 Notion 的授权与写入规则见[便携记录契约](../plugins/kaoyan-408/references/portable-learning-records.md)和各自的 brain 契约。
