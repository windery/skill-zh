#!/usr/bin/env python3
"""skill-zh 插件的钩子入口，SessionStart 和 PostToolUse 都走这里。

Claude Code 以异步方式运行它（见 hooks.json）。它永远以 0 退出：
这里出了问题也不能在用户的会话里冒出钩子报错，只能写进日志。
"""

import os
import sys

# 让 skill_zh 包能从插件根目录导入。这是导入包之前的引导代码，所以不能用 config.plugin_root()。
PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, PLUGIN_ROOT)


def main() -> None:
    try:
        from skill_zh import hook

        hook.main(sys.stdin)
    except Exception as e:
        try:
            from skill_zh.state import debug_log

            debug_log(f"hook 出错：{e!r}")
        except Exception:
            pass
    finally:
        sys.exit(0)


if __name__ == "__main__":
    main()
