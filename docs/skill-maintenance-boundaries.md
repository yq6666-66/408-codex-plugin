# 408 与 study-copilot 的维护边界

这份说明处理同名技能的发现歧义，不表示已经合并或删除另一仓库的技能，也不推断代码来源方向。

比较基线：本仓库 `c1d632a2059ff1bce26eb5643fa5c95d12b92edc`，`yq6666-66/study-copilot-skills` 的 `f57066401216dd1b89507672da4460d3f0256772`。固定提交的 Skill 名称及 SKILL.md 字节比较结果：13 个同名，1 个正文相同、12 个正文不同。正文不同不等于语义没有重复，也不能仅凭同名判断可以直接覆盖。

| 同名 Skill | 基线正文比较 |
| --- | --- |
| kaoyan-408-planner | 不同 |
| kaoyan-408-tutor | 不同 |
| kaoyan-english-coach | 不同 |
| kaoyan-error-loop-coach | 不同 |
| kaoyan-material-study-assistant | 不同 |
| kaoyan-math-coach | 不同 |
| kaoyan-mock-exam-coach | 不同 |
| kaoyan-official-info-researcher | 不同 |
| kaoyan-past-paper-searcher | 不同 |
| kaoyan-politics-coach | 不同 |
| kaoyan-progress-diagnostician | 不同 |
| kaoyan-review-executor | 不同 |
| kaoyan-past-paper-analyst | 相同 |

408 基线独有 admissions-researcher；study-copilot 基线独有 qwen-drill 和 subject-onboarding。这是指定提交的快照，不保证另一仓库后续状态相同。

2.7 在本仓库维护 408 知识点索引、tutor 和错题闭环的 408 依据输出；其余 2.x 入口仍保留。建议同一任务只选择一个来源明确的插件，保留完整的插件/技能命名空间，避免同时启用同名入口后无法判断实际来源。先用隔离新会话做对照，不自动卸载用户已安装插件或修改全局设置。

本仓库继续保留并优化通用计划、执行和其他学科技能，按实际需要增加新技能；同名与正文分叉比较仅用于澄清维护边界和安装来源，不作为删除依据。另一仓库的内容和 README 本轮没有修改；未来变更须对照功能、契约、引用、记录兼容性及用户迁移方式，不能只按名字删掉一份。
