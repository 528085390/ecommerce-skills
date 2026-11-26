#!/usr/bin/env python3
import json
from playwright.sync_api import sync_playwright

def main():
    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp("http://127.0.0.1:9223")
        ctx = b.contexts[0]
        page = ctx.pages[0]

        res = page.evaluate("""function() {
            var dialog = Array.from(document.querySelectorAll('.el-dialog')).find(function(d) {
                return d.innerText.indexOf('编辑SPU') !== -1;
            });
            var btn = Array.from(dialog.querySelectorAll('button')).find(function(b) {
                return b.innerText.trim() === '更新';
            });
            var comp = btn.__vue__;
            while (comp && !comp.handleUpdate) comp = comp.$parent;
            if (comp) {
                return comp.handleUpdate.toString();
            }
            return 'No comp';
        }""")
        print("handleUpdate source code:")
        print(res)

if __name__ == '__main__':
    main()
