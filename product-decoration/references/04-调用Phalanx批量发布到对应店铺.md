# 第四步 · 调用 Phalanx 批量发布到对应店铺

取得第 3 步的录入结果后，核对 Phalanx 中对应的商品，以及 `商品装修说明.md` 记录的目标平台和店铺。调用 Phalanx 的批量发布功能，将本轮商品发布到各自对应的店铺。请求字段、站点匹配和状态查询见 [Phalanx 批量发布接口](../../../api/phalanx_product_publish_api.md)。

按商品核对批量发布结果。发布成功后，在说明中记录对应店铺、发布结果及实际完成日期，再启动第 5 步搜同款和第 6 步核对店铺商品，两步可并行。若仍在处理或发布失败，记录实际状态，完成日期留「—」。

## 前置与会话

- 第 3 步的录入结果已核对（SPU / SKU 与 CSV 对应）。
- 目标平台和店铺以 `商品装修说明.md` 记录的本轮确认值为准，不要沿用上一次的店铺。
- 会话与第 3 步同一个 Phalanx 登录（`ally.easyambass.com`，凭证在 skill 根目录 `ally.rtf`），请求带 `token` 请求头。会话过期时重新登录取 token，不要靠重试发布。
- 发布前用本轮账号从 `GET /oally/user/info` 的 `data.websites` 按完整域名核对唯一 `website_id`。将同一个会话 token 注入本机的 `PHALANX_TOKEN` 后，可在 Skill 目录运行 `python3 scripts/check_env.py --phalanx-site <目标域名>`。缺记录、出现多条或接口响应不清楚时，在当前账号的「批量发布到站点」弹窗核对。仅处理已核实的站点。

## 发布与续跑

1. 用 `GET /oally/v2/product/list` 带 `spu_like` 查询。按返回记录的 `sku` 与本轮完整 SPU 精确匹配，再核对第 3 步给出的商品内部 ID。分页时检查后续候选，直到确认唯一。按本轮核对的 `website_id` 读取 `published_websites` 对应记录。
2. 对同一商品和站点，已上架且 `process_status=Success` 时复用现有结果。状态为 `Processing` 时继续轮询。初次无记录的目标可以提交，已明确失败的目标先核对失败原因和最新状态，再判断是否重试。只合并待提交站点集合相同的商品。
3. 提交超时、断线或状态不明时，从同一商品和站点恢复回读。待上一次结果明确再决定是否重试。提交受理和处理中保留实际状态，成功项继续交接。

## 验收

逐商品、逐站点核对 `status=Available` 和 `process_status=Success`。记录商品内部 ID、站点域名、`website_id`、最终状态、`rel_id`、`url` 和验收日期。将成功站点的 `rel_id` 作为候选店铺商品 ID 交给第 6 步，由对应店铺后台独立核对。
