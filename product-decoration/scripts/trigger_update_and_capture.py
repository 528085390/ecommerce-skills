#!/usr/bin/env python3
import json
import time
from playwright.sync_api import sync_playwright

JS_CLICK = """function() {
    var dialog = Array.from(document.querySelectorAll('.el-dialog')).find(function(d) {
        return d.innerText.indexOf('编辑SPU') !== -1;
    });
    if (!dialog) return 'Dialog not found';
    var btn = Array.from(dialog.querySelectorAll('button')).find(function(b) {
        return b.innerText.trim() === '更新';
    });
    if (!btn) return 'Button not found';
    
    var comp = btn.__vue__;
    while (comp && !comp.handleUpdate) comp = comp.$parent;
    if (comp) {
        comp.handleUpdate();
        return 'handleUpdate invoked successfully';
    }
    return 'Component not found';
}"""

def main():
    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp("http://127.0.0.1:9223")
        ctx = b.contexts[0]
        page = ctx.pages[0]

        captured = []

        def on_req(req):
            if not any(req.url.endswith(ext) for ext in ['.js', '.css', '.png', '.jpg', '.woff', '.woff2', '.ttf', '.svg', '.ico']):
                entry = {
                    'type': 'REQUEST',
                    'method': req.method,
                    'url': req.url,
                    'headers': {k: v for k, v in req.headers.items() if k in ['token', 'content-type', 'authorization']},
                    'post_data': req.post_data
                }
                captured.append(entry)
                print(f">>> [REQ] {req.method} {req.url}", flush=True)
                if req.post_data:
                    print(f"    DATA: {req.post_data[:500]}", flush=True)

        def on_res(res):
            if not any(res.url.endswith(ext) for ext in ['.js', '.css', '.png', '.jpg', '.woff', '.woff2', '.ttf', '.svg', '.ico']):
                body = ""
                try:
                    body = res.text()
                except Exception:
                    pass
                entry = {
                    'type': 'RESPONSE',
                    'status': res.status,
                    'url': res.url,
                    'body': body
                }
                captured.append(entry)
                print(f"<<< [RES] {res.status} {res.url}", flush=True)
                if body:
                    print(f"    BODY: {body[:500]}", flush=True)

        page.on('request', on_req)
        page.on('response', on_res)

        print("Calling handleUpdate in page...")
        res = page.evaluate(JS_CLICK)
        print("Action:", res)

        time.sleep(5)

        with open("/tmp/phalanx_captured_update.json", "w", encoding="utf-8") as f:
            json.dump(captured, f, ensure_ascii=False, indent=2)

        print(f"Done! Captured {len(captured)} requests/responses.")

if __name__ == '__main__':
    main()
