# 408考研插件

`kaoyan-408` 是面向考研 408 方向的中文 **Skills-only** 学习插件，运行在 Codex 与 ChatGPT 中，覆盖**数学一、数学二、英语一、英语二、408 与政治**。插件提供六科真题（2010 年起，不设固定结束年份）的合规检索与分析、三种教学模式的新手图文讲解、学习规划与执行、进度诊断、错题闭环、学习检查点、原创模考、官方招考信息核验，并可按 [通用学习层契约](plugins/kaoyan-408/references/learning-layer-contract.md) 条件式连接 14 个学习层应用（Obsidian / Notion / Udemy / Sider Scholar / Exa / GoodNotes / Wolfram / A-Z Dictionary / Quizlet / Ace Quiz Maker / Ace Knowledge Graph / AhaMotion / Vocabulary Trainer / Kahoot）。

当前版本：`2.5.0`

项目没有 App、MCP、后台服务、云端题库、账号或 API Key。网页搜索、图片生成、各学习层和本地文件能力由当前 ChatGPT/Codex 宿主决定；未连接或权限不足时插件明确降级，不伪造搜索结果或学习记录。

---

## 功能总览

### 真题搜索与核验

- 检索范围：`2010` 年起**数学一、数学二、英语一、英语二、408、政治** 六类试卷，**不设固定结束年份**。未来年份请求按真实可访问来源判断试卷是否已公开，不因超过固定年份判定不存在。
- 普通网页发现与 `site:github.com` 定向检索并行；只有实际访问到结果才标记来源渠道。
- 官方来源优先；GitHub 来源记录仓库、文件、commit、许可与原始 URL。
- 每条记录至少区分**试卷年度、实际考试日期、来源、完整度、授权或许可状态**。
- 去重键为「科目 + 试卷年度 + 试卷类型 + 题号 + 内容哈希」，同时保存 `paperYear` 与 `examDate`。
- 许可证不明时只保存索引与必要短摘录；只有官方明确允许或开放许可证覆盖时才保存全文。
- 搜索关闭时输出 `[真题未命中]` 与可复制的搜索式，不伪造结果。
- **政治时政核验**：政治真题答案涉及当年时政时，按该试卷实际适用的考试年度核验当年语境，不用当前年份新闻替代。

### 讲题与练习（三种教学模式）

- **详细讲解**（默认）：数学、英语、408、政治的单题与概念讲解默认详细，覆盖前置知识、概念定理、关键中间步骤、公式来源、推导过程、选项逐项分析、独立复核与首个错误定位；只有明确说“只要答案”“简洁版”“不要过程”时才压缩，且不损害关键正确性。
- **逐级提示**：用户说“卡住了”“提示我”时，从弱到强分层提示，不立即泄露答案。
- **独立作答**：用户说“考考我”“先别给答案”“我自己做”“出一道题”“模拟一下”时，先出题等作答，再批改 → 定位错误 → 讲解 → 变式 → 必要时复测。
- 多题每批最多四题，分批只发生在题目边界；结构只在有教学价值时组织，不机械输出固定标题。
- **题面完整性检查**：图片、截图、扫描页、手写与多页题面统一核对题号、页序、缺页、裁切、正负号、指数、上下标、单位、进制、小数点、括号、关键符号与选项对应关系；只对**足以改变答案或推导路径的歧义**追问，轻微版式问题不阻断。
- **答案泄露规则**：普通练习按用户请求决定何时揭示答案；冻结模考在正式交卷前零泄露，所有外部测验工具调用继承同一规则。
- **数学核验**：可用宿主已有计算能力做代入验证、数值/符号计算与边界检查；回答中区分“工具实际运行得到的结果”与“Agent 人工复核”，不声称运行了实际没有运行的程序。

### 408 状态模拟器

`scripts/study_simulator.py`（纯 Python 标准库）支持 Cache 地址拆分、FIFO / LRU 页面置换、FCFS / RR 调度的分步状态模拟，输出完整状态序列与每步变化，并可生成本地 HTML 演示（上一步/下一步导航）：

```powershell
python scripts/study_simulator.py cache --addr-bits 16 --block-size 64 --cache-lines 256 --addresses 0,65535
python scripts/study_simulator.py fifo --frames 3 --references 1,2,3,4,1,2,5,1,2,3,4,5
python scripts/study_simulator.py rr --processes "P1:0:24,P2:0:3,P3:0:3" --quantum 4 --html demo.html
```

