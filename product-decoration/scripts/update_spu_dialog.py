#!/usr/bin/env python3
"""Fill SPU edit dialog fields in Phalanx"""
import json
import time
from playwright.sync_api import sync_playwright

JS_FILL = r"""
(() => {
    const dialog = Array.from(document.querySelectorAll('.el-dialog')).find(d => d.innerText.includes('编辑SPU'));
    if (!dialog) return { error: 'Dialog not found' };

    const setInputValue = (input, val) => {
        if (!input) return;
        input.value = val;
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
    };

    // 1. 采购链接
    const linkInput = dialog.querySelector('input[placeholder="采购链接"]');
    setInputValue(linkInput, 'https://detail.1688.com/offer/1015660639021.html');

    // 2. 成本价 (RMB) - SPU & 规格表
    const costInputs = dialog.querySelectorAll('input[placeholder="成本价(RMB)"]');
    costInputs.forEach(inp => setInputValue(inp, '26.5'));

    // 3. 重量 - SPU & 规格表
    const weightInputs = dialog.querySelectorAll('input[placeholder="重量"]');
    weightInputs.forEach(inp => setInputValue(inp, '750'));

    // 4. 海关编码
    const hsInputs = dialog.querySelectorAll('input[placeholder="海关编码"]');
    hsInputs.forEach(inp => setInputValue(inp, '3926400000'));

    // 5. 供应商 - 选第一个
    const suppInput = dialog.querySelector('input[placeholder="供应商"]');
    let suppSelected = false;
    let suppLabel = '';
    if (suppInput) {
        const select = suppInput.closest('.el-select');
        const v = select ? select.__vue__ : null;
        if (v && v.options && v.options.length > 0) {
            const firstOpt = v.options[0];
            if (v.handleOptionSelect) {
                v.handleOptionSelect(firstOpt, true);
            } else {
                v.$emit('input', firstOpt.value);
                v.$emit('change', firstOpt.value);
            }
            suppSelected = true;
            suppLabel = firstOpt.label || firstOpt.currentLabel || firstOpt.value;
        }
    }

    return {
        purchaseLink: linkInput ? linkInput.value : '',
        costPrices: Array.from(costInputs).map(i => i.value),
        weights: Array.from(weightInputs).map(i => i.value),
        hsCodes: Array.from(hsInputs).map(i => i.value),
        supplier: suppLabel || (suppInput ? suppInput.value : '')
    };
})()
"""

def main():
    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp("http://127.0.0.1:9223")
        ctx = b.contexts[0]
        page = ctx.pages[0]
        
        res = page.evaluate(JS_FILL)
        print("Filled values result:")
        print(json.dumps(res, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
