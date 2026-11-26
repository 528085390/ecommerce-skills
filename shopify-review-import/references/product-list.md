# Shopify 商品列表自动导入

按本轮用户给出的店铺、列表或链接清单、筛选条件、评价数口径、每款目标数量、处理上限、可见性和停止条件执行。用户指定“补到 50 条”时，用 50 减去该商品在指定口径下的现有条数，最低为 0。按用户指明的顺序执行。缺失影响批量提交范围的规则时集中确认，同时可先读取目录和核对基线。

1. **读取清单。** 用户给出商品链接清单时保留其顺序。由店铺目录开始时，通过 Shopify Admin GraphQL 的 `products` 读取 `id`、`title`、`handle`、`status`、`onlineStoreUrl`。请求 `pageInfo { hasNextPage endCursor }`，下一页传 `after`，直到覆盖用户授权范围。指定 Shopify 后台筛选或集合时，按对应筛选读取目录。核对返回的店铺，并按 Shopify 商品 ID 去重。[Shopify 商品查询与分页](https://shopify.dev/docs/api/admin-graphql/latest/queries/products)
2. **筛选和算量。** 从 Judge.me 读取各商品的现有评价，按本轮要求区分已发布、未发布、归档及总数。用同店 Shopify 外部商品 ID 对齐。分页读全后再计算，查询失败或商品对应关系不明确时标记待核对。记录每款 Shopify ID、handle、当前数量、目标数量、本次应导入条数和顺序。
3. **一次确认范围。** 展示候选清单、每款应导入条数、合计及可见性，核对草稿与授权。用户已明确授权包含这些文件和商品的整批全自动导入时，直接在授权范围内执行，无需逐款问。只要求筛选或制表时交付清单或文件。
4. **逐款执行。** 实际读取每款商品详情，记录文案使用的事实出处。详情不足时跳过该款并记录原因。每款编制独立 CSV，保留已核对的商品句柄并填写合法邮箱（用户提供地址优先，否则按姓名生成主流邮箱地址，域名从 `gmail.com`、`outlook.com`、`icloud.com` 等中轮换），按主 Skill 的上传前参数跑 `validate-csv --allow-email`。提交统一走 Judge.me 逐条创建 API `POST /reviews`：先 `create --allow-email --dry-run` 核对，再正式提交。提交前复查商品身份和评价基线。若评价数变化，重新计算缺口，只在原授权范围内提交。同一店铺串行提交并逐款验收，记录文件名、review ID、实际新增、发布和前台状态。
5. **对账和续跑。** 将清单和回执保存在本批输出目录，按 Shopify 商品 ID 记录待处理、已提交、已验收、跳过或失败。续跑时先对账已提交项并跳过已验收项。只补确认未导入的行。遇到店铺或商品错配、提交状态不明或可能重复时，先停止提交并排查。达到用户指定的款数、条数上限或列表结束即停止，汇报逐款结果和待处理项。

此工作流复用 rovenxa 已实测的单商品提交和验收步骤。Shopify 多商品连续写入尚无实测回执。换店或首次执行列表批次时，先验收同批第一款，再继续处理其余已授权商品。

已登录且安装的 Shopify CLI 支持 `store execute` 时，可用下面的只读命令从目标店开始枚举。后续页把返回的 `endCursor` 填入 `products` 的 `after`，并沿用排序和筛选条件。

```sh
shopify store execute --store example-shop.myshopify.com --query 'query { shop { myshopifyDomain } products(first: 50, sortKey: ID) { nodes { id title handle status onlineStoreUrl } pageInfo { hasNextPage endCursor } } }'
```
