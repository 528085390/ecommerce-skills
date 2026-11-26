#!/usr/bin/env python3
"""Agent 专用浏览器（Playwright Chromium + CDP + 指纹伪装）

约定：这是 agent 操作网页的默认浏览器，登录态都保存在这个 profile 里。
用户明确说「用内置浏览器」时才改用 WorkBuddy 内置浏览器。

为什么不用系统 Chrome：
  macOS 26/27 的 libaperitif.dylib 会在浏览器以「非 LaunchServices 方式」启动时
  把进程掐掉（崩溃信号 SIGTRAP，helper 侧 ApertureCheckInitialized abort）。
  从命令行跑 /Applications/Google Chrome.app/... 一定会崩，与本机沙箱无关。
  Playwright 自带 Chromium 的 bundle id 不同，不受该拦截影响。

为什么要有指纹伪装：
  裸 Playwright 的 navigator.webdriver=true、plugins=0、无 window.chrome，
  阿里 x5sec 会直接判机器，滑块怎么拖都失败（errorYpbxq）。
  指纹参数首次生成后落盘固定，避免每次会话跳变（跳变本身也是特征）。

用法：
  python3 agent_browser.py                      # 启动常驻实例（默认端口 9223）
  python3 agent_browser.py --url https://x.com  # 启动并打开指定站点
  python3 agent_browser.py --port 9333          # 换端口（一个 profile 同时只能一个实例）
  python3 agent_browser.py --open <url>         # 在已运行的实例里新开标签页
  python3 agent_browser.py --status             # 看实例状态和当前标签页

可配置（换机器/换人的时候只改环境变量，不改代码）：
  AGENT_BROWSER_PROFILE  profile 目录，默认 ~/.cache/agent-browser（Windows 为 %LOCALAPPDATA%\agent-browser）
  AGENT_BROWSER_PORT     CDP 端口，默认 9223

登录态保存在 profile 目录里，退出后重开照样在。
清理登录态 = 删掉该目录（会连带清掉指纹文件 fp.json，下次重新生成）。
"""
import argparse
import json
import os
import random
import sys
import time


def default_profile():
    env = os.environ.get("AGENT_BROWSER_PROFILE")
    if env:
        return os.path.expanduser(env)
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "agent-browser")
    return os.path.expanduser("~/.cache/agent-browser")


PROFILE = default_profile()
FP_FILE = os.path.join(PROFILE, "fp.json")
DEFAULT_PORT = int(os.environ.get("AGENT_BROWSER_PORT", "9223"))

