# SHOPLINE 商品评价接口与登录要求

| 操作 | 接口或入口 | 需要浏览器登录态 | 其他要求 |
| --- | --- | --- | --- |
| 读取公开商品详情、生成草稿、制表和校验 | 商品详情及本地 Python 脚本 | 否 | 商品需可访问。制表使用 Python 3 和内置模板。 |
| 读取后台评价列表和现有评价数 | 商品评价应用列表或商品详情 | **需要** | 使用目标店铺的后台登录和评价应用权限。 |
| 探测会话、上传 XLSX、只查导入回执 | 上传脚本接入目标店铺评价应用 | **需要** | 安装 Node.js、桌面 Chrome 和 Playwright。登录脚本打开的 Chrome 会话，或按 README 复用已登录的本机 Chrome。普通 SHOPLINE Open API token 无法用于当前上传脚本。 |
| 核对是否在前台展示 | 公开商品页 | 否 | 评价须已发布，且主题需要启用评价展示。后台核对实际评价或隐藏状态仍需登录。 |

## 当前上传脚本使用的请求

这是已实测的商品评价应用网页接口，路径相对目标店铺后台。其他店铺须先运行 `--probe` 确认应用、权限及响应兼容性。调用在已登录应用页的同源会话中完成。

| 请求 | 用途和参数 |
| --- | --- |
| `POST /api/gsv-comment/comment/import` | 上传 XLSX。multipart 字段为 `file`、`needIdempotent=false`、`templateType=1`。当前应用的 CSRF 请求头是 `a_osudb_csrf`，由上传脚本在页面会话中取得。 |
| `POST /api/gsv-comment/common/progress/comment/page` | 只读查询导入记录。JSON 参数为 `pageNum`、`pageSize`、`execActionList`。脚本按原文件名和导入动作匹配任务，并核对完成状态、成功数和失败数。 |

`--probe` 会查导入记录确认会话可用，`--check-only` 用原文件查回执。两者都需要登录，且均不会提交文件。遇到登录失效，先在脚本使用的同一 Chrome 会话重新登录。会话、CSRF、浏览器资料目录和本地提交记号留在自己的环境中。

本页的网页接口以[随包上传脚本](../scripts/shopline_review_upload.mjs)为准。
