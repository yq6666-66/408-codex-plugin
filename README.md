# kaoyan-408

面向考研的中文学习插件，覆盖数学一/二、英语一/二、408 和政治，支持规划、讲题、真题与招生检索、错题复测及学习记录。完整插件保留原有 14 个技能，并增加 3 个 408 专用入口，共 17 个技能。

当前版本：`2.9.0-dev.1`（开发候选）。默认安装仍使用已发布的稳定版 `v2.8.0`；候选标签及附件的状态请查看 [v2.9.0-dev.1 Release 页面](https://github.com/yq6666-66/408-codex-plugin/releases/tag/v2.9.0-dev.1)。真实模型自动路由、真实笔记写入及新客户端行为尚未完整验收。

固定版本可使用 `--ref v2.8.0` 或 `--branch v2.8.0`。需要试用开发候选时，可使用已创建的 `--ref v2.9.0-dev.1` 或 `--branch v2.9.0-dev.1`；候选不替代稳定版。

已发布 v2.8.0 ZIP 为 60 个文件，SHA-256 `bb0dd4439a621d5842e10b23f289cd1f0e7ca33d9c6df328a9891dc1c3b9a407`；请与 Release 的校验文件核对。

## 快速安装

确认正式 Release 已发布后，在支持插件命令的 Codex CLI 中执行：

```powershell
codex plugin marketplace add yq6666-66/408-codex-plugin --ref v2.8.0
codex plugin add kaoyan-408@kaoyan-408
```

正式标签发布后，也可在终端中克隆固定标签，然后用宿主的本地插件安装入口选择仓库：

```powershell
git clone --branch v2.8.0 --depth 1 https://github.com/yq6666-66/408-codex-plugin.git
```

正式发布后从 [Release 页面](https://github.com/yq6666-66/408-codex-plugin/releases/tag/v2.8.0)下载 ZIP 和校验文件。在上述克隆仓库的根目录运行，ZIP 路径按实际下载位置填写：

```powershell
python scripts/install_local.py verify-release --zip <下载的ZIP路径> --version 2.8.0 --sha256 bb0dd4439a621d5842e10b23f289cd1f0e7ca33d9c6df328a9891dc1c3b9a407
```

安装后新建对话，试着说：“我考数学二和 408，帮我安排本周计划。”也可以要求“先给一条提示，不要泄露答案”。宿主是否自动选择技能需实际确认；若未调用，可使用客户端的插件选择入口。

## 功能和技能

规划与执行支持目标分解、学习时段、进度诊断、检查点和到期复测；学科教练支持逐题讲解、提示和独立作答。真题与招生检索区分官方事实、网友评价与待核信息；模考在交卷前保留答案。

| Skill | 主责 | 示例触发 | 负向边界 |
| --- | --- | --- | --- |
| `kaoyan-408-planner` | 阶段、月度、周度、目标日期倒排与跨科配额 | “今年考研怎么分配四科时间” | 不展开单次时段，不伪造真题频率 |
| `kaoyan-review-executor` | 展开当前时段；按检查点恢复上次复习 | “今晚 90 分钟刷数学”“继续上次复习” | 不决定长期路线，不凭聊天历史编造检查点 |
| `kaoyan-progress-diagnostician` | 根据记录诊断偏差、风险与调整信号 | “按我粘贴的进度看要不要加时间” | 不凭空生成进度 |
| `kaoyan-error-loop-coach` | 跨题错因聚类、复测与掌握证据 | “这套卷错题都是同一类” | 不替代单题第一处错误定位 |
| `kaoyan-mock-exam-coach` | 冻结题面模考；交卷前零泄露 | “来套卷，交卷前别给答案” | 交卷前不讲题或泄露线索 |
| `kaoyan-408-tutor` | 408 四科概念与单题；可调状态模拟器 | “讲这道 Cache 题” | 不做整卷趋势或搜索整套资料 |
| `408-error-diagnosis` | 依据实际作答定位 408 单题首错 | “检查我这一步哪里错” | 不替代跨题错因闭环 |
| `408-concept-followup` | 解释 408 局部概念、条件与反例 | “为什么命中不改变 FIFO 顺序” | 完整讲题仍由 tutor 主责 |
| `408-calculation-check` | 复核 408 数值、单位与状态过程 | “核对这个 Cache 地址计算” | 未运行脚本不称脚本核验 |
| `kaoyan-math-coach` | 数学一/二讲解、第一处错误与训练 | “帮我验算这个极限” | 先明确卷种，不做跨题闭环 |
| `kaoyan-english-coach` | 英语一/二阅读、翻译、完形与写作批改 | “批改这篇英语二作文” | 区分卷种与评分口径 |
| `kaoyan-politics-coach` | 政治理论、材料题、批改与背诵复测 | “这段材料对应什么原理”“现在先考我背诵” | 时政按试卷实际年度核验，不凭记忆断言当前时政 |
| `kaoyan-past-paper-searcher` | 六科真题来源发现、核验、许可与登记 | “帮我找 2024 数学二真题” | 不直接完成逐题教学 |
| `kaoyan-past-paper-analyst` | 已核验真题的覆盖、难度与有限趋势 | “这三年 408 哪些考点变多” | 不搜索来源，不把小样本写成规律 |
| `kaoyan-material-study-assistant` | 用户材料的摘要、卡片、提纲与原创练习 | “把我贴的讲义做成卡片” | 不索取未授权材料，不替代单题讲解 |
| `kaoyan-official-info-researcher` | 报名、考试安排、政策与单项官方事实核验 | “今年报名哪天开始”“核验某校是否考 408” | 不主责完整择校调研；无宿主调度能力不承诺自动提醒 |
| `kaoyan-admissions-researcher` | 院校筛选、招生详情、历年比较、网友评价与择校参考 | “哪些学校考 408”“查某校招生、近两年录取与网上评价” | 评价不替代官方事实；不推断个人录取概率或自动保存报告 |

三个 408 专用入口分别处理单题首错、局部概念和计算复核；从头完整讲题仍由 tutor 主责，多题错因聚类与复测由错题闭环主责。明确指定技能时尊重指定；自动选择的实际效果取决于宿主。

## 知识点依据

插件提供 60 个项目知识点，四科各 15 条。当前源码候选提供 60 张原创公共知识卡，安装完整候选后可用于学习，无需先配置个人笔记库。60 个知识点均已对照 2027 年第三方大纲正文：9 条为直接主题对应，51 条为上位或部分主题对应；该对照并非官方原文认证。规则依据和年度映射分别记录，卡片不覆盖全部 408 考点，外部来源仅支持各条注明的范围。[知识点依据契约](plugins/kaoyan-408/references/knowledge-point-basis-contract.md) · [2027 正文对照复核](eval/v2.9-acceptance/review-2027-mapping-independent.md) · [知识卡内容复核](eval/v2.9-acceptance/final-60-review-binding.md) · [规则来源核对](eval/v2.8-acceptance/rule-source-review-20261026.md) · [内容许可与来源](THIRD_PARTY_CONTENT.md)。

## 平台与权限

| 宿主 | 入口与证据边界 |
| --- | --- |
| Codex | 提供原生清单；历史隔离安装和定向样本不证明当前版本自动路由通过。 |
| Claude Code | 提供原生清单；旧版本隔离安装通过，当前新会话行为未验收。 |
| Cursor | 提供仓库导入入口；旧报告的本机版本和完整技能列表未核实。 |
| ZCode | 提供原生清单；旧版普通请求未触发技能，显式选择 planner 可调用；当前版本未复测。 |
| WorkBuddy | 提供原生清单；旧版 CLI 安装已验证，新会话使用未验证。 |

[完整平台支持和历史验证范围](docs/platform-support.md)。外部搜索、脚本和文件能力由宿主决定；无法实际读取时标待核。学习记录只在授权范围内写入，写入、读回及校验成功后才称已保存；只读或不记忆时不写入。记录 Schema 1.2 保持 1.0/1.1 读取兼容，检查点可导出供跨会话恢复。

## 进一步使用与回退

[各宿主安装与恢复指南](docs/installation.md)提供固定版本、本地仓库入口和回退说明。

- [便携学习记录与检查点](plugins/kaoyan-408/references/portable-learning-records.md) · [Obsidian 配置](plugins/kaoyan-408/references/obsidian-brain-contract.md) · [Notion 契约](plugins/kaoyan-408/references/notion-brain-contract.md)
- [独立三技能导出](docs/v3-release.md) · [技能维护边界](docs/skill-maintenance-boundaries.md) · [变更记录](CHANGELOG.md)
- [2.6.1 宿主验证](eval/v2.6.1-acceptance/native-host-review-20261017.md) · [2.8 验收资料](eval/v2.8-acceptance/README.md) · [2.6.0 发布与验收](eval/v2.6-acceptance/results-v2.6.0-candidate.md) · [历史 README 归档](docs/readme-history-20261028.md)
- 需要稳定版时，先通过宿主正常入口移除当前插件，再使用 `codex plugin marketplace add yq6666-66/408-codex-plugin --ref v2.6.0` 和 `codex plugin add kaoyan-408@kaoyan-408`。旧版对较新记录的处理取决于对应版本契约；回退前先备份记录。

项目没有后台题库或账号服务。[隐私](PRIVACY.md) · [使用条款](TERMS.md) · [安全](SECURITY.md) · [内容版权](THIRD_PARTY_CONTENT.md)
