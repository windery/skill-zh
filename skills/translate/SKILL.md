---
description: 立刻把待翻译的英文 skill 简介翻成中文，不等下次会话
disable-model-invocation: true
allowed-tools: Bash(python3 *skill_zh* translate)
---

用 Bash 工具运行下面的命令，超时设为 600000 毫秒（翻译几十个 skill 需要一两分钟）：

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skill_zh" translate
```

用中文把输出原样展示给用户，不要翻译或改写。如果输出说后台已经在翻译，告诉用户稍后运行 `/skill-zh:status` 查看结果。新的简介从下一个会话开始显示，告诉用户这一点。
