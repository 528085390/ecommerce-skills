#!/usr/bin/env python3
"""兼容入口：等价于 agent_browser.py --url https://www.1688.com/

保留这个文件名，是因为第 5 步文档和历史命令都指向它。
新调用请直接用 agent_browser.py。
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
args = [sys.executable, os.path.join(HERE, "agent_browser.py")]
if "--url" not in sys.argv:
    args += ["--url", "https://www.1688.com/"]
sys.exit(subprocess.call(args + sys.argv[1:]))
