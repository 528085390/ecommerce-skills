#!/usr/bin/env python3
"""环境自检：换机器、换人接手时先跑这一条。

检查 6 类：Python 与依赖 / Ruby 与采集资产 / 浏览器内核 / CDP 实例与 1688 登录态 / SHOPLINE CLI / 工作区目录。
只读，不改任何东西。缺失项会给出可直接复制的修复命令。

用法：
  python3 scripts/check_env.py
  python3 scripts/check_env.py --net            # 额外测网络（1688 + SHOPLINE）
  python3 scripts/check_env.py --phalanx        # 只验证本机 PHALANX_TOKEN
  python3 scripts/check_env.py --phalanx-site example.com  # 验证目标站点是否可选
  python3 scripts/check_env.py --workspace ~/Documents/我的工作区
"""
import argparse
from http.client import HTTPException
import importlib.util
import json
import os
import platform
import re
import shutil
import sys
import urllib.error
import urllib.request

OK, WARN, FAIL = "OK", "WARN", "FAIL"
results = []


def add(level, name, detail="", fix=""):
    results.append((level, name, detail, fix))


def check_python():
    v = sys.version_info
    if v >= (3, 9):
        add(OK, "Python", f"{v.major}.{v.minor}.{v.micro}")
    else:
        add(FAIL, "Python", f"{v.major}.{v.minor}，需要 3.9+", "装 Python 3.9 以上再跑")


def check_playwright():
    if importlib.util.find_spec("playwright"):
        add(OK, "playwright 模块", "已安装")
    else:
        add(FAIL, "playwright 模块", "未安装",
            "python3 -m pip install playwright && python3 -m playwright install chromium")


