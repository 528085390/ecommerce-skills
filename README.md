# 电商运营 Skills 合集

五个可交接的 Agent Skill 文档包，覆盖跨境电商的**商品页采集 → 选图 → 商品装修刊登 → 评价导入**全链路，面向 Shopify / SHOPLINE 店铺。

每个目录都是一个独立 Skill：`SKILL.md` 是入口，`references/` 放流程细节，`scripts/` 放可执行脚本，`assets/` 放模板与前端片段。

## 包含的 Skill

| Skill | 用途 | 主要产物 |
| --- | --- | --- |
| [product-page-capture](product-page-capture/SKILL.md) | 从商品详情页抓商品名称、简介、标签、多件折扣、全部轮播与详情媒体（禁止 OCR） | `商品数据/MMDD-中文-英文/`：`封面.jpg`、`轮播图/`、`详情图/`、商品详情 HTML、名称简介标签 MD |
| [product-image-selection](product-image-selection/SKILL.md) | 按宽高比挑选轮播图与详情图，优先扩图补齐，缺图逐项说明 | 「商品名字＋选图」文件夹 + 缺口说明 Markdown（默认 16:9×3、4:3×2、1:1×2、9:16×2、3:4×2，共 11 张） |
| [product-decoration](product-decoration/SKILL.md) | 全流程商品装修：竞品采集 → 单品 CSV → Phalanx 录入并发布到指定店铺 → 1688 以图搜同款 → 补采购与 ERP → 建模板、填卖点标签、绑定并验收 | 已发布商品、详情页模板、`1688搜图结果.json/.csv`、验收记录 |
| [shopify-review-import](shopify-review-import/SKILL.md) | 按商品链接/列表读取详情，生成评价草稿，制表校验，用 Judge.me 逐条 `POST /reviews` 提交并验收 | 评价 CSV 草稿、校验报告、已提交评价 |
| [shopline-review-import](shopline-review-import/SKILL.md) | 同上，走 SHOPLINE 商品评价应用：生成文案 → 制表校验 XLSX → 上传 → 核对回执与公开状态 | 评价 XLSX、上传回执、验收记录 |

`product-image-selection` 与 `product-page-capture` 都依赖 `product-decoration` 的采集规范，建议五个一起安装，保持同级目录结构（部分文档使用 `../product-page-capture/SKILL.md` 这类相对链接）。

## 安装

把整个目录下的五个文件夹复制到你的 Agent 的 skills 目录即可：

| Agent | skills 目录 |
| --- | --- |
| Claude Code | `~/.claude/skills/` |
| Codex | `~/.codex/skills/` |
| Gemini CLI | `~/.gemini/config/skills/` |

```bash
git clone <本仓库地址> ecommerce-skills
cp -R ecommerce-skills/product-* ecommerce-skills/shop*-review-import ~/.claude/skills/
```

## 凭证与安全

**本仓库不包含任何账号、密码或 token。** 原作者本地的 `.rtf` 明文凭证文件（`ally.rtf`、`独立站产品刊登系统key.rtf`）已被排除，`.gitignore` 也会挡住同类文件。

运行时按需注入环境变量，值只在本机读取，不写进命令回显、日志或交付文件：

| 变量 | 用途 |
| --- | --- |
| `DLZ123_ACCOUNT` / `DLZ123_PASSWORD` / `DLZ123_PHPSESSID` | 单品采集站登录与会话复用 |
| `PHALANX_ACCOUNT` / `PHALANX_PASSWORD` / `PHALANX_TOKEN` | Phalanx（`ally.easyambass.com`）登录与接口 token |
| `SHOPLINE_ACCESS_TOKEN` | 核对 SHOPLINE 后台商品（需 `read_products`） |
| `REVIEW_TOKEN_FILE` / `REVIEW_SHOP` / `REVIEW_PRODUCT_ID` / `REVIEW_CSV` | 评价导入脚本的 token 文件路径与目标店铺参数 |

换机器或换人接手时，先读 [product-decoration/references/移植与适配指南.md](product-decoration/references/移植与适配指南.md)，再跑 `python3 scripts/check_env.py` 做环境自检。

## 运行依赖

- **Python 3**：多数脚本（`requests` 等按脚本内说明安装）
- **Node.js + Playwright + 桌面 Chrome**：SHOPLINE 评价上传需要已登录的浏览器会话
- **Ruby**：`save_product_page.rb`
- **可调试的 Chrome（CDP 9223）**：1688 搜图、接口抓包需要复用同一个已登录 profile

## 目录结构

```text
.
├── product-decoration/          # 全流程装修（最大的一个，含 13 篇 references）
├── product-image-selection/
├── product-page-capture/
├── shopify-review-import/
└── shopline-review-import/
```

## 已知说明

- 文档里少数相对链接（如 `../../../api/...`、`../../../商品数据/...`）指向作者本地工作区，仓库内不含对应文件，按需自行补建。
- 各 Skill 内含平台接口细节与本机实测记录，换店铺前请重新核对域名、主题 ID、权限和模板。
