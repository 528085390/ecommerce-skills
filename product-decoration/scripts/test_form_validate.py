#!/usr/bin/env python3
import json
from playwright.sync_api import sync_playwright

def main():
    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp("http://127.0.0.1:9223")
        page = b.contexts[0].pages[0]

        res = page.evaluate("""() => {
            const dialog = Array.from(document.querySelectorAll('.el-dialog')).find(d => d.innerText.includes('编辑SPU'));
            const btn = Array.from(dialog.querySelectorAll('button')).find(b => b.innerText.trim() === '更新');
            let comp = btn ? btn.__vue__ : null;
            while (comp && !comp.handleUpdate) comp = comp.$parent;
            if (!comp) return { error: 'Component not found' };

            // 1. 设置 express_type (产品属性)
            const propInput = dialog.querySelector('input[placeholder="产品属性"]');
            if (propInput) {
                const select = propInput.closest('.el-select');
                const v = select ? select.__vue__ : null;
                if (v && v.options && v.options.length > 0) {
                    const opt = v.options.find(o => o.value === 'fast') || v.options[0];
                    if (v.handleOptionSelect) {
                        v.handleOptionSelect(opt, true);
                    } else {
                        v.$emit('input', opt.value);
                        v.$emit('change', opt.value);
                    }
                }
            }

            // 2. 确保 comp.editForm 包含所有必填数据
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

            const valid = comp.validateProductForm();
            return {
                valid: valid,
                express_type: comp.editForm.express_type,
                hs_code: comp.editForm.hs_code,
                supplier_code: comp.editForm.supplier_code,
                cost_price: comp.editForm.cost_price,
                weight: comp.editForm.weight,
                purchase_link: comp.editForm.purchase_link,
                variants: comp.editForm.variants.map(v => ({
                    sku: v.sku,
                    hs_code: v.hs_code,
                    cost_price: v.cost_price,
                    weight: v.weight
                }))
            };
        }""")
        print("Validation test result:")
        print(json.dumps(res, indent=2, ensure_ascii=False))

if __name__ == '__main__':
    main()
