#!/usr/bin/env python3
"""Read-only local checks before preparing a SHOPLINE review import."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import urlsplit
from xml.etree import ElementTree
from zipfile import BadZipFile

from shopline_reviews import TEMPLATE, product_handle, template_headers, verify_upload


SKILL_DIR = Path(__file__).resolve().parent.parent


def chrome_path():
    for name in ("google-chrome", "google-chrome-stable", "chrome", "chromium"):
        found = shutil.which(name)
        if found:
            return found
    candidates = [Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")]
    for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        if root := os.environ.get(variable):
            candidates.append(Path(root) / "Google/Chrome/Application/chrome.exe")
    return str(next((path for path in candidates if path.is_file()), ""))


def main():
    parser = argparse.ArgumentParser(description="只读检查 Skill 环境、店铺配置和可选的待上传文件。")
    parser.add_argument("--store", required=True, help="后台域名，例如 peakoom.myshopline.com")
    parser.add_argument("--product-host", required=True, help="前台域名，例如 peakoom.com")
    parser.add_argument("--product", help="待处理商品的前台 HTTPS 链接")
    parser.add_argument("--file", type=Path, help="可选：待上传 XLSX，用于校验 Handle 与内容")
    parser.add_argument("--expected-count", type=int, help="可选：期望评价条数")
    args = parser.parse_args()
    checks = {}
    store = args.store.lower()
    front = args.product_host.lower()
    checks["store"] = bool(re.fullmatch(r"[a-z0-9][a-z0-9.-]*\.myshopline\.com", store))
    checks["product_host"] = bool(re.fullmatch(r"[a-z0-9][a-z0-9.-]*\.[a-z]{2,}", front)) and not front.endswith(".myshopline.com")
    checks["python"] = sys.version_info >= (3, 9)
    try:
        checks["template"] = TEMPLATE.is_file() and len(template_headers()) == 11
    except (OSError, ValueError, KeyError, BadZipFile, ElementTree.ParseError):
        checks["template"] = False
    node = shutil.which("node")
    npm = shutil.which("npm")
    checks["node"] = bool(node)
    checks["npm"] = bool(npm)
    checks["chrome"] = bool(chrome_path())
    local_playwright = SKILL_DIR / "node_modules/playwright"
    runtime = Path(os.environ.get("SHOPLINE_NODE_RUNTIME", Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node"))
    checks["playwright"] = local_playwright.is_dir() or (runtime / "node_modules/playwright").is_dir()
    if node:
        version = subprocess.run([node, "-p", "process.versions.node"], text=True, capture_output=True, check=False)
        major = version.stdout.strip().split(".")[0]
        checks["node"] = version.returncode == 0 and major.isdigit() and int(major) >= 18
    if args.product:
        url = urlsplit(args.product)
        checks["product_url"] = url.scheme == "https" and url.hostname in {store, front}
        try:
            handle = product_handle(args.product)
        except ValueError:
            checks["product_url"] = False
            handle = None
    else:
        handle = None
    if args.file:
        if not handle:
            parser.error("--file 须同时提供 --product。")
        try:
            count = verify_upload(args.file, handle, expected_count=args.expected_count)
            checks["file"] = True
        except (OSError, ValueError, KeyError, BadZipFile, ElementTree.ParseError) as error:
            checks["file"] = False
            count = str(error)
    else:
        count = None
    result = {
        "ok": all(checks.values()), "checks": checks,
        "store": store, "product_host": front,
        "handle": handle, "count": count,
        "chrome": chrome_path() or None,
        "playwright": str(local_playwright if local_playwright.is_dir() else runtime / "node_modules/playwright"),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
