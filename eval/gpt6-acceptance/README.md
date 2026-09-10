# GPT-6 实际回答验收 harness

**状态：尚未实际运行。** 本目录只提供可重复的测试材料、记录格式与校验工具；截至本版本发布，没有任何一份“实际 GPT-6 回答记录”在此环境中产生。工程测试（`unittest`）通过不等于 GPT-6 教学效果已验收。

## 目的

把“工程质量”和“GPT-6 实际回答质量”分开验收：

- 工程测试：`python scripts/check.py`、unittest —— 验证代码、契约与脚本。
- GPT-6 验收：本目录的用例在真实宿主上运行并记录回答 —— 验证教学行为。

## 测试材料

- [`cases.json`](cases.json)：17 个用例，覆盖四科详细回答、简洁覆盖、五题分批、图片缺损、关键符号模糊、模考交卷前不泄题、连续搜题→核验→讲解、政治真题检索、未来年份试卷、院校数据口径、继续上次复习、到期错题、工具不可用降级、计算工具与人工复核区别。

## 运行步骤（新旧版本对比）

1. **同一宿主、同一模型、同一推理档位**：新旧两版必须条件一致。
2. 旧版：在宿主中安装 v2.4.0（`codex plugin marketplace add yq6666-66/408-codex-plugin --ref v2.4.0`）。
3. 新版：同法安装 v2.5.0。
4. 每版逐条运行 `cases.json` 的用例；图片类用例使用 `materials/` 中的固定材料（或按 input 描述自备并记入 `inputMaterial`）。
5. 每条用例把模型真实回答、实际工具调用与逐条 checkpoint 判分记入一份 record JSON（模板见 [`record-template.json`](record-template.json)）。**必须粘贴模型真实输出，禁止编造或模拟回答。**
6. 校验并出报告：
   ```powershell
   python scripts/gpt6_acceptance.py --record record-v2.4.0.json
   python scripts/gpt6_acceptance.py --record record-v2.5.0.json
   python scripts/gpt6_acceptance.py --compare record-v2.4.0.json record-v2.5.0.json
   ```

## 判分规则

- 每条用例的 `checkpoints` 是判分依据；`verdict` 必须引用回答原文或工具输出作为 evidence。
- **不得只因回答中出现指定关键词就判 pass**；checkpoint 要求的是行为与正确性。
- 对比验收标准：正确性不得回退、关键教学能力不得回退、新流程必须真正完成。
- harness 会拒绝占位符或明显编造的记录（空白、`TODO`、`模拟回答` 等）。

## 记录要求

每份 record 必须保存：插件版本、模型版本、推理档位、宿主、输入材料、模型实际回答、工具调用结果、每条 checkpoint 的判分依据。
