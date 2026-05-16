"""
FastClaw - AI Agent Framework

支持三种运行方式：
1. 直接运行: cd fastclaw && python main.py
2. 模块运行: python -m fastclaw
3. pip 安装后: fastclaw start
"""

__version__ = "1.1.3"

import os
import sys
from pathlib import Path

# ===== 路径处理 =====

_PKG_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _PKG_DIR.parent

# 设置默认 FASTCLAW_WORKSPACE 环境变量
# 优先级：已设置的环境变量 > 项目根目录的 workspace/ > ~/.fastclaw/workspace
_default_workspace = _PROJECT_ROOT / "workspace"
if os.environ.get("FASTCLAW_WORKSPACE") is None:
    if _default_workspace.exists() and _default_workspace.is_dir():
        os.environ["FASTCLAW_WORKSPACE"] = str(_default_workspace)
    else:
        os.environ["FASTCLAW_WORKSPACE"] = str(Path.home() / ".fastclaw" / "workspace")

# 确保项目根目录在 sys.path（用于直接运行模式）
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