def check_ruby():
    """第 1 步落盘脚本是 ruby 写的。"""
    exe = shutil.which("ruby")
    if not exe:
        add(FAIL, "Ruby", "没找到（第 1 步落盘脚本需要）",
            "macOS 自带；Debian/Ubuntu: sudo apt install ruby；Windows: RubyInstaller 或 WSL")
        return
    try:
        import subprocess
        out = subprocess.run([exe, "-v"], capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        out = exe
    add(OK, "Ruby", out or exe)


def skill_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def check_capture_assets():
    """检查第 1 步需要的采集器、标签模板和落盘脚本。"""
    root = skill_root()
    need = [
        "assets/extract_storefront.js",
        "assets/product-feature-tags.html",
        "scripts/save_product_page.rb",
    ]
    missing = [path for path in need if not os.path.isfile(os.path.join(root, path))]
    if missing:
        add(FAIL, "采集资产", "缺 " + "、".join(missing),
            "从 skill 包重新取回 assets/ 与 scripts/（两者必须同级，落盘脚本按相对路径读模板）")
    else:
        add(OK, "采集资产", f"{os.path.join(root, 'assets')}（提取脚本 + 标签模板）")


def chromium_dirs():
    home = os.path.expanduser("~")
    if os.name == "nt":
        return [os.path.join(os.environ.get("LOCALAPPDATA", home), "ms-playwright")]
    if sys.platform == "darwin":
        return [os.path.join(home, "Library/Caches/ms-playwright")]
    return [os.path.join(home, ".cache/ms-playwright")]


def check_chromium():
    for d in chromium_dirs():
        if os.path.isdir(d):
            hits = [x for x in os.listdir(d) if x.startswith("chromium")]
            if hits:
                add(OK, "Chromium 内核", f"{d}（{len(hits)} 个版本）")
                return
    add(FAIL, "Chromium 内核", "没找到 Playwright 下载的 Chromium",
        "python3 -m playwright install chromium")


def check_cdp(host, port):
    url = f"http://{host}:{port}/json/version"
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            info = json.loads(r.read().decode("utf-8", "ignore"))
        add(OK, f"CDP {host}:{port}", info.get("Browser", "有响应"))
        return True
    except Exception as e:
        add(FAIL, f"CDP {host}:{port}", f"连不上（{type(e).__name__}）",
            "python3 scripts/agent_browser.py   # 或让 AI 用你自己的浏览器开 CDP")
        return False


def check_1688_login(host, port, cdp_ok):
    if not cdp_ok or not importlib.util.find_spec("playwright"):
        add(WARN, "1688 登录态", "跳过（CDP 或 playwright 不可用）")
        return
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.connect_over_cdp(f"http://{host}:{port}", timeout=8000)
            ctx = b.contexts[0]
            cks = {c["name"] for c in ctx.cookies("https://h5api.m.1688.com")}
    except Exception as e:
        add(WARN, "1688 登录态", f"读不到 cookie（{type(e).__name__}）", "在浏览器窗口里登录 1688")
        return
    if "_m_h5_tk" in cks:
        add(OK, "1688 登录态", "有 _m_h5_tk")
    else:
        add(WARN, "1688 登录态", "缺 _m_h5_tk（未登录或已失效）",
            "在 agent 浏览器窗口里登录 1688，然后重跑")


def find_cli():
    env = os.environ.get("SHOPLINE_CLI")
    if env and os.path.exists(os.path.expanduser(env)):
        return os.path.expanduser(env)
    w = shutil.which("sl")
    if w:
        return w
    home = os.path.expanduser("~")
    for c in [
        os.path.join(home, ".shopline-cli/node_modules/.bin/sl"),
        os.path.join(os.environ.get("APPDATA", ""), "npm/sl.cmd"),
    ]:
        if c and os.path.exists(c):
            return c
    return None


def check_cli():
    cli = find_cli()
    if cli:
        add(OK, "SHOPLINE CLI", cli)
    else:
        add(WARN, "SHOPLINE CLI", "没找到 sl（第 7–8 步需要）",
            "npm i -g @shoplineos/cli  # 或用 SHOPLINE_CLI 指向可执行文件")


def check_workspace(ws):
    if not ws:
        add(WARN, "工作区", "未指定，跳过目录检查", "用 --workspace <你的工作区> 指定")
        return
    add(OK if os.path.isdir(ws) else WARN, "工作区", ws)
    for sub, level in [("商品数据", WARN), ("api", WARN)]:
        p = os.path.join(ws, sub)
        if os.path.isdir(p):
            add(OK, f"  {sub}/", p)
        else:
            add(level, f"  {sub}/", "不存在（首次跑会自动建或需自备）")


def check_proxy():
    keys = ["HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"]
    hit = [f"{k}={os.environ[k]}" for k in keys if os.environ.get(k)]
    add(OK if hit else WARN, "代理环境变量", "，".join(hit) if hit else "未设置（直连）")


def check_net():
    for name, url in [("1688 接口", "https://h5api.m.1688.com"),
                      ("SHOPLINE", "https://www.shopline.com")]:
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=10) as r:
                add(OK, f"网络 · {name}", f"HTTP {r.status}")
        except Exception as e:
            add(WARN, f"网络 · {name}", f"{type(e).__name__}", "检查代理节点或本地网络")


class RejectRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_phalanx(name, path, token):
    login_hint = "在本机为本轮账号登录 Phalanx，并将会话 token 注入 PHALANX_TOKEN 后重跑"
    url = "https://portal.ecom.umcasual.cn/api" + path
    request = urllib.request.Request(url, method="GET", headers={
        "Accept": "application/json",
        "token": token,
    })
    opener = urllib.request.build_opener(RejectRedirect())
    try:
        with opener.open(request, timeout=10) as response:
            if response.status != 200:
                add(FAIL, name, f"HTTP {response.status} · 未能验证会话", "核对只读接口响应")
                return
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        with error:
            if error.code == 401:
                add(FAIL, name, "HTTP 401 · 会话未通过", login_hint)
            elif error.code == 403:
                add(FAIL, name, "HTTP 403 · 访问被拒绝", "核对本轮账号的读取权限及本机代理")
            else:
                add(FAIL, name, f"HTTP {error.code} · 未能验证会话", "检查接口和本机网络")
        return
    except (json.JSONDecodeError, UnicodeDecodeError):
        add(FAIL, name, "接口未返回有效 JSON", "检查登录跳转或本机代理")
        return
    except (OSError, ValueError, HTTPException):
        add(FAIL, name, "只读接口请求失败", "检查本机网络、代理和 token 配置")
        return

    code = str(payload.get("code")) if isinstance(payload, dict) else ""
    data = payload.get("data") if isinstance(payload, dict) else None
    if code in {"10000", "401"}:
        add(FAIL, name, "会话未通过 · 需要重新登录", login_hint)
    elif code == "403":
        add(FAIL, name, "账号无权调用此接口", "核对本轮账号的读取权限")
    elif code == "200" and isinstance(data, dict):
        return data
    else:
        add(FAIL, name, "业务响应未通过会话校验", "核对账号权限和接口响应")


