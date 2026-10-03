---
description: 查看每个 skill 简介的汉化状态：已汉化、待翻译、本来就是中文
disable-model-invocation: true
allowed-tools: Bash(python3 *skill_zh* status)
---

下面是 skill-zh 的状态输出。原样展示给用户，不要改写；如果有「待翻译」的，提醒可以运行 `/skill-zh:translate` 立刻翻译。

!`python3 "${CLAUDE_PLUGIN_ROOT}/skill_zh" status`
