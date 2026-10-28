# 17 技能路由扩展验收输入

状态：数据、输入投影与静态验证已在开发分支准备；未运行模型、未评分。原 2.8 十组自然输入和历史评分文件保持原字节。

## 输入与评分内容

- `forward-additions.json`：12 条，三个新入口各有 positive、colloquial、conflict、compound。真实 `check_forward_cases` 不接受 negative/nearest_neighbor 作为 kind；负向和最近邻以 conflict 及自然 A/B 表达。
- `behavior-additions.json`：9 条，含三个新入口的关键边界及两条真实逐轮请求定义；评分 rubric 为非空字符串列表，多轮另有评分侧 `reviewOnly.perTurn`。
- `natural-cases.json`：8 组 A/B、16 case、20 轮自然输入，覆盖首错/聚类、概念/完整题、复核/首错、续问/换任务、未交卷/交卷、非408、保存授权和笔记权限。
- `baseline-route-overrides.json`：原十组输入的 17 技能评分覆盖，绑定原文件 SHA-256；`baseline-derived-cases.json` 是可直接导出的派生视图，仅改 6 个轮次的预期主责，自然输入、材料和其他评分约束保留。
- `export_inputs.py`：复用原 `eval/v2.8-acceptance/export_inputs.py` 的 `export_case`，只增加三个新 Skill ID 的拒绝检查。输出仍只有 `messages`、`materials`，不投影 case ID、overrides、reviewOnly 或 runnerOnlySetup。
- `test_full17_inputs.py`：8 项输入投影、泄漏、标识、原始输入及跨平台 UTF-8 输出检查。
- `docs/fourteen-skill-audit-20261027.md`：14 入口逐项静态审查，不宣称观察到了模型违规。

自然集、派生评分、投影器和材料位于本目录，测试位于 `tests/test_full17_inputs.py`。新增 cases 已追加到两份工程目录，原有数组和 ID 保留；实际技能集合与通过状态以最终集成树和验证记录为准。

## 历史输入的评分覆盖

原 `cases.json` 的 G01-A 改由单题错因入口评分；G06-A 概念入口，G06-B 计算入口；G10-A 两轮和 G10-B 首轮为概念入口。G10 后续数学与搜索分工保持。G07-A 是完整用户题面讲解，G08 是提示/完整讲评模式，仍由原 tutor 处理。

派生评分视图只用于新 17 树；不能把旧树结果改绑新树，也不能发送整个派生文件给模型。旧十组仍是 20 case、23 轮，自然扩展另为 16 case、20 轮；如全跑，共 36 case、43 轮。多轮必须插入真实前一轮回复，不能预填 assistant 或一次拼接全部 turns。

## 隔离与使用

```text
python -B export_inputs.py N17-01-A
python -B export_inputs.py G01-A --catalog baseline-derived-cases.json
```

模型侧仅接收导出的 messages 与正常材料文件；正常 Skill 发现不能被预期入口强制读取替代。`materials/notes-vault` 是原虚构材料的副本，允许给模型读取；配置、服务准备和评分说明保持模型不可读。

所有 notes case 各自使用新的 Vault 和虚构 Notion session。新目录内不复制真实配置、凭据或用户笔记。服务准备复用原虚构 Notion fixture，工具必须真实可写才能观察零写尝试；工具不可用或隔离不成立时标 `invalid-environment`。N17-07 需要网络/来源核验，只有实际取得合格来源才触发授权索引写入；核不到不能为了完成测试伪造写入。

原准备、校验脚本及备份留在本地准备目录，不属于模型材料或本目录交付物。

原输入在旧工作区的 CRLF 原字节 SHA-256 为 `b5cdf370153bbee15fd6b1b0a0725b5b60305cc6e00ce3ce1e7317f826b59f48`；Git 中 LF 字节 SHA-256 为 `3387dfdb2fbcec62e1382eeecfa703f16a93cd26c4218f3d563903301e71d156`。两者逐字节仅换行差异；派生评分必须分别核对两个确切哈希及双向换行转换，不修改原文件，也不把任意归一化内容当成原证据。
