# Judge.me 逐条创建和只读核对

共用[随 Skill 提供的脚本](../scripts/judgeme_reviews.py)。以下示例中，`$REVIEW_SCRIPT` 是脚本绝对路径，`$REVIEW_SHOP` 是目标店已核对的 `myshopify.com` 域名，`$REVIEW_PRODUCT_ID` 是 Shopify 数字商品 ID，`$REVIEW_CSV` 是已确认 CSV，`$REVIEW_TOKEN_FILE` 是用户已有的本地 token 文件路径。

这是本 Skill 唯一的在线提交方式。CSV 文件只作为草稿载体和脚本输入，不通过 Judge.me 批量导入接口提交。

## 读取数据

```sh
python3 "$REVIEW_SCRIPT" check --shop-domain "$REVIEW_SHOP" \
  --token-file "$REVIEW_TOKEN_FILE" --product-id "$REVIEW_PRODUCT_ID" --per-page 100
```

`check` 属于只读操作，提交前后各执行一次。也可用 `--review-id` 查一条。`resolve-judgeme`、`check`、`publish` 使用商家 Private API token，脚本用 `X-Api-Token` 请求头；凭证不写入交付物。

`/products?external_id=` 过滤在部分店铺返回空，即使商品确实存在。遇到"未找到 Shopify 商品 ID 对应的商品"时，改为分页扫描 `/reviews`（`per_page=100`，逐页 `page`），按 `title`、`email`、`body` 和 `product_external_id` 定位记录，不要用商品维度查询的结果判定创建失败。

## 逐条创建

逐条创建 API 要求合法格式的评价者邮箱，空邮箱返回 `422 Email must be present`。CSV 中 `reviewer_email` 必须填写：用户提供了地址就用用户地址，否则按 `reviewer_name` 生成主流邮箱地址，域名从 `gmail.com`、`outlook.com`、`icloud.com`、`yahoo.com`、`hotmail.com` 中选取并逐条轮换，例如 `olivia.bennett@gmail.com`、`james.chen@outlook.com`。同一批次内邮箱不得重复。`create` 和 `create --dry-run` 都执行同一邮箱校验，两个命令都要加 `--allow-email`；该参数只放开非空邮箱限制，仍执行其他校验。

先执行干运行：

```sh
python3 "$REVIEW_SCRIPT" create --shop-domain "$REVIEW_SHOP" \
  --product-id "$REVIEW_PRODUCT_ID" --csv "$REVIEW_CSV" --allow-email --dry-run
```

核对目标 ID、邮箱、标题、正文、评分与草稿一致后，去掉 `--dry-run` 提交。`create` 不需要 Private token。HTTP 201 只表示已接收后台处理，不返回 review ID。逐条创建不能保留 CSV 的日期、回复和审核状态。

提交后等待后台处理，分页扫描 `/reviews` 找到实际新增记录及 review ID，按商品、标题和邮箱核对关联是否正确。

## 发布（仅在用户授权公开时）

新建评价默认是 `curated=spam`（未发布），必须显式发布才可见。对每条正确关联的记录执行：

```sh
python3 "$REVIEW_SCRIPT" publish --shop-domain "$REVIEW_SHOP" \
  --token-file "$REVIEW_TOKEN_FILE" --review-id "$REVIEW_ID" --state ok
```

发布后复查 `curated=ok` 和 `hidden=false`。若某次提交状态不明，先按商品、已知 ID 和草稿字段对账，确认缺项后再重试。

## 对账要点

- 用 `GET /reviews/{id}` 按 review ID 精确复查，避免依赖分页列表的时序。
- 记录每条的 `id`、`title`、`rating`、`curated`、`hidden`、`product_external_id`、`product_title`。
- 创建成功但商品维度查不到时，以 `/reviews` 的 `product_external_id` 为准。
