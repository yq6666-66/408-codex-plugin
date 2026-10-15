# v2.6.1 校验器来源

本机当前系统 Skills 缺少 `plugin-creator`。本轮从 OpenAI 官方 `openai/codex` 固定历史提交取得下列原始文件，在仓库外临时目录核对 SHA-256 后使用，没有改写系统 Skills。该版本是官方历史样例，不宣称为当前最新版，也不是旧证据中 `4e84c911…` 脚本的同版本复验。

固定提交：`985cf47a4eb6084b2ff6b30ebdb1216acda85bb4`。

| 文件 | 官方来源 | SHA-256 |
| --- | --- | --- |
| 插件验证器 | [validate_plugin.py](https://github.com/openai/codex/blob/985cf47a4eb6084b2ff6b30ebdb1216acda85bb4/codex-rs/skills/src/assets/samples/plugin-creator/scripts/validate_plugin.py) | `f4eeadb733b28b0c3e714de263a76d6542866a672f3e99bdffcf4dbcdf85e944` |
| 标识符验证依赖 | [identifier_validation.py](https://github.com/openai/codex/blob/985cf47a4eb6084b2ff6b30ebdb1216acda85bb4/codex-rs/skills/src/assets/samples/plugin-creator/scripts/identifier_validation.py) | `a6d51ce4a9a7e8f85626ff5808a467a67574e7f8cdf1167ffb467c5f67e57223` |
| 同版本规范 | [plugin-json-spec.md](https://github.com/openai/codex/blob/985cf47a4eb6084b2ff6b30ebdb1216acda85bb4/codex-rs/skills/src/assets/samples/plugin-creator/references/plugin-json-spec.md) | `eeb640130f69636affaa299d4170d5a7ae6a0ff978296ddf75c409ce6dd87b91` |
| Skill 验证器 | 本机系统 Skill 的 `skill-creator/scripts/quick_validate.py` 原样副本 | `6068513d924ed3559e186dfcdead7439129828dcf402167fd925c06dffbf2806` |

插件验证器只读 JSON、Skill 和 agent YAML；依赖 Python 标准库、PyYAML 及同目录标识符模块。临时运行环境使用 `PYTHONUTF8=1`、`PYTHONDONTWRITEBYTECODE=1`。

通过仓库已有命令生成证据：

```text
python scripts/run_system_validators.py --system-root <临时校验器根目录> --write tests/system-validator-evidence.json
python scripts/run_system_validators.py --verify-evidence tests/system-validator-evidence.json
```

正式证据中的插件版本与安装树哈希仍须匹配当前候选。任何运行时文件改变后须重新生成，不能把此来源说明或旧版通过记录当作当前树校验结果。
