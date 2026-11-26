#!/usr/bin/env python3
"""Phalanx 接口抓包监听器
连接到 CDP 端口 9223 上的常驻浏览器，监听所有发往 Phalanx API 的请求和响应，
实时打印并持久化到 /tmp/phalanx_api_captured.log。
"""
import json
import os
import sys
import time
from playwright.sync_api import sync_playwright

LOG_PATH = "/tmp/phalanx_api_captured.log"
CDP_URL = "http://127.0.0.1:9223"

def main():
    print(f"Connecting to CDP at {CDP_URL}...", flush=True)
    with sync_playwright() as p:
        try:
            b = p.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            sys.exit(f"Failed to connect CDP: {e}")
            
        ctx = b.contexts[0]
        
        with open(LOG_PATH, "a", encoding="utf-8") as log_f:
            log_f.write(f"\n\n=== NEW CAPTURE SESSION STARTED AT {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
            log_f.flush()

        def attach_to_page(page):
            print(f"Attached listener to page: {page.url}", flush=True)

            def on_request(req):
                url = req.url
                if not any(url.endswith(ext) for ext in ['.js', '.css', '.png', '.jpg', '.woff', '.woff2', '.ttf', '.svg', '.ico']):
                    entry = {
                        "time": time.strftime("%H:%M:%S"),
                        "type": "REQUEST",
                        "method": req.method,
                        "url": url,
                        "headers": {k: v for k, v in req.headers.items() if k in ["token", "content-type", "authorization"]},
                        "post_data": req.post_data
                    }
                    line = f"[{entry['time']}] -> {req.method} {url}"
                    print(line, flush=True)
                    if req.post_data:
                        print(f"      PAYLOAD: {req.post_data[:500]}", flush=True)
                    with open(LOG_PATH, "a", encoding="utf-8") as f:
                        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                        f.flush()

            def on_response(res):
                url = res.url
                if not any(url.endswith(ext) for ext in ['.js', '.css', '.png', '.jpg', '.woff', '.woff2', '.ttf', '.svg', '.ico']):
                    body = ""
                    try:
                        body = res.text()
                    except Exception:
                        pass
                    entry = {
                        "time": time.strftime("%H:%M:%S"),
                        "type": "RESPONSE",
                        "status": res.status,
                        "url": url,
                        "body": body[:2000] if body else ""
                    }
                    line = f"[{entry['time']}] <- {res.status} {url}"
                    print(line, flush=True)
                    if body:
                        print(f"      RESPONSE: {body[:300]}", flush=True)
                    with open(LOG_PATH, "a", encoding="utf-8") as f:
                        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                        f.flush()

            page.on("request", on_request)
            page.on("response", on_response)

        for pg in ctx.pages:
            attach_to_page(pg)
        ctx.on("page", attach_to_page)

        print("Listening for Phalanx API requests... (ready for user action)", flush=True)
        while True:
            time.sleep(1)

if __name__ == "__main__":
    main()
