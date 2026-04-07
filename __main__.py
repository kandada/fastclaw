"""
支持 python -m fastclaw 运行
"""

import sys
import asyncio
from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _PKG_DIR.parent

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fastclaw.main import main as fastclaw_main

if __name__ == "__main__":
    asyncio.run(fastclaw_main())
