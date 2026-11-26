# CSV 草稿格式（不用于提交）

本 Skill 的提交方式统一为 Judge.me 逐条创建 API `POST /reviews`，见[逐条 API 和只读核对](judgeme-api.md)。

CSV 文件只作为评价草稿载体和 `judgeme_reviews.py` 的输入，字段与模板见 [`assets/judgeme-template.csv`](../assets/judgeme-template.csv)。本地校验用 `validate-csv`，不再需要 Judge.me 后台会话、预签名上传、导入日志或后台"从电子表格导入"入口。

- `reviewer_email` 必须填写合法格式地址（逐条 API 硬性要求），校验和创建命令都加 `--allow-email`。
- `curated` 记录期望可见性；逐条 API 创建后默认为 `spam`，需按授权用 `publish` 改为 `ok`。
- 文件仍保存为无 BOM 的 UTF-8，避免本地校验和脚本读取失败。