def check_phalanx(site=None):
    name = "Phalanx 会话" if site is None else "Phalanx 发布站点"
    token = os.environ.get("PHALANX_TOKEN", "").strip()
    if not token:
        add(FAIL, name, "缺少 PHALANX_TOKEN", "在本机登录本轮账号并注入会话 token")
        return

    if site is None:
        data = read_phalanx(name, "/oally/v2/product/list?page=1&limit=1", token)
        if data is not None:
            if isinstance(data.get("list"), list):
                add(OK, name, "会话有效，可读取商品列表")
            else:
                add(FAIL, name, "商品列表响应缺少 data.list 数组")
        return

    domain = site.strip().rstrip(".").lower()
    if not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", domain):
        add(FAIL, name, "请输入目标店铺的域名，例如 example.com")
        return

    data = read_phalanx(name, "/oally/user/info", token)
    if data is None:
        return
    websites = data.get("websites")
    if not isinstance(websites, list):
        add(FAIL, name, "账号响应缺少 data.websites 数组", "在本轮账号的发布弹窗中核对站点")
        return
    matches = [
        row for row in websites
        if isinstance(row, dict)
        and isinstance(row.get("website_domain"), str)
        and row["website_domain"].strip().rstrip(".").lower() == domain
    ]
    if not matches:
        add(FAIL, name, f"{domain} 未出现在本轮账号的发布站点清单中")
    elif len(matches) > 1:
        add(FAIL, name, f"{domain} 对应多条站点记录", "到本轮账号的发布弹窗核对")
    else:
        site_id = str(matches[0].get("website_id"))
        if site_id.isascii() and site_id.isdecimal() and int(site_id) > 0:
            add(OK, name, f"{domain} 在本轮账号的发布站点清单中，website_id={site_id}")
        else:
            add(FAIL, name, f"{domain} 的站点 ID 缺失或无效", "到本轮账号的发布弹窗核对")


def main():
    ap = argparse.ArgumentParser(description="product-decoration 环境自检")
    ap.add_argument("--host", default=os.environ.get("AGENT_BROWSER_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("AGENT_BROWSER_PORT", "9223")))
    ap.add_argument("--workspace", default=os.getcwd())
    ap.add_argument("--net", action="store_true", help="额外测试网络连通性")
    ap.add_argument("--phalanx", action="store_true", help="仅调用只读接口验证本机 PHALANX_TOKEN")
    ap.add_argument("--phalanx-site", metavar="DOMAIN", help="只读验证本轮账号的目标发布站点")
    args = ap.parse_args()

    print(f"系统  {platform.system()} {platform.release()}  |  {platform.machine()}\n")

    if args.phalanx or args.phalanx_site is not None:
        check_phalanx(args.phalanx_site)
    else:
        check_python()
        check_playwright()
        check_ruby()
        check_capture_assets()
        check_chromium()
        cdp_ok = check_cdp(args.host, args.port)
        check_1688_login(args.host, args.port, cdp_ok)
        check_cli()
        check_workspace(os.path.abspath(os.path.expanduser(args.workspace)))
        check_proxy()
        if args.net:
            check_net()

    icon = {OK: "✓", WARN: "!", FAIL: "✗"}
    print("检查结果")
    print("-" * 62)
    for level, name, detail, fix in results:
        print(f"{icon[level]} {name:18} {detail}")
        if fix and level != OK:
            print(f"  → {fix}")
    print("-" * 62)

    fails = [r for r in results if r[0] == FAIL]
    warns = [r for r in results if r[0] == WARN]
    print(f"通过 {len([r for r in results if r[0] == OK])} 项，提醒 {len(warns)} 项，阻塞 {len(fails)} 项")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
