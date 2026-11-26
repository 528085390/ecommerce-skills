#!/usr/bin/env python3
"""Trigger Phalanx SPU Update and capture the full API call & response"""
import json
import time
from playwright.sync_api import sync_playwright

def main():
    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp("http://127.0.0.1:9223")
        ctx = b.contexts[0]
        page = ctx.pages[0]

        captured = []

        def on_req(req):
            url = req.url
            if not any(url.endswith(ext) for ext in ['.js', '.css', '.png', '.jpg', '.woff', '.woff2', '.ttf', '.svg', '.ico']):
                entry = {
                    'type': 'REQUEST',
                    'method': req.method,
                    'url': url,
                    'headers': {k: v for k, v in req.headers.items() if k in ['token', 'content-type', 'authorization']},
                    'post_data': req.post_data
                }
                captured.append(entry)
                print(f">>> [REQ] {req.method} {url}", flush=True)
                if req.post_data:
                    print(f"    DATA: {req.post_data[:600]}...", flush=True)

        def on_res(res):
            url = res.url
            if not any(url.endswith(ext) for ext in ['.js', '.css', '.png', '.jpg', '.woff', '.woff2', '.ttf', '.svg', '.ico']):
                body = ""
                try:
                    body = res.text()
                except Exception:
                    pass
                entry = {
                    'type': 'RESPONSE',
                    'status': res.status,
                    'url': url,
                    'body': body
                }
                captured.append(entry)
                print(f"<<< [RES] {res.status} {url}", flush=True)
                if body:
                    print(f"    BODY: {body[:600]}...", flush=True)

        page.on('request', on_req)
        page.on('response', on_res)

        print("Executing handleUpdate via page.evaluate...")
        res = page.evaluate("""() => {
            const dialog = Array.from(document.querySelectorAll('.el-dialog')).find(d => d.innerText.includes('编辑SPU'));
            if (!dialog) return { error: 'Dialog not found' };
            const btn = Array.from(dialog.querySelectorAll('button')).find(b => b.innerText.trim() === '更新');
            if (!btn) return { error: 'Update button not found' };
            
            let comp = btn ? btn.__vue__ : null;
            while (comp && !comp.handleUpdate) comp = comp.$parent;
            if (!comp) return { error: 'Component not found' };

            // Ensure form is valid
            comp.editForm.express_type = comp.editForm.express_type || 'fast';
            comp.editForm.hs_code = '3926400000';
            if (comp.editForm.variants && comp.editForm.variants.length > 0) {
                comp.editForm.variants.forEach(v => {
                    v.hs_code = '3926400000';
                    v.cost_price = 26.5;
                    v.weight = 750;
                    v.supplier_code = comp.editForm.supplier_code || 'GZCC';
                    v.supplier = comp.editForm.supplier || '广州池骋';
                    v.purchase_link = comp.editForm.purchase_link;
                    v.express_type = comp.editForm.express_type;
                });
            }

            console.log('Invoking comp.handleUpdate()...');
            comp.handleUpdate();
            return { success: true };
        }""")
        print("Evaluate result:", res)

        # Wait for the network calls to finish
        time.sleep(5)

        with open("/tmp/phalanx_captured_update.json", "w", encoding="utf-8") as f:
            json.dump(captured, f, ensure_ascii=False, indent=2)

        print(f"\nDone! Captured {len(captured)} requests/responses.")

if __name__ == '__main__':
    main()
