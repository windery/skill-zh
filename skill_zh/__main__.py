"""Entry point for ``python3 -m skill_zh`` and ``python3 path/to/skill_zh``.

The second form is what the plugin's skills and hook use: it needs no
PYTHONPATH prefix, which Bash permission rules would otherwise have to match.
"""

import os
import sys

if not __package__:
    # Run as a directory: put the plugin root, not the package itself, on the path.
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skill_zh.cli import main  # noqa: E402

sys.exit(main())
