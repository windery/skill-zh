#!/usr/bin/env python3
"""SessionStart / PostToolUse hook entry point for the skill-zh plugin.

Claude Code runs this script asynchronously (see hooks.json). It always exits
0: a failure here must never surface as a hook error in the user's session,
so problems go to the log instead.
"""

import os
import sys

# Make the skill_zh package importable from the plugin root.
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
