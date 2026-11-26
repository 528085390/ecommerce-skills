#!/usr/bin/env python3
"""Fill or verify the three product-intro settings in a SHOPLINE Fashion template.

卖点来源：优先用采集清单的 `intro`。没有标题下简介时，可用 --detail-block 选择
清单 `details` 中的原文正文块。历史简介 Markdown 中已有卖点的，也可继续复用。
标签来源：简介 Markdown 末尾的标签容器。清单和简介都没有标签时把 Sline 清空，不留样例文案。
"""

import argparse
import json
import re
from html import escape, unescape
from pathlib import Path


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def summary_paragraphs(summary, tags):
    """读取历史简介正文，停在多件折扣或标签 HTML 之前。"""
    lines = []
    for raw in summary.splitlines():
        text = raw.strip()
        if text.startswith("<") or text == "## 多件折扣":
            break
        if text and not text.startswith("#"):
            lines.append(text)
    if tags and lines and lines[-1] == " · ".join(tags):
        lines.pop()
    return lines


def captured_texts(manifest):
    """采集到的全部正文段落，用于确认填进模板的文字来自原文而非改写。"""
    return {
        (item.get("text") or "").strip()
        for item in manifest.get("details", [])
        if item.get("type") == "text"
    }


def selected_detail_lines(manifest, positions):
    details = manifest.get("details") or []
    if len(set(positions)) != len(positions):
        raise ValueError("详情块位置重复，请每块只选择一次")
    lines = []
    for position in sorted(positions):
        if not 1 <= position <= len(details):
            raise ValueError(f"详情块位置 {position} 超出清单范围")
        block = details[position - 1]
        text = block.get("text") if isinstance(block, dict) and block.get("type") == "text" else None
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"详情块 {position} 没有可用的正文原文")
        lines.append(text)
    return lines


def intro_lines(manifest, summary, detail_blocks=()):
    """按页面顺序返回可追溯到采集清单的卖点。"""
    if manifest.get("intro"):
        if detail_blocks:
            raise ValueError("清单已有标题下简介，请使用该简介")
        lines = [
            entry["heading"] + (" " + entry["body"] if entry["body"] else "")
            for entry in manifest["intro"]
        ]
        captured_lines = manifest.get("audit", {}).get("introLines", lines)
        if lines != captured_lines or any(not line.strip() for line in lines):
            raise ValueError("简介缺失或与采集原文不一致，请核对源页面和清单")
        for entry in manifest["intro"]:
            if entry["heading"] not in summary or entry["body"] not in summary:
                raise ValueError("简介文件和清单的卖点不一致")
        return lines

    if detail_blocks:
        return selected_detail_lines(manifest, detail_blocks)

    lines = summary_paragraphs(summary, manifest.get("tags") or [])
    if not lines:
        raise ValueError("卖点缺失：请用 --detail-block 选择清单中的详情正文块")
    known = captured_texts(manifest)
    if not known:
        raise ValueError("卖点无法核对：清单缺少 details 采集原文")
    unknown = [line for line in lines if line not in known]
    if unknown:
        raise ValueError(f"卖点与采集原文不一致：{unknown[0][:60]}")
    return lines


def sline_block(manifest, summary):
    """返回标签 HTML；清单和简介都没有标签时返回空串，用于清空 Sline 区块。"""
    marker = '<div class="product-feature-tags">'
    if marker not in summary:
        if manifest.get("tags"):
            raise ValueError("清单有标签，但简介文件缺少标签容器和样式")
        return ""

    sline = summary[summary.index(marker):].strip()
    labels = [
        unescape(label.strip())
        for label in re.findall(r'<span class="product-feature-tag">([^<]*)</span>', sline)
    ]
    if labels != manifest.get("tags"):
        raise ValueError("Sline 标签与清单原文不一致")
    if not sline.endswith("</style>"):
        raise ValueError("Sline 样式缺失，简介文件末尾应有完整的 <style> 区块")
    return sline


def product_copy(manifest, summary, detail_blocks=()):
    lines = intro_lines(manifest, summary, detail_blocks)
    sline = sline_block(manifest, summary)
    escaped_lines = "<br><br>".join(escape(line, quote=False) for line in lines)
    intro = f'<p><span style="color: #e03e2d;"><strong>{escaped_lines}</strong></span></p>'
    tag_count = len(manifest.get("tags") or [])
    return intro, sline, len(lines), tag_count


def filled_template(template, intro, sline):
    info = template["sections"]["main-product-info"]["blocks"]["main"]["blocks"]["info"]
    blocks = info["blocks"]
    order = info["block_order"]
    between = order[order.index("title") + 1:order.index("price")]
    if [blocks[key]["type"] for key in between] != ["text", "custom-sline"]:
        raise ValueError("标题和价格之间的区块与已验证的 Fashion 结构不同，请核对实际主题")
    text = blocks[between[0]]["settings"]
    tags = blocks[between[1]]["settings"]
    if not {"text", "text_mobile"}.issubset(text) or "sline" not in tags:
        raise ValueError("对应区块缺少待填写字段，请核对实际主题")
    text["text"] = text["text_mobile"] = intro
    tags["sline"] = sline
    return template


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path, help="已核对的主题默认模板或最新专用模板")
    parser.add_argument("manifest", type=Path, help="已验收的竞品采集清单")
    parser.add_argument("summary", type=Path, help="商品名称_简介_标签.md")
    parser.add_argument("target", type=Path, help="新的暂存文件，或 --verify 时已回拉的文件")
    parser.add_argument("--detail-block", type=int, action="append", default=[],
                        metavar="位置", help="选择清单 details 中的正文块，从 1 计数，可重复传入")
    parser.add_argument("--verify", action="store_true", help="只校验回拉模板，不写文件")
    args = parser.parse_args()
    try:
        manifest = read_json(args.manifest)
        intro, sline, line_count, tag_count = product_copy(
            manifest, args.summary.read_text(encoding="utf-8"), args.detail_block
        )
        expected = filled_template(read_json(args.baseline), intro, sline)
        if args.verify:
            if read_json(args.target) != expected:
                raise ValueError("回读模板与预期不一致，请比对三个字段及其余模板设置")
        else:
            with args.target.open("x", encoding="utf-8") as stream:
                json.dump(expected, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"{error}\n")
    action = "核对" if args.verify else "写入"
    tail = "，Sline 已清空" if not sline else ""
    print(f"已{action} {line_count} 条卖点和 {tag_count} 个标签{tail}")


if __name__ == "__main__":
    main()