脚本或 Python 不可用时，各 Skill 仍能用文字方式完成同样的分步教学——脚本不是答题前提。

### 学习闭环

- **规划**：阶段、月度、周度、目标日期倒排与跨科配额。
- **执行与恢复**：把计划或本次目标展开为时间盒；“继续上次复习”读取真实持久化的 `SessionCheckpoint` 恢复未完成任务、当前学习位置、到期错题与待复测，读取不到时明确说明。
- **诊断**：根据真实记录识别进度偏差、风险与调整信号。
- **错题闭环**：跨题错因聚类、间隔复测、延迟掌握证据判断。复测证据区分**完全独立作答 / 提示后完成 / 看过解析 / 看解析后立即重做 / 迁移题**；“看懂解析”和“看后立即重做”不单独构成掌握证据。
- **模考**：冻结题面模考，交卷前零泄露，交卷后按公开 rubric 评分。
- **日期**：相对日期（今天、三天后、下周等）优先用宿主可靠当前日期解析，并同时展示绝对日期（如“三天后（2026-09-14）”）；到期计算可用 `records.py due --date` 显式传基准日期，结果可重复。

### 官方信息核验

- 当年大纲、报名、考试安排只以教育部、研招网、省级教育考试院、报考点及政府机构官网为准。
- 支持 408 院校目录发现与逐校核验；**院校比较先统一口径**（招生年度、院系、专业代码、学硕/专硕、全日制/非全日制、考生类别），复试线、拟录取初试分、综合成绩、计划数、进复试数、拟录取数、推免数、专项数、调剂数等指标不得混用，未公开数据留空或标未知。
- **提醒与公告跟踪**：宿主实际提供定时任务/监控工具时按用户请求创建，只有宿主实际返回创建成功才告知“已经设置”；公告跟踪只在有实质变化、跟踪失败或需要用户行动时通知。
- 独立检索（不同院校/年度/来源）可交子 Agent 并行；最终事实判断、冲突处理、总结与笔记写入由主 Agent 汇总，不允许多个子 Agent 同时写同一记录。

---

## 便携学习记录：Schema 1.2 与 records.py

- 新输出使用 **Schema 1.2**；读取端继续兼容 **1.0 / 1.1 / 1.2**，已有 `StudyProfile` / `ProgressSnapshot` / `ReviewQueue` 三类记录全部保留，新增轻量 `SessionCheckpoint`。
- 1.2 新增：稳定 `recordId`（一次分配持续复用）、`updatedAt`、结构化 `retestEvidence`、`SessionCheckpoint`。
- **不需要提前迁移整个旧库**：旧记录照常读取；只有真正需要保存升级结果时才补稳定 ID 并持久复用。兼容时保留安全的未知扩展字段与既有掌握状态，不凭空生成旧记录不存在的独立作答证据。
- 统一 CLI 工具 `scripts/records.py`（纯标准库，文件或 stdin 进、stdout JSON 出、退出码适合自动化）：

```powershell
python scripts/records.py validate records.json
python scripts/records.py normalize old.json          # 1.0/1.1 → 1.2，不伪造证据
python scripts/records.py merge a.json b.json         # 冲突确定性合并，不丢任何一方
python scripts/records.py due queue.json --date 2026-09-11   # 到期计算必须显式给基准日期
python scripts/records.py checkpoint create --date 2026-09-11
```

详见 [便携学习记录契约](plugins/kaoyan-408/references/portable-learning-records.md)。

---

## 使用方法

### 在哪里使用

- **ChatGPT Desktop / Codex Desktop**：新建任务后直接提问即可，13 个 Skills 自动加载；也可在桌面设置中添加 GitHub marketplace 安装（见“安装”）。
- **新版 CLI / IDE**：安装完成后同样在新会话中生效。
- 学习层取决于宿主是否提供对应工具；未连接时插件自动降级，不伪造结果。能力按需加载：所有学习层共用一份 [通用学习层契约](plugins/kaoyan-408/references/learning-layer-contract.md)（搜索、计算、词典、卡片、测验、图谱、媒体、笔记、课程、文件、定时任务），用户点名某品牌且工具实际可用时按需调用。

### 记忆控制（权限语义严格区分）

- “本次不记忆” / “只读模式” → **禁止所有学习记录写入**（Obsidian、Notion 及其他笔记层全部只读）。
- “不要同步 Notion” → **仅限制 Notion 写入**；Obsidian 等已授权本地持久化照常执行。
- “关闭大脑” → 全局禁用 Obsidian 写入（运行配置脚本 `disable`）。
- “忘记/删除某项记忆” → 先定位具体记录，默认移入归档，不直接永久删除。

