# 便携学习记录契约 1.2（兼容读取 1.0 / 1.1）

便携记录用于把当前会话结果复制到下一次会话。未启用 Obsidian 大脑时由用户自行保管并在需要时重新粘贴；启用后可按大脑契约在用户自己的 Vault 中结构化保存，但仍保持可复制、可审计和可迁移。机器校验规则见 [portable-learning-records.schema.json](portable-learning-records.schema.json)，统一命令行工具为仓库内 `scripts/records.py`（仅用 Python 标准库）。

## 通用规则

- 新输出必须使用 `schemaVersion: "1.2"`，并包含正确的 `recordType`；读取端继续兼容 1.0、1.1 与 1.2。已有三类记录（`StudyProfile` / `ProgressSnapshot` / `ReviewQueue`）继续保留，1.2 新增轻量 `SessionCheckpoint`。
- 输出严格 JSON；日期使用 `YYYY-MM-DD`。未知值统一使用 `null`，不得使用空字符串、“未提供”或猜测值。
- 相对日期（今天、明天、后天、本周、下周、三天后等）优先使用宿主提供的可靠当前日期与时区解析；展示或保存关键日期时必须同时写出绝对日期，例如 `三天后（2026-09-14）`。不得把当前日期强行写入日期未知的旧历史记录。到期计算必须允许显式传入基准日期（`records.py due --date`），使结果可重复。
- `unit` 未知时使用兼容值 `"unspecified"`。正确率 `rate` 使用 `0` 到 `1`；`total` 为 `0` 时 `rate` 必须为 `null`。
- `correct` 与 `total` 同时存在时必须满足 `correct <= total`；`total` 为 `0` 时 `correct` 只能为 `0` 或 `null`。三者均有值时，`rate` 必须与 `correct / total` 一致；冲突值只报告并请求确认，不伪造修正。
- 不加入姓名、账号、凭据、设备路径、原始题面全文或与学习交接无关的信息。
- 解析旧对象时保留所有安全的未识别字段及其所在层级，不静默删除；迁移前说明发现的缺失、冲突或不兼容值。若未知字段含凭据、个人标识、设备路径或原始材料全文，隐私边界优先：把原字段值改为 `null`，在根级 `redactedFields` 记录其 JSON Pointer 路径，并明确说明已脱敏。
- 旧扩展字段与规范字段同名且值冲突时，以有效的新字段承载规范值，把安全的旧值移入根级 `legacyExtensions`，以原 JSON Pointer 为键，并在 `migrationWarnings` 说明；无法安全确定规范值时先请求确认，不声称已经完成迁移。

机器校验时，Schema 根入口接受 1.1 与 1.2 输出；读取旧记录时使用同一文件的 `#/$defs/legacyInput` 定义（1.0 与 1.1），规范化后再用根入口验证 1.2 结果。

## Schema 1.2 新增字段

### 稳定记录 ID（`recordId`）

- 1.2 记录应携带 `recordId`，格式 `kr-` 加 16 位小写十六进制。
- ID 一经分配就保持稳定：后续更新复用同一 ID，不随内容变化重算。
- 旧记录不要求提前迁移；只有真正需要保存升级结果时才补 ID，之后持续复用。补 ID 的确定性规则见 `records.py normalize`：对“尚无 `recordId` 的原始记录内容”做规范 JSON 哈希，因此同一条记录重复 normalize 得到相同 ID；已有 ID 的记录保持原 ID。
- `ReviewQueue.items` 可选携带同格式的 `itemId`，用于跨次更新稳定定位单个错题。

### 更新时间（`updatedAt`）

- 1.2 记录可携带 `updatedAt`（`YYYY-MM-DD`）。只在宿主提供可靠当前日期、且记录内容确有更新时写入；未知时保持 `null`，不得用当前日期回填旧记录。

### 结构化复测证据（`retestEvidence`）

`ReviewQueue.items[].retestEvidence` 是结构化复测证据数组，每项含：

| 字段 | 取值 |
| --- | --- |
| `evidenceType` | `independent`（完全独立作答）/ `hint-assisted`（使用提示后完成）/ `solution-seen`（已经看过解析）/ `redo-after-solution`（看解析后立即重做）/ `transfer`（迁移题表现） |
| `outcome` | `correct` / `incorrect` / `partial` / `null` |
| `date` | `YYYY-MM-DD` 或 `null` |
| `note` | 简要说明或 `null` |

掌握判断规则：

- “看懂解析”（`solution-seen`）不得单独作为掌握证据；“刚看完解析后立即重做正确”（`redo-after-solution`）也不得单独证明稳定掌握。
- 掌握判断优先参考真实、独立、且具有时间间隔或迁移性质的作答证据：延迟后的 `independent` 与 `transfer`。
- 兼容旧记录：`masteryEvidence` 字符串数组继续保留；不得为旧记录凭空生成它不存在的独立作答证据。
- `retestOffsetDays` 的锚定日期可写 `retestAnchorDate`（该偏移被创建时的日历基准），便于日后用显式基准日期计算到期；没有锚定时保持 `null`。

### 轻量学习检查点（`SessionCheckpoint`）

```json
{
  "schemaVersion": "1.2",
  "recordType": "SessionCheckpoint",
  "checkpointId": "kc-0f1e2d3c4b5a6978",
  "updatedAt": "2026-09-11",
  "currentTask": "2014-2018 英语二阅读精读",
  "position": "2016 Text 2 第 3 题讲解完成，第 4 题未开始",
  "dueItems": ["kr-1234567890abcdef#1"],
  "pendingRetests": ["kr-1234567890abcdef#2"],
  "notes": null
}
```

