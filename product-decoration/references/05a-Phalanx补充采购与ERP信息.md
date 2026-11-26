# 第五步增补 · 在 Phalanx 补充采购与 ERP 信息

商品已发布且 1688 货源已确认后，沿用第 3 步用采集站模板导入的商品和 SKU，在 Phalanx 补齐采购、报关与物流字段，供后续订单采购使用。

---

## 一、适用时机与前后关联

本步需要以下输入。

- 第 3 步交出的 Phalanx 商品内部 ID，以及有效的 Phalanx 会话。
- 第 5 步已确认的货源。完整采购链接、人民币成本价和单件克重均有可核对来源。
- 本轮商品对应的供应商代码与名称、产品属性和海关编码。

本步可与第 6–9 步并行。使用普通「更新」保存采购信息，更新成功后把结果写入说明，供第 10 步交付。

---

## 二、必填字段与取值规范

文档示例和脚本内置的供应商、编码及产品属性需要按本轮商品核对。执行脚本时显式传入确认值。若成本、重量或商品属性因 SKU 不同而不同，逐 SKU 核对和填写。当前脚本适用于统一写入一组值的情况。

| 字段名称 | 接口字段名 | 界面位置 | 格式与取值规范 | 取值来源或示例 |
|---|---|---|---|---|
| **采购链接** | `purchase_link` | 基础信息 | 1688 商品完整详情 URL（`https://detail.1688.com/offer/...html`） | 来自 1688 搜同款选中的候选商品 |
| **成本价** | `cost_price` | 基础信息 + 规格表 | 人民币金额（数字浮点），SPU 与所有 SKU 均需填入 | 1688 首档/起批单价，如 `26.5` |
| **商品质量 / 重量** | `weight` / `weight_unit` | 基础信息 + 规格表 | 净重或包装毛重，**单位固定为克 (`g`)**，SPU 与所有 SKU 均需填入 | 1688 包装规格表或参数，如 `750` |
| **供应商** | `supplier` / `supplier_code` | 基础信息 + 规格表 | 选择本轮确认的签约供应商，**代码与名称需同时存在** | 历史示例 `GZCC` / `广州池骋` |
| **海关编码** | SPU 的 `hs_code`，各变体的 `erp_product_variant.hs_code` | 报关信息 + 规格表 | **必须为 10 位数字** | 采用本轮商品已确认的报关编码 |
| **产品属性 / 敏感信息** | `express_type` | 基础信息 | 下拉单选枚举值：`normal` / `fast` / `fastLiquid` / `cosmeticLiquid` | 普货选 `normal`；带电池/储能电站选 `fast` |

---

## 三、正确执行方法

### 方法一：接口更新

在本机将本轮 Phalanx 会话注入 `PHALANX_TOKEN`。优先把第 3 步的商品内部 ID 传给 `scripts/update_phalanx_spu.py`。只有 SPU 时可用 `--spu` 定位商品，脚本用 `spu_like` 搜索，再按返回的 `sku` 选出唯一的完整匹配。

脚本 GET 一次完整商品实体，只修改采购、报关与物流字段，再提交一次全量 PUT。收到业务码 `200` 即记更新完成。提交超时或断线时记录「结果待确认」。同一 SPU 的更新串行执行。

以下参数是历史示例。执行时换成本轮商品 ID 和已确认的采购值。

```bash
python3 scripts/update_phalanx_spu.py \
  --id 61180 \
  --link "https://detail.1688.com/offer/1050305189268.html" \
  --cost 15.8 \
  --weight 300 \
  --supplier-code "GZCC" \
  --supplier "广州池骋" \
  --hs-code "3926400000" \
  --express-type "normal"

# 只有 SPU 时，可将 --id 参数替换为 --spu <完整 SPU>。
```

### 方法二：Phalanx Web 界面更新

1. 打开浏览器登录 `https://ally.easyambass.com/#/Dashboard`；
2. 导航到 **商品管理 → SPU 列表**，在搜索框输入商家 SPU（如 `G48YX-HL112403`）；
3. **点击 SPU 蓝色链接**，唤起「编辑SPU」弹窗；
4. 在弹窗中逐项修改以下表单：
   - 采购链接：粘贴 1688 商品详情链接；
   - 成本价(RMB)：输入数字（如 `26.5`）；
   - 重量：输入数字（如 `750`），单位下拉保持 `g`；
   - 供应商使用本轮已确认的签约选项；
   - 产品属性（敏感信息）：下拉选择 `特货（带电、带磁）`（常规商品选 `普货`）；
   - 海关编码填写本轮已核对的 10 位数字；
   - **下方规格表**：若有多行规格，逐行填入成本价、重量、海关编码，或点击表头的「批量修改成本价」、「批量修改重量」统一填入；
5. 点击弹窗底部的 **「更新」** 按钮（勿点「更新并发布到站点」，除非当前准备直接发布）；
6. 看到右上角弹出绿色提示「更新成功」，弹窗自动关闭，列表自动刷新。

---

## 四、核心接口协议（抓包验证详情）

1. **获取详情（先查全量）**：
   - `GET https://portal.ecom.umcasual.cn/api/oally/product/get?id={product_id}`
   - 请求头使用本轮会话的 `token`。
   - 返回包含 `body_html`、`image_paths`、`variants`、`option_names` 的完整商品树。
2. **提交更新（全量覆盖）**：
   - `PUT https://portal.ecom.umcasual.cn/api/oally/product/update`
   - Header：`Content-Type: application/json`，`token: <Phalanx_Token>`
   - Body：修改后的完整商品 JSON（见下方变体嵌套结构）；
   - 返回：`{"code": 200, "message": "success"}`。