STEALTH_JS = r"""
(() => {
  const FP = __FP_JSON__;
  const def = (o, p, g) => { try { Object.defineProperty(o, p, { get: g, configurable: true }); } catch (e) {} };

  // 1. webdriver
  def(Navigator.prototype, 'webdriver', () => undefined);
  try { delete Object.getPrototypeOf(navigator).webdriver; } catch (e) {}

  // 2. 语言 / 平台 / 硬件
  def(Navigator.prototype, 'languages', () => ['zh-CN', 'zh', 'en']);
  def(Navigator.prototype, 'language', () => 'zh-CN');
  def(Navigator.prototype, 'hardwareConcurrency', () => FP.hardwareConcurrency);
  def(Navigator.prototype, 'deviceMemory', () => FP.deviceMemory);
  def(Navigator.prototype, 'platform', () => 'MacIntel');
  def(Navigator.prototype, 'maxTouchPoints', () => 0);

  // 3. 插件（Chrome 内置 5 个 PDF 相关插件）
  const mk = (n, f, d) => {
    const p = Object.create(Plugin.prototype);
    Object.defineProperties(p, {
      name: { value: n, enumerable: true }, filename: { value: f, enumerable: true },
      description: { value: d, enumerable: true }, length: { value: 1, enumerable: true },
    });
    return p;
  };
  const list = [
    mk('PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format'),
    mk('Chrome PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format'),
    mk('Chromium PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format'),
    mk('Microsoft Edge PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format'),
    mk('WebKit built-in PDF', 'internal-pdf-viewer', 'Portable Document Format'),
  ];
  const pa = Object.create(PluginArray.prototype);
  list.forEach((p, i) => { pa[i] = p; });
  Object.defineProperty(pa, 'length', { value: list.length });
  Object.defineProperty(pa, 'item', { value: (i) => list[i] || null });
  Object.defineProperty(pa, 'namedItem', { value: (n) => list.find(p => p.name === n) || null });
  def(Navigator.prototype, 'plugins', () => pa);
  def(Navigator.prototype, 'mimeTypes', () => {
    const arr = Object.create(MimeTypeArray.prototype);
    Object.defineProperty(arr, 'length', { value: 2 });
    return arr;
  });

  // 4. window.chrome
  window.chrome = window.chrome || {};
  window.chrome.runtime = window.chrome.runtime || {
    connect: () => {}, sendMessage: () => {},
    onMessage: { addListener: () => {}, removeListener: () => {} },
  };
  window.chrome.app = window.chrome.app || {
    isInstalled: false,
    InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
    RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' },
  };
  window.chrome.csi = window.chrome.csi || (() => ({ onloadT: Date.now(), startE: Date.now(), pageT: 1000, tran: 15 }));
  window.chrome.loadTimes = window.chrome.loadTimes || (() => ({
    requestTime: Date.now() / 1000 - 0.3, startLoadTime: Date.now() / 1000 - 0.3,
    commitLoadTime: Date.now() / 1000 - 0.2, finishDocumentLoadTime: Date.now() / 1000 - 0.1,
    finishLoadTime: Date.now() / 1000, firstPaintTime: Date.now() / 1000 - 0.05,
    firstPaintAfterLoadTime: 0, navigationType: 'Other', wasFetchedViaSpdy: true,
    wasNpnNegotiated: true, npnNegotiatedProtocol: 'h2', wasAlternateProtocolAvailable: false,
    connectionInfo: 'h2',
  }));

  // 5. WebGL vendor / renderer
  const patchGL = (proto) => {
    if (!proto) return;
    const orig = proto.getParameter;
    proto.getParameter = function (p) {
      if (p === 37445) return FP.webglVendor;
      if (p === 37446) return FP.webglRenderer;
      return orig.call(this, p);
    };
  };
  patchGL(window.WebGLRenderingContext && WebGLRenderingContext.prototype);
  patchGL(window.WebGL2RenderingContext && WebGL2RenderingContext.prototype);

  // 6. 权限查询
  if (navigator.permissions && navigator.permissions.query) {
    const origQ = navigator.permissions.query;
    navigator.permissions.query = (params) => (
      params && params.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission, onchange: null })
        : origQ.call(navigator.permissions, params)
    );
  }

  // 7. canvas 微噪声（同 seed，稳定不影响可读性）
  const toDataURL = HTMLCanvasElement.prototype.toDataURL;
  HTMLCanvasElement.prototype.toDataURL = function (...args) {
    try {
      const c = this.getContext('2d');
      if (c && this.width > 16 && this.height > 16) {
        const img = c.getImageData(0, 0, 1, 1);
        img.data[0] = (img.data[0] + Math.round((FP.canvasSeed || 0.0005) * 255)) % 255;
        c.putImageData(img, 0, 0);
      }
    } catch (e) {}
    return toDataURL.apply(this, args);
  };

  // 8. 去掉 CDP 痕迹
  ['__playwright', '__pw_manual', '__PW_inspect', 'cdc_adoQpoasnfa76pfcZLmcfl_Array'].forEach(k => {
    try { delete window[k]; } catch (e) {}
  });
  try {
    Object.defineProperty(window, 'outerWidth', { get: () => window.innerWidth });
    Object.defineProperty(window, 'outerHeight', { get: () => window.innerHeight + 85 });
  } catch (e) {}
})();
"""