- “继续上次复习”必须读取真实持久化的 `SessionCheckpoint` 与到期错题后恢复：上次未完成任务、当前学习位置、到期错题、必要的后续复测。
- 读取不到真实记录时明确说明，不得根据模糊聊天历史凭空推断恢复状态。

## StudyProfile 1.2

规划师每次输出一个 `StudyProfile`。未知字段写 `null`，`constraints` 没有已知限制时使用空数组。

```json
{
  "schemaVersion": "1.2",
  "recordType": "StudyProfile",
  "recordId": "kr-0f1e2d3c4b5a6978",
  "updatedAt": "2026-09-11",
  "targetExam": "408考研",
  "targetDate": "2026-12-26",
  "weeklyHours": 35,
  "currentPhase": "foundation",
  "constraints": ["周三晚不可学习"]
}
```

## ProgressSnapshot 1.2

执行器每次输出可回填对象：已计划的数据写入 `planned`，尚未完成的 `completed`、正确率和实际结果写 `null`。诊断师每次输出规范化对象，只整理用户实际提供的数据。

```json
{
  "schemaVersion": "1.2",
  "recordType": "ProgressSnapshot",
  "updatedAt": "2026-09-11",
  "period": {
    "start": "2026-09-07",
    "end": "2026-09-13"
  },
  "metrics": [
    {
      "subject": "408",
      "name": "练习题",
      "unit": "questions",
      "planned": 10,
      "completed": 8
    }
  ],
  "accuracy": [
    {
      "subject": "408",
      "correct": 17,
      "total": 25,
      "rate": 0.68
    }
  ],
  "blockers": ["进程同步题耗时过长"]
}
```

不得把不同单位合并为一个数字；分钟、小时、章节和题数分别建立 `metrics` 项。

## ReviewQueue 1.2

错题闭环每次输出一个 `ReviewQueue`；模考在用户明确交卷并完成复盘后每次输出一个。没有待复测项时允许 `items: []`，但不得把当场答对直接标为 `mastered`。

```json
{
  "schemaVersion": "1.2",
  "recordType": "ReviewQueue",
  "recordId": "kr-1234567890abcdef",
  "updatedAt": null,
  "generatedAt": "2026-09-11",
  "items": [
    {
      "subject": "408",
      "topic": "操作系统/进程同步/信号量",
      "errorCause": "把资源数量和等待进程数量混为一谈",
      "errorCauseStatus": "confirmed",
      "nextRetestDate": null,
      "retestOffsetDays": 3,
      "retestAnchorDate": "2026-09-11",
      "itemId": "kr-1234567890abcdf0",
      "status": "pending",
      "masteryEvidence": [],
      "retestEvidence": []
    }
  ]
}
```

- `errorCauseStatus` 使用 `confirmed`、`hypothesis` 或 `null`。
- `status` 使用 `pending`、`due`、`retesting`、`mastered` 或 `null`。
- 有日历基准（用户提供或宿主可靠当前日期）时写 `nextRetestDate` 绝对日期，并同时展示对应绝对日期；没有基准时写 `retestOffsetDays`，`nextRetestDate` 为 `null`，二者不得同时给出。
- 掌握证据必须是延迟后独立作答与迁移表现等可观察事实；立即重做、自评、看过解析或单次碰巧答对都不足。

## 旧记录兼容迁移（1.0 / 1.1 → 1.2）

读取 1.0 或 1.1 后先规范化，再按 1.2 输出（`records.py normalize` 已实现同等规则）：

1. 根据对象字段补充 `recordType`，把 `schemaVersion` 更新为 `"1.2"`；已有 1.1 字段原样保留。
2. 缺 `recordId` 时按规范 JSON 哈希确定性补 ID；已有 `recordId`/`itemId` 保持不变。缺 `updatedAt` 时写 `null`，不用当前日期回填。
3. 根级 `plannedUnits/completedUnits` 转为一条 `metrics`：`subject: null`、`name: "overall"`。若旧扩展字段或等价记录明确给出单位则原样保留；只有单位未知时才写 `unit: "unspecified"`。
4. `bySubject` 中每个科目的 `plannedUnits/completedUnits` 分别转为 `metrics`，`name: "workload"`；优先保留该项实际提供的单位，只有未知时才写 `unit: "unspecified"`，不同已知单位不得合并。
5. 只有 `accuracy` 与 `sampleSize` 时，转为 `rate` 与 `total`，并把 `correct` 设为 `null`；不得由四舍五入的正确率反推出正确题数。
6. 旧 `retestDate: "D+N"` 转为 `nextRetestDate: null` 与 `retestOffsetDays: N`；合法绝对日期转入 `nextRetestDate`。
7. 旧版空字符串、`"未提供"`、`"unknown"` 等未知标量哨兵统一转为 `null`；`constraints`、`blockers`、`masteryEvidence` 等集合字段的未知哨兵转为空数组。未识别字段和字段冲突按通用规则处理，不静默覆盖或丢失。
8. 根据特征字段推断 1.0 对象类型；多个类型同时匹配时先说明歧义并请求最小确认，不擅自丢弃扩展字段。
9. 迁移不伪造证据：旧记录没有结构化复测证据就保持 `retestEvidence: []`，不生成独立作答记录，不把仅有“看过解析”历史的条目升级为 `mastered`。

纯讲题、翻译、写作批改或材料摘要不生成无意义的空记录；需要跨题复测时转交错题闭环。