### 常用问法

| 场景 | 示例问法 |
| --- | --- |
| 真题搜索 | “找 2024 数学二真题的公开来源”“2027 的 408 卷子现在有吗” |
| 政治真题 | “找 2023 政治真题来源，时政答案按哪年核验” |
| 单题详细讲解 | “详细讲这道 408 Cache 题” |
| 逐级提示 | “这题我卡住了，提示我，别给答案” |
| 独立作答 | “考考我操作系统进程同步”“出一道题我自己做” |
| 模拟器 | “用模拟器演示 FIFO 置换 1,2,3,4,1,2,5” |
| 继续复习 | “继续上次复习”“上次学到哪了” |
| 到期错题 | “按 2026-09-11 看哪些错题到期” |
| 官方核验 | “查 2026 年报名时间、XX 大学复试内容和近两年录取” |
| 院校比较 | “比较 A、B 两校 408 复试线与拟录取情况，统一口径” |
| 规划/执行/诊断 | “做 408 四科周计划”“今晚 90 分钟刷数学”“按快照诊断风险” |
| 模考 | “生成一张 408 章节测，交卷前别给答案，交卷后评分” |

---

## 13 个 Skills

| Skill | 主责 | 示例触发 | 负向边界 |
| --- | --- | --- | --- |
| `kaoyan-408-planner` | 阶段、月度、周度、目标日期倒排与跨科配额 | “今年考研怎么分配四科时间” | 不展开单次时段，不伪造真题频率 |
| `kaoyan-review-executor` | 展开当前时段；按检查点恢复上次复习 | “今晚 90 分钟刷数学”“继续上次复习” | 不决定长期路线，不凭聊天历史编造检查点 |
| `kaoyan-progress-diagnostician` | 根据记录诊断偏差、风险与调整信号 | “按我粘贴的进度看要不要加时间” | 不凭空生成进度 |
| `kaoyan-error-loop-coach` | 跨题错因聚类、复测与掌握证据 | “这套卷错题都是同一类” | 不替代单题第一处错误定位 |
| `kaoyan-mock-exam-coach` | 冻结题面模考；交卷前零泄露 | “来套卷，交卷前别给答案” | 交卷前不讲题或泄露线索 |
| `kaoyan-408-tutor` | 408 四科概念与单题；可调状态模拟器 | “讲这道 Cache 题” | 不做整卷趋势或搜索整套资料 |
| `kaoyan-math-coach` | 数学一/二讲解、第一处错误与训练 | “帮我验算这个极限” | 先明确卷种，不做跨题闭环 |
| `kaoyan-english-coach` | 英语一/二阅读、翻译、完形与写作批改 | “批改这篇英语二作文” | 区分卷种与评分口径 |
| `kaoyan-politics-coach` | 政治理论、材料题、批改与背诵复测 | “这段材料对应什么原理”“现在先考我背诵” | 时政按试卷实际年度核验，不凭记忆断言当前时政 |
| `kaoyan-past-paper-searcher` | 六科真题来源发现、核验、许可与登记 | “帮我找 2024 数学二真题” | 不直接完成逐题教学 |
| `kaoyan-past-paper-analyst` | 已核验真题的覆盖、难度与有限趋势 | “这三年 408 哪些考点变多” | 不搜索来源，不把小样本写成规律 |
| `kaoyan-material-study-assistant` | 用户材料的摘要、卡片、提纲与原创练习 | “把我贴的讲义做成卡片” | 不索取未授权材料，不替代单题讲解 |
| `kaoyan-official-info-researcher` | 当年招考、院校目录、复试录取核验与统一口径比较 | “哪些学校考 408？某校复试考什么” | 不做学科教学；无宿主调度能力不承诺自动提醒 |

同一会话内连续任务（检索来源 → 核验题面 → 讲解 → 授权范围内的笔记整理）由 Agent 自动串联，不要求用户复制、粘贴或传递“交接卡”。

---

## 安装与回退

新版 Codex CLI/IDE 可添加仓库 marketplace 后安装：

```powershell
codex plugin marketplace add yq6666-66/408-codex-plugin --ref v2.5.0
codex plugin add kaoyan-408@kaoyan-408
```

