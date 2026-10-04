"""`python3 -m skill_zh` 和 `python3 路径/skill_zh` 两种运行方式的入口。

插件的 skill 和钩子用的是第二种：不需要先设 PYTHONPATH，Bash 权限规则也就不用去匹配它。
"""

import os
import sys

if not __package__:
    # 以目录方式运行时，要把插件根目录（不是包目录本身）加进 sys.path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skill_zh.cli import main  # noqa: E402

sys.exit(main())
