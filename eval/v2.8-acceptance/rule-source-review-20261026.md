# 八张规则卡的外部来源核对

核验日期：2026-10-26。此次实际打开作者原始材料或学校课程正文，给八张项目规则卡增加部分外部支持。规则卡仍为项目原创归纳，模拟器约定、年度大纲归属与题目答案分别判断。

| 卡片 | 已读取来源与定位 | 仅支持的范围 |
| --- | --- | --- |
| 二分闭区间 | [Sedgewick/Wayne 作者仓库的 BinarySearch.indexOf](https://raw.githubusercontent.com/kevin-wayne/algs4/master/src/main/java/edu/princeton/cs/algs4/BinarySearch.java) | 有序数组闭区间比较、缩小边界并返回一个匹配位置；不支持首个/末个位置变体 |
| Cache 直接映射 | [Cornell CS 3410 — Caches](https://www.cs.cornell.edu/courses/cs3410/2024fa/notes/caches.html)，Direct-Mapped Cache、Larger Blocks | 唯一行定位与标记/索引/偏移划分 |
| 全相联 LRU | 同页 Fully Associative Cache、Replacement Policies | 无索引字段及按最近访问历史淘汰 |
| FIFO、LRU 页面置换 | [OSTEP 作者第 22 章](https://pages.cs.wisc.edu/~remzi/OSTEP/vm-beyondphys-policy.pdf)，§22.3/§22.5、Figure 22.2/22.5 | 进入顺序与最近访问顺序的区别 |
| FCFS、RR 调度 | [OSTEP 作者第 7 章](https://pages.cs.wisc.edu/~remzi/OSTEP/cpu-sched.pdf)，§7.1–7.3/§7.7 | 先来先服务、周转时间定义及时间片轮转核心机制 |
| 网络时延 | [Kurose/Ross 作者交互材料](https://gaia.cs.umass.edu/kurose_ross/interactive/end-end-delay.php)，Computing end-end delay / Solution | 传输与传播时延公式及其不同物理含义 |

出处字段、支持范围和未覆盖事项保存在 [机器记录](rule-source-review-20261026.json)及规则卡的 `externalReferences`。此处只链接并归纳必要规则，没有复制来源代码或教材正文。二分链接位于作者仓库的可变 master 分支，定位与核验日期共同限定本次阅读对象。

## 保持的证据边界

- 八张卡均标 `project-reviewed-external-partial`，没有“整卡全部已核”状态。每个来源都必须带 `supports` 和 `limitations`。
- 同到达按名字排序、RR 片末到达者先入队、非空初态的槽位放置、忽略 I/O/切换成本等仍是题目或项目约定。FCFS 等待时间关系是限定模型下的推导，不称来源逐字公式。
- 60 个知识点索引完全未改；17 条 2025 年学校材料映射已核、43 条待核，2027 年度全部待核。外部规则出处不能成为当年大纲证明。
- Princeton 教材站部分页面返回 403，另有一份课程页仅返回加载外壳，均没有用于正文核验；实际采用作者原始仓库中可读的二分实现。
- 结构门禁只检查出处字段和内部一致性，不联网重验来源，也不代替真实模型、原生客户端、学习记录写入或完整安全审计。

## 接口与工程验证

规则卡 Schema 1.0 保持兼容：旧 pending 卡可不带 `externalReferences`，也可带空数组；partial 卡必须有至少一个完整已核引用。引用禁止未定义字段，不能夹带 `basisYear`、`syllabusPath` 等大纲映射字段。`source.kind`、项目来源标题与定位规则继续严格约束。

新增回归先在旧实现出现两项预期失败（partial 来源与旧 pending 空数组兼容），随后扩展 Schema 与门禁；测试覆盖缺字段、错误日期、空定位/支持/限制、错误状态、年度字段混入和旧卡兼容。

本次实际运行 `python -B tools/validate_knowledge.py` 通过；`python -B -m unittest discover -s tests -p test_v300_knowledge.py -q` 为 19 项、0 失败。独立检查确认知识点索引与本分支基线逐字节一致。这些结果是本地结构与内部一致性验证，不包含原生客户端、自动路由或模型行为验收。