也可克隆固定版本，在 ChatGPT Desktop 或 Codex Desktop 打开仓库并从 repo marketplace 安装：

```powershell
git clone --branch v2.5.0 --depth 1 https://github.com/yq6666-66/408-codex-plugin.git
```

跨平台安装器（统一参数名 `--validate-only`）：

```powershell
python scripts/install_local.py install --validate-only   # 只做离线结构校验
python scripts/install_local.py install                   # 校验后经官方 CLI 安装
```

退出码：`0` 成功；`1` 校验、命令或安装失败；`2` 当前宿主不支持插件命令。只有实际成功才输出 `Installed kaoyan-408`。

消费者固定版本验证（与时间无关：发布 31 天、一年后哈希仍正确的版本均可安装）：

```powershell
python scripts/install_local.py verify-release --zip kaoyan-408-2.5.0.zip --sha256 <发布SHA-256> --version 2.5.0
python scripts/install_local.py verify-tree --dir <已安装插件目录> --version 2.5.0
```

安装器通过官方 CLI 的结构化 JSON 输出识别 Git marketplace / 本地 marketplace；同名但来源不同、缓存目录、文件被改、版本或哈希不一致都会被拒绝并说明原因。消费者安装验证不等于维护者完整发布门禁（官方插件/Skill 校验、Windows/Ubuntu 测试、可重复构建等仍然保留）。

**回退到 v2.4.0**：

```powershell
codex plugin remove kaoyan-408
codex plugin marketplace remove kaoyan-408
codex plugin marketplace add yq6666-66/408-codex-plugin --ref v2.4.0
codex plugin add kaoyan-408@kaoyan-408
```

学习记录无需任何迁移回退：Schema 1.2 的读取端兼容 1.0/1.1，旧版 v2.4.0 直接读取 1.1 及更早记录；1.2 记录若被旧版读取，未知字段按旧版契约保留在 `legacyExtensions` 语义下处理（历史掌握状态不丢失）。

---

## Obsidian / Notion 双笔记库

保留双笔记库行为：绑定范围、写前重读、增量合并、写后验证。明确落点：

| 内容 | Obsidian | Notion |
| --- | --- | --- |
| 政治 | `40-真题/408考研/政治/` | `06｜政治` |
| 学习档案 | `学习档案.md` | `07｜学习档案` |
| 学习进度 | `当前进度.md` | `07｜学习档案` |
| 错题队列 | `错题队列.md` | `08｜错题队列` |
| SessionCheckpoint | `学习检查点.md` | `09｜学习检查点` |

```powershell
python scripts/configure_obsidian_brain.py configure --vault <Vault绝对路径>
python scripts/configure_obsidian_brain.py check
```

Notion 首次写入需确认绑定“408考研”主页（标记 `kaoyan-408-brain:1.0`）。权限语义见上文“记忆控制”：`只读`/`本次不记忆` 禁止一切写入；`不要同步 Notion` 只限制 Notion。

---

## GPT-6 实测与工程测试的区别

工程测试（`python scripts/check.py`、unittest）只证明代码与契约正确；**GPT-6 教学质量必须用真实宿主实测验收**，材料与记录格式见 [`eval/gpt6-acceptance/`](eval/gpt6-acceptance/README.md)（同一组用例可同时跑旧版与新版，保存插件版本、模型版本、推理档位、输入、真实回答、工具调用与判分依据）。截至 v2.5.0 发布，该验收 harness **尚未实际运行**。

---

## 隐私与版权

- 发布者没有后台服务，无法访问会话、Notion、Obsidian、真题文件、学习记录或 API Key。
- 只有官方明确允许或开放许可证覆盖时才保存真题全文；其他来源只保存索引、合法短摘录和原创解析。
- 不提供付费题库、批量答案、网盘资料或未授权材料下载；用户提供的文件、链接、已连接知识库与已授权记录正常处理。
- 各学习层均为用户授权的可选连接：发布者不接收 Udemy 登录态、Sider Scholar 会话、GoodNotes 数据、Notion Token 或 Obsidian Vault 内容。

参见 [PRIVACY.md](PRIVACY.md)、[TERMS.md](TERMS.md)、[SECURITY.md](SECURITY.md) 和 [THIRD_PARTY_CONTENT.md](THIRD_PARTY_CONTENT.md)。

源码与支持：[GitHub 仓库](https://github.com/yq6666-66/408-codex-plugin) · [Issues](https://github.com/yq6666-66/408-codex-plugin/issues)
