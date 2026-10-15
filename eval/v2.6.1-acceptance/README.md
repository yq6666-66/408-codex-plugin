# v2.6.1 检查点定向验收

两类固定虚构场景、8 个检查点，专门验证更新命令、同日顺序、重复更新、教学状态和相同修订号冲突。场景实际调用隔离安装的脚本；fixture 没有题面或答案，模型不得补造。所有操作限于读取与内存计算。

复用现有真实 capture runner，通过 `--suite eval/v2.6.1-acceptance` 选择本套件，其他隔离、模型、安装树绑定及逐项判分要求仍遵循 [runner 文档](../v2.6-acceptance/README.md)。不要向受测模型提供 cases.json 中的判分条目。

```text
python eval/v2.6-acceptance/run_cases.py --repository <候选仓库> --suite eval/v2.6.1-acceptance --installed-plugin <隔离安装目录> --codex-home <隔离配置目录> --output <仓库外原始证据目录> --exe <实际Codex程序> --model <固定模型> --effort high
```

该套件不代替既有 40 点调研/教学场景，也不证明向用户的 Obsidian/Notion 实际写入成功。