---

## 五、必须牢记的避坑指南（踩坑总结）

### 坑点 1：未选「产品属性 / 敏感信息」导致提交被静默拦截
- **现象**：在界面点击「更新」按钮没有任何接口发出，或右上角弹出黄色警告：`请选择敏感信息`。
- **原因**：前端代码内置了强校验：
  ```javascript
  if (!this.editForm.express_type) return this.$message.warning("请选择敏感信息"), !1;
  ```
- **避坑对策**：
  - 必须设置 `express_type`！
  - 选项含义：
    - `normal`：普货（日用品、无电池五金、普通塑胶等）
    - `fast`：特货（带电、带磁）——**凡是带有锂电池、充电宝、太阳能电站、磁吸部件的必须选此项**
    - `fastLiquid`：特货（液体、粉末、膏体）
    - `cosmeticLiquid`：化妆品类液体/膏体/粉末

### 坑点 2：海关编码按实际字段填写

填写本轮确认的 10 位数字海关编码，写入 SPU 顶层 `hs_code` 和每个 SKU 的 `erp_product_variant.hs_code`。遇到 SKU 缺少 PUT 所需的 ERP 子对象时，记录上游数据缺项。

### 坑点 3：SPU 顶层数据与 SKU 变体表脱节（双重同步要求）
- **现象**：更新成功后，列表页依然显示 `0 RMB / 0 g`，或 ERP 仓库无法读取单品重量。
- **原因**：Phalanx 的数据模型中，SPU 的 `cost_price` 和 `weight` 只是外显默认值；采购和海外仓物流真正读取的是变体列表 `variants[i]` 以及嵌套对象 `erp_product_variant`（其中的 `pd_weight` 为千克制浮点字符串，如 `"0.750000"`；`pd_target_amount` 为单价浮点字符串，如 `"26.500000"`）。
- **避坑对策**：
  - 必须对 `variants` 列表做完整映射：
    ```python
    v["cost_price"] = cost
    v["weight"] = weight
    v["supplier_code"] = supplier_code
    v["supplier"] = supplier
    v["express_type"] = express_type
    if "erp_product_variant" in v:
        v["erp_product_variant"]["hs_code"] = hs_code
        v["erp_product_variant"]["default_supplier_code"] = supplier_code
        v["erp_product_variant"]["pd_weight"] = f"{weight / 1000.0:.6f}"
        v["erp_product_variant"]["pd_target_amount"] = f"{cost:.6f}"
    ```
  - 使用 `scripts/update_phalanx_spu.py` 可自动处理上述嵌套转换，杜绝手工遗漏。

### 坑点 4：供应商必须「代码与名称同时绑定」
- **现象**：更新后供应商显示为空白，或者海外仓推单时提示未指定供应商代码。
- **原因**：界面上显示的是供应商中文名称（如 `广州池骋`），但后端 ERP 识别的是供应商唯一系统代码（`GZCC`）。
- **避坑对策**：
  - 写入已核对的 `supplier_code` 和 `supplier`；
  - 同步规格表内的 `erp_product_variant.default_supplier_code`。

### 坑点 5：请求方法是 PUT，载荷必须是全量实体
- **现象**：使用 POST 请求返回 404/405；或者只传修改的 5 个字段导致商品原有的 `body_html`（详情富文本）、`image_paths`（轮播图）、`shop_option_names`（规格分类）全部被置空清除。
- **避坑对策**：
  - 必须先 `GET /api/oally/product/get?id={id}` 获取现有实体 JSON；
  - 在原有实体对象上修改目标属性，再以 `PUT` 方式整体提交回 `/api/oally/product/update`。

### 坑点 6：自动化点 UI 易受 Element UI 遮罩层与隐藏元素干扰
- **现象**：Playwright `page.locator('button:has-text("更新")').click()` 超时挂起，或 `locator.fill()` 填入到了隐藏的批量修改模态框输入框中。
- **原因**：弹窗使用了 Element UI，存在 `.v-modal` 遮罩层，且页面存在多个文本包含「更新」的按钮（如「更新并发布到站点」）以及隐藏的 batchUpdate input。
- **避坑对策**：
  - **首选命令行 API 脚本**，绕过所有 DOM 动画与遮罩；
  - 若在浏览器中调试执行，应使用 JS 原生分发或 Vue 组件方法：
    ```javascript
    const dialog = Array.from(document.querySelectorAll('.el-dialog')).find(d => d.innerText.includes('编辑SPU'));
    const btn = Array.from(dialog.querySelectorAll('button')).find(b => b.innerText.trim() === '更新');
    btn.__vue__.$parent.handleUpdate();
    ```

### 坑点 7：Phalanx 会话 Token 的有效性
- **现象**：接口返回业务码 `10000`、`401` 或登录失效。
- **避坑对策**：
  - 本地运行优先使用环境变量 `PHALANX_TOKEN`。兼容旧流程的脚本会在环境变量为空时读取 `/tmp/phalanx_token.txt`。切换账号时注入本轮会话，并运行 `python3 scripts/check_env.py --phalanx` 做只读校验；
  - 登录失效时，重新在浏览器中打开 `https://ally.easyambass.com/#/login` 使用凭证登录一次即可刷新，勿反复重发无效请求。

---

## 六、更新结果

更新接口返回业务码 `200`，或界面显示「更新成功」，即可在 `商品装修说明.md` 记录商品内部 ID、采购来源、实际提交值、更新结果和完成日期。接口明确报错时记录失败原因。提交超时或断线时保留「结果待确认」，完成日期用「—」，店铺装修分支可继续。
