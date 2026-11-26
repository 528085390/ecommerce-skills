# Shopify / Judge.me 接口与登录要求

提交统一走逐条创建 API。下表中的 CSV 批量导入接口、预签名上传和后台导入入口在本 Skill 中不再使用。

| 操作 | 接口或入口 | 需要浏览器登录态 | 其他要求 |
| --- | --- | --- | --- |
| 读取公开商品详情、生成草稿、校验 CSV | 商品页、`GET /products/<handle>.js`、本地 `validate-csv` | 否 | 网页读取需要网络及商品可访问。制表校验使用 Python 3。 |
| 读取 Shopify 后台商品列表 | Admin GraphQL `products`，或后台商品列表 | GraphQL 可用已授权的 CLI 或 Admin API 凭证。后台界面需要登录 | 凭证必须属于目标店铺并具备读取商品权限。 |
| 逐条创建评价（唯一提交方式） | Judge.me 公开 API 的 `POST /reviews` | 否 | 官方文档要求合法格式的评价者邮箱，空邮箱返回 422。命令加 `--allow-email` 并填写合成或用户提供的地址。HTTP 201 表示已接收，需后续对账。 |
| 脚本核对记录或修改发布状态 | Judge.me 公开 API 的 `GET /products`、`GET /reviews`、`GET /reviews/{id}`、`PUT /reviews/{id}` | 否 | 目标店铺域名与 Judge.me Private API token。修改发布状态须在授权范围内。 |

- [逐条 API 和只读核对](judgeme-api.md)包含脚本调用、邮箱规则、发布步骤和对账方法。公开 API 路径、认证和字段查 [Judge.me 官方 API 文档](https://judge.me/api/docs)及 [Judge.me API 帮助](https://judge.me/help/en/articles/8409180-using-judge-me-api)。
- 商品目录的查询与分页见 [Shopify Admin GraphQL 文档](https://shopify.dev/docs/api/admin-graphql/latest/queries/products)及[商品列表工作流](product-list.md)。
