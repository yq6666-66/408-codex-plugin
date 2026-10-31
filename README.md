# kaoyan-408

面向考研学习的中文插件，支持数学一／二、英语一／二、408 和政治。从制定计划、逐题讲解到错题复测、进度诊断与招生信息核验，提供 17 个分工明确的技能。

你可以直接提问：“我考数学二和 408，帮我安排这周的学习。”也可以发一道题、你的作答过程或一份有权使用的讲义。基础学习不需要配置笔记库；需要跨会话保存时，再按需启用学习记录。

## 选择版本

当前版本：`2.9.0-dev.1`。这是**预发布版**：新增 60 张 408 公共知识卡和 2027 年第三方大纲对照，适合希望提前体验新内容的使用者。真实模型自动路由、真实笔记写入及新客户端行为尚未完整验收。

| 版本 | 适合谁 | 下载 |
| --- | --- | --- |
| `v2.8.0` 稳定版 | 希望优先使用已发布稳定版 | [稳定版 Release](https://github.com/yq6666-66/408-codex-plugin/releases/tag/v2.8.0) |
| `v2.9.0-dev.1` 预发布版 | 希望体验公共知识卡与新版依据 | [预发布 Release](https://github.com/yq6666-66/408-codex-plugin/releases/tag/v2.9.0-dev.1) |

默认安装选 `v2.8.0`。两个版本均包含 17 个技能；60 张公共知识卡属于 `v2.9.0-dev.1`，不应当作稳定版已包含的功能。

## 安装与第一次使用

### Codex CLI

在支持插件命令的 Codex CLI 中，安装固定的稳定版：

```powershell
codex plugin marketplace add yq6666-66/408-codex-plugin --ref v2.8.0
codex plugin add kaoyan-408@kaoyan-408
```

要试用预发布版，将第一条命令中的版本改为 `--ref v2.9.0-dev.1`。如果已存在同名市场或插件，先检查其来源、版本和宿主提供的更新方式；切换前备份已有学习记录。

也可准备固定版本的仓库，再按宿主支持的本地安装入口选择该仓库：

```powershell
git clone --branch v2.8.0 --depth 1 https://github.com/yq6666-66/408-codex-plugin.git
```

预发布版使用 `--branch v2.9.0-dev.1`。完整插件需要整个插件目录与共享引用，不要只复制单个 `SKILL.md`。

### 下载与校验

从对应 Release 页面下载 ZIP 和 `.sha256` 文件。预发布包的 SHA-256 为 `de2809735d525615936c3e4c6a9fb79661a9c058484bc1c23352f00a02d094af`；稳定版 `v2.8.0` 为 `bb0dd4439a621d5842e10b23f289cd1f0e7ca33d9c6df328a9891dc1c3b9a407`。

例如，在已检出 `v2.9.0-dev.1` 的仓库根目录，用实际下载路径替换下面的文件路径，再执行：

```powershell
$zipPath = "C:\Downloads\kaoyan-408-2.9.0-dev.1.zip"
python scripts/install_local.py verify-release --zip $zipPath --version 2.9.0-dev.1 --sha256 de2809735d525615936c3e4c6a9fb79661a9c058484bc1c23352f00a02d094af
```

### 开始一段学习

安装后重新加载客户端并新建对话，可以从以下请求开始：

1. “我考数学二、英语二、408 和政治，每周有 15 小时，帮我制定一周计划。”
2. “这是我的 FIFO 解题过程，帮我找第一处错误，先不要给完整答案。”
3. “只提示第四步，不要告诉我淘汰页。”
4. “把我提供的学习材料整理成问答卡，先不要保存。”

是否自动选择正确技能取决于宿主；如果没有调用，可使用客户端提供的插件或技能选择入口。其他宿主的安装路径见[安装与恢复指南](docs/installation.md)，请以客户端实际提供的功能为准。

## 能做什么

### 规划、执行与复习

| 技能 | 适合的任务 |
| --- | --- |
| `kaoyan-408-planner` | 制定阶段、月度和周计划，分配跨科学习时间。 |
| `kaoyan-review-executor` | 把已有计划展开为本次学习时段，或根据检查点续学。 |
| `kaoyan-progress-diagnostician` | 根据实际记录诊断进度偏差，给出调整信号。 |
| `kaoyan-error-loop-coach` | 聚类多题错因、安排到期复测并判断掌握证据。 |
| `kaoyan-mock-exam-coach` | 组织模考；交卷前保留答案，交卷后讲评。 |

### 讲题与学科辅导

| 技能 | 适合的任务 |
| --- | --- |
| `kaoyan-408-tutor` | 从头讲解 408 概念和题目，按需使用随包计算工具。 |
| `408-error-diagnosis` | 根据实际作答定位 408 单题的第一处错误。 |
| `408-concept-followup` | 解释 408 局部概念、条件、反例或连续疑点。 |
| `408-calculation-check` | 复核 408 的数值、单位和状态变化。 |
| `kaoyan-math-coach` | 辅导数学一／二，讲解题目并复核计算。 |
| `kaoyan-english-coach` | 辅导英语一／二阅读、翻译、完形和写作。 |
| `kaoyan-politics-coach` | 辅导政治理论辨析、材料题和背诵复测。 |

完整讲题通常由 tutor 主责；三个 408 专用入口分别聚焦单题首错、局部追问和计算复核。用户明确指定技能时尊重指定；连续追问和复合请求由宿主根据当前主要目的处理。没有实际作答过程时，应将易错点与用户已犯错误区分开。

### 真题、资料与招生

| 技能 | 适合的任务 |
| --- | --- |
| `kaoyan-past-paper-searcher` | 发现真题来源，核验出处和可访问性。 |
| `kaoyan-past-paper-analyst` | 基于实际读到的材料分析覆盖、难度和有限趋势。 |
| `kaoyan-material-study-assistant` | 将用户有权使用的材料整理成摘要、卡片或原创练习。 |
| `kaoyan-official-info-researcher` | 核验报名、考试安排和单项官方事实。 |
| `kaoyan-admissions-researcher` | 调研院校招生信息、历年情况和公开评价。 |

搜索结果摘要不等于已读到题面；招生公告、网友评价与分析判断分别标注。不能访问来源或关键事实缺失时，结果保持待核。

## 408 知识点依据

`v2.9.0-dev.1` 提供四科各 15 张原创公共知识卡，包含概念、适用条件、易混点、例题和自测。它们围绕项目已有 60 个知识点组织，**不代表覆盖全部 408 考点**。

年度对照使用[第三方整理的 2027 年大纲正文](https://www.csgraduates.com/study_methods/outline/2027/)：9 条为直接主题对应，51 条为上位或部分主题对应。年度归属、具体规则的外部来源和项目推导分别记录；第三方正文不是官方原始大纲，主题对应也不证明解题公式或答案正确。未获得支持的细节保持待核。

完整讲评按匹配的知识点给出依据；仅提示、独立作答或模考未交卷时，精确依据可能泄题，留到允许讲评后再给。无法匹配时标为未收录或待核。

[知识点依据契约](plugins/kaoyan-408/references/knowledge-point-basis-contract.md) · [2027 年对照复核](eval/v2.9-acceptance/review-2027-mapping-independent.md) · [知识卡内容复核](eval/v2.9-acceptance/final-60-review-binding.md) · [内容许可与来源](THIRD_PARTY_CONTENT.md)

## 平台、权限与验证范围

| 宿主 | 支持入口与已知边界 |
| --- | --- |
| Codex | 提供原生清单；旧树上的安装与定向样本不证明当前版本自动路由通过。 |
| Claude Code | 提供原生清单；旧版隔离安装通过，当前新会话行为未验收。 |
| Cursor | 提供仓库导入入口；历史报告未核实本机版本和完整技能列表。 |
| ZCode | 提供原生清单；旧版普通提问未触发技能，显式选择 planner 曾调用成功；当前版本未复测。 |
| WorkBuddy | 提供原生清单；旧版 CLI 安装已验证，新会话使用未验证。 |

插件的搜索、脚本和文件操作取决于宿主实际能力。学习记录为可选功能：只有在用户授权范围内写入，并且写入、读回和校验成功后，才报告已保存。记录 Schema 1.2 保持 1.0／1.1 读取兼容；回退版本前应备份记录，旧版对新字段的处理以旧版契约为准。

工程测试、安装成功与真实教学行为是不同证据。预发布候选的双系统构建、检查与未测项见[交付记录](eval/v2.9-acceptance/candidate-delivery.md)，历史客户端证据见[平台支持表](docs/platform-support.md)。

## 更多资料

[安装与恢复指南](docs/installation.md) · [便携学习记录与检查点](plugins/kaoyan-408/references/portable-learning-records.md) · [Obsidian 配置](plugins/kaoyan-408/references/obsidian-brain-contract.md) · [Notion 契约](plugins/kaoyan-408/references/notion-brain-contract.md)

[独立三技能导出](docs/v3-release.md) · [技能维护边界](docs/skill-maintenance-boundaries.md) · [变更记录](CHANGELOG.md) · [历史 README](docs/readme-history-20261028.md)

项目没有后台题库或账号服务。[隐私](PRIVACY.md) · [使用条款](TERMS.md) · [安全](SECURITY.md) · [内容版权](THIRD_PARTY_CONTENT.md)
