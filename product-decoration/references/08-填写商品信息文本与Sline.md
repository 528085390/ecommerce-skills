# 第八步 · 填写商品信息文本与 Sline

两个平台都在本地填写模板，使用第 7 步对应的主题 CLI 限路径上传和回读。Shopify 先查看目标主题的模板及引用的区块，使用该主题已有的卖点和标签设置。与底稿比对改动范围，回读后核对上传文件和采集原文，再交第 9 步完整模板路径和后缀。命令见[第 7 步 Shopify 路径](07-创建商品详情页模板.md#shopify)。

## SHOPLINE

只改三个字段：标题下的桌面卖点 `text`、手机卖点 `text_mobile`、标签区 `custom-sline.sline`。模板里其他内容一律不动。

## 输入

- 第 7 步核对的底稿和目标路径。独立执行时复用验收后的底稿，合并上传时直接用已核对的默认底稿，更新已有模板时用最新回拉的专用模板。生成文件写到未被占用的暂存路径。
- 第 1 步的采集清单（`商品数据/_work/<xxx>_manifest.json`）。
- 第 1 步的 `商品名称_简介_标签.md`（在素材目录里）。

## 先确认素材齐不齐

填之前先看清单里三项：`intro`（标题下卖点）、`tags`（标签文字）、`details`（详情区原文）。常见三种情况：

| 清单状态 | 卖点来源 | 标签来源 |
|---|---|---|
| `intro` 和 `tags` 都有 | 直接取 `intro` 的每条 `heading` + `body` | 简介 Markdown 末尾的 `product-feature-tags` 容器 |
| `intro` 空，详情区有卖点 | 用 `--detail-block` 指定清单 `details` 中的正文位置。历史 Markdown 已保存的原文卖点也可复用 | 有标签时使用原标签容器。无标签时 Sline 写空串 |
| `intro` 有，`tags` 空 | 取 `intro` 的原文 | Sline 写空串 |

**卖点和标签均须有来源。** 优先使用采集原文，包含可逐条对回的详情原文。无可用原文时可留空，或使用用户提供的文案。逐字保留标点、数字、表情和顺序。

选详情卖点时，在说明中记录选定的正文块位置，方便回读和续跑。块位置从 `details` 第 1 项起算，图片等其他块也占一个位置。脚本按清单原顺序读取所选正文。历史 Markdown 的正文回落在「多件折扣」或标签 HTML 处结束，并逐条对回采集原文。

确需留空或用用户文案时，按下文格式在专用模板副本手工填入，记录来源。回读时解析 JSON，比对手工生成的预期文件，同时与底稿比较，确认只改三个指定字段。

## 定位三个字段

Fashion 主题的路径是：

```
sections.main-product-info.blocks.main.blocks.info
```

在 `block_order` 里找到 `title` 和 `price`，两者之间的区块应当是 `text` 和 `custom-sline`。区块 ID 会随主题变化（实测出现过 `1793601177245e2717be`、`179360123709246c5b90`），**只按类型和位置定位，不认 ID**。

同层可能还有别的 `custom-sline`（例如 `tiered-pricing-bundle`，承载多件折扣，样例长度可达 8000+ 字符）。**只能改标题和价格之间那个**，其他的碰都别碰。

## 用脚本生成

```bash
helper=skill/product-decoration/scripts/fill_shopline_template.py
manifest=商品数据/_work/商品清单文件名.json
target=templates/product.1124-hand-crank-charger.json
baseline="$stage_dir/templates/product.json"
render_dir=$(mktemp -d)
folder_name=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["folder_name"])' "$manifest")
summary_md="商品数据/$folder_name/商品名称_简介_标签.md"
copy_args=()
# 页面确无标题下简介时填入已选正文块位置。
# 燃油壶嘴实测：copy_args=(--detail-block 5 --detail-block 8 --detail-block 11 --detail-block 13 --detail-block 15)
test -s "$baseline" && test -s "$summary_md" &&
mkdir -p "$render_dir/templates" &&
cp "$stage_dir/theme.schema.json" "$stage_dir/theme.config.json" "$render_dir" &&
python3 "$helper" "$baseline" "$manifest" "$summary_md" "$render_dir/$target" "${copy_args[@]}"
```

示例从工作区根目录执行。将清单、目标路径及底稿换成本轮实际路径。续跑已有模板时，将 `baseline` 指向核对过的目标模板。

四个位置参数依次为 `baseline`、`manifest`、`summary_md`、`target`。脚本**拒绝覆盖已存在的文件**（保护底稿），失败时先看是不是路径已存在。

成功输出形如 `已写入 8 条卖点和 0 个标签，Sline 已清空`。条数要和素材对得上，对不上说明取数规则走了预期外的分支。

生成后自检：

```bash
python3 - "$render_dir/$target" <<'EOF'
import json, sys
t = json.load(open(sys.argv[1], encoding="utf-8"))
info = t["sections"]["main-product-info"]["blocks"]["main"]["blocks"]["info"]
for k, v in info["blocks"].items():
    if v["type"] == "text":
        s = v["settings"]; print("text 条数:", s["text"].count("<br><br>") + 1, "| 手机同文:", s["text"] == s["text_mobile"])
    if v["type"] == "custom-sline":
        print("custom-sline", k, "sline 长度:", len(v["settings"].get("sline", "")))
EOF
```

## 填写规则

- 卖点之间的分隔是 `<br><br>`，每条单独一段。
- 整段包在 `<p><span style="color: #e03e2d;"><strong>…</strong></span></p>` 里，红色用主题现有的 `#e03e2d`。
- 原文里的 `&`、`<`、`>` 做一次 HTML 转义（`escape(..., quote=False)`），**只做一次**。转义两次会在页面上显示成 `&amp;`。
- 表情、标点、数字、空格、大小写、顺序全部照录。竞品原文自相矛盾也照录，需要说明时写在交付记录里。
- `text` 和 `text_mobile` 填同一份内容。只填一个，另一端会残留旧卖点或空白。
- 标签用完整容器，包含 `<div class="product-feature-tags">…</div>` 和原有 `<style>`，整段替换 `sline`。四个、五个标签都全部保留。
- 本品没有标签时 `sline` 写空串。空串会让标签区留一块空白，但比残留别的商品文案安全；要去掉留白需改动 `block_order`，属于结构改动，先问用户。

## 上传与回读校验

复用第 7 步已核对的 `cli`、`theme_id` 和 `verify_dir`。上传和回读使用生成文件时记录的 `render_dir` 和同一个目标路径。批量时在同一个 `render_dir` 生成各目标，然后在 `--only` 列出全部目标。

```bash
test -s "$render_dir/$target" &&
"$cli" theme push --theme "$theme_id" --allow-live --path "$render_dir" --nodelete --only "$target" &&
"$cli" theme pull --theme "$theme_id" --path "$verify_dir" --nodelete --only "$target" &&
test -s "$verify_dir/$target" &&
python3 "$helper" "$baseline" "$manifest" "$summary_md" "$verify_dir/$target" --verify "${copy_args[@]}"
```

`--verify` 对整份 JSON 做语义比对：以同一份底稿重新算出期望结果，与回读文件全等才算通过。它同时能发现「只改了三个字段」这件事——若回读里别处也变了，说明有别人在同时编辑，改用最新版本核对，别拿旧副本覆盖。

同店同主题的多个模板可合并一次上传，逐文件回读验收。合并第 7 步时在回读的 `--only` 列表加上 `templates/product.json`，并与上传前的默认底稿做字节比对。

回读通过后，将店铺后台域名、主题 ID、完整目标模板路径和第 6 步的商品编辑链接交给第 9 步。

## 常见问题

| 情况 | 处理 |
|---|---|
| 脚本报「卖点缺失」或「卖点与采集原文不一致」 | 页面确无独立简介时，用 `--detail-block` 选择 `details` 中已核对的正文。历史 Markdown 回落时逐条核对原文。 |
| 脚本报「详情块没有可用的正文原文」 | 检查位置编号是否按清单所有块计数，并选择 `type=text` 的位置。 |
| 脚本报「标签缺失」 | 检查简介 Markdown 末尾有没有 `product-feature-tags` 容器；清单有标签而文件没有时补齐容器，两边都没有则走 Sline 清空。 |
| 脚本报文件已存在 | 保护机制。换新的目标路径，别覆盖底稿。 |
| 桌面更新了，手机仍是旧卖点 | 漏了 `text_mobile`。两端必须同一份内容。 |
| 页面出现 `&amp;` 字面量 | 转义做了两次。改为只转义一次。 |
| 标签少了或样式变了 | 用了不完整的容器。整段复制简介 Markdown 末尾的 HTML，含 `<style>`。 |
| 多件折扣区块被改坏 | 改错了 `custom-sline`。改标题和价格之间那个，`tiered-pricing-bundle` 不动。 |
| 底稿带着别的商品样例文案 | 用本品内容完整替换。本品确实缺项时清空对应字段，不要保留无关文案。 |
| 回读 JSON 格式变了 | 比解析后的整份 JSON，不逐字符比文本。主题更新会导致 `block_order`、`tiered-pricing-bundle` 等结构变化，与本步无关。 |

## 改过取数逻辑要回归

用一款 `intro` 非空的旧商品（如车载暖风机）以当前 `product.json` 为底稿重跑，比对三个字段与成品模板，确认没改坏：

```bash
python3 "$helper" api/themes/shopline/templates/product.json \
  商品数据/_work/viewkoom_car_heater_manifest.json \
  "商品数据/1-1119-车载暖风机-car heater/商品名称_简介_标签.md" /tmp/reg.json
```

主题 `product.json` 会随主题更新变化，整份 JSON 不一致属正常，**只比 `text` / `text_mobile` / `sline` 三个字段**。

## 本次实测

- 模板为 Peakoom 的 Fashion 主题下的 [1119-posture-corrector](../../../api/themes/shopline/templates/product.1119-posture-corrector.json)。默认模板的商品信息区已有两个独立区块，文本区块有桌面和手机两份内容，填入了三条红色加粗卖点；Sline 填入了四个标签和样式。JSON 里只有这三个字段变动。
- 复测 · 不锈钢煎锅：四条卖点填入两端，`#e03e2d` + 加粗，Sline 四个标签原样式，单文件上传后回拉验收通过。
- 复测 · 磁吸 LED 灯：8 张轮播、9 张详情图（含 GIF）、43 个详情图文块。用户要求照录原文，已把远端调整稿换回原文，逐条核验 3 条卖点和 4 个标签。
- 复测 · 手摇应急充电器（无标签商品）：竞品 kenmiso 把卖点放在详情区 `FEATURES`，清单 `intro`、`tags` 都是空数组，原脚本直接报「简介缺失」退出。脚本增加回落：卖点取简介文件正文 8 条原文并逐条比对 `details`；标签两边都没有，Sline 写空串。生成结果 8 条卖点、`text_mobile` 与 `text` 相同、目标 `custom-sline` 为 0 字符、`tiered-pricing-bundle` 未改动。暖风机回归三个字段与成品一致。
- 燃油壶嘴原始简介含「多件折扣」，详情原文选用第 5、8、11、13、15 块。用同一组位置生成与回读校验，简介文件可直接复用第 1 步落盘版本。