def load_fp():
    os.makedirs(PROFILE, exist_ok=True)
    if os.path.exists(FP_FILE):
        fp = json.load(open(FP_FILE))
    else:
        fp = {}
    changed = False
    for k, v in {
        "hardwareConcurrency": random.choice([8, 10, 12]),
        "deviceMemory": 8,
        "screen": random.choice([[1512, 982], [1440, 900], [1728, 1117]]),
        "webglVendor": "Apple Inc.",
        "webglRenderer": random.choice(["Apple M2", "Apple M3", "Apple M1 Pro"]),
        "canvasSeed": round(random.uniform(0.0001, 0.0009), 6),
    }.items():
        if k not in fp:
            fp[k] = v
            changed = True
    if changed:
        json.dump(fp, open(FP_FILE, "w"))
    return fp


def _playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("缺少 playwright：python3 -m pip install playwright && python3 -m playwright install chromium")
    return sync_playwright


def launch(port, url):
    sync_playwright = _playwright()
    fp = load_fp()
    w, h = fp["screen"]
    ua = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/159.0.0.0 Safari/537.36")

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, headless=False,
            args=[f"--remote-debugging-port={port}",
                  "--disable-blink-features=AutomationControlled",
                  "--no-sandbox", "--disable-dev-shm-usage", "--start-maximized",
                  "--lang=zh-CN"],
            user_agent=ua, locale="zh-CN", timezone_id="Asia/Shanghai",
            viewport={"width": w, "height": h}, device_scale_factor=2, color_scheme="light",
        )
        ctx.add_init_script(STEALTH_JS.replace("__FP_JSON__", json.dumps(fp)))
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        if url and url != "about:blank":
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
        print(f"READY  profile={PROFILE}  cdp=http://127.0.0.1:{port}", flush=True)
        print("登录态会存进这个 profile；关掉本进程后重开仍在。", flush=True)
        while True:
            time.sleep(30)


def open_tab(port, url):
    sync_playwright = _playwright()
    with sync_playwright() as p:
        try:
            b = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        except Exception as e:
            sys.exit(f"连不上 http://127.0.0.1:{port}（实例没在跑？）：{e}")
        ctx = b.contexts[0]
        pg = ctx.new_page()
        pg.goto(url, wait_until="domcontentloaded", timeout=60000)
        print(f"已打开：{pg.url}")
    status(port, quiet=True)


def status(port, quiet=False):
    sync_playwright = _playwright()
    with sync_playwright() as p:
        try:
            b = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        except Exception as e:
            sys.exit(f"连不上 http://127.0.0.1:{port}：{e}")
        ctx = b.contexts[0]
        if not quiet:
            print(f"CDP  http://127.0.0.1:{port}")
            print(f"profile  {PROFILE}")
            print(f"标签页  {len(ctx.pages)} 个")
        for i, pg in enumerate(ctx.pages, 1):
            try:
                title = pg.title()
            except Exception:
                title = "(未响应)"
            print(f"  [{i}] {title[:60]} | {pg.url[:90]}")


def main():
    global PROFILE, FP_FILE
    ap = argparse.ArgumentParser(description="agent 专用浏览器（持久 profile + CDP + 指纹伪装）")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT,
                    help=f"CDP 端口，默认 {DEFAULT_PORT}（读 AGENT_BROWSER_PORT）")
    ap.add_argument("--profile", default=None,
                    help="profile 目录，默认读 AGENT_BROWSER_PROFILE 或 ~/.cache/agent-browser")
    ap.add_argument("--url", default="about:blank", help="启动后打开的地址")
    ap.add_argument("--open", metavar="URL", help="在已运行的实例里新开标签页")
    ap.add_argument("--status", action="store_true", help="查看实例状态和标签页")
    args = ap.parse_args()

    if args.profile:
        PROFILE = os.path.abspath(os.path.expanduser(args.profile))
        FP_FILE = os.path.join(PROFILE, "fp.json")

    if args.open:
        open_tab(args.port, args.open)
        return
    if args.status:
        status(args.port)
        return
    launch(args.port, args.url)


if __name__ == "__main__":
    main()
