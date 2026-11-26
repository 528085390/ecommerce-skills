#!/usr/bin/env python3
"""Finalize the local files for an already verified product decoration."""

import argparse
import json
import re
import tempfile
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit


SUMMARY = "商品装修说明.md"
REQUIRED_FILES = (
    "商品名称_简介_标签.md",
    "商品详情_打开后全选复制.html",
    "单品采集结果.csv",
    "1688搜图结果.json",
    "1688搜图结果.csv",
)
REQUIRED_STEPS = ("1", "2", "3", "4", "5", "5a", "6", "7", "8", "9")
STEP_ROW = re.compile(r"^\|[ \t]*((\d+a?)\.[ \t]+[^|\n]+)\|([^|\n]+)\|([^\n]+)\|[ \t]*$", re.M)
COMPLETE = re.compile(r"^(?:已完成|✓|✅)(?:\s+(\d{4}-\d{2}-\d{2}))?$")
IMAGE_TYPES = {".jpg", ".png", ".webp", ".gif", ".svg"}


def is_http_url(value):
    if not isinstance(value, str) or not value or any(
        character.isspace() or character in "<>" for character in value
    ):
        return False
    url = urlsplit(value)
    return url.scheme in {"http", "https"} and bool(url.hostname)


def verify_media(directory, expected_count):
    if not directory.is_dir():
        raise ValueError(f"缺少素材目录 {directory.name}")
    media = [
        file for file in directory.iterdir()
        if file.is_file() and file.stem.isdecimal() and file.suffix != ".download" and file.stat().st_size
    ]
    if sorted(int(file.stem) for file in media) != list(range(1, expected_count + 1)):
        raise ValueError(f"{directory.name}的编号或数量与采集清单不符（应有 {expected_count} 个）")
    return media


def update_summary(summary, source_url, previews, completed_on):
    source_line = re.search(r"^- \[竞品商品页\]\((.+)\)[ \t]*$", summary, re.M)
    if not source_line or source_line[1] != source_url:
        raise ValueError("说明中的竞品商品页与采集清单的 source_url 不一致")

    rows = {}
    for row in STEP_ROW.finditer(summary):
        number = row[2]
        if number in rows:
            raise ValueError(f"说明中有重复的第 {number} 步")
        rows[number] = row
    pending = [
        step for step in REQUIRED_STEPS
        if step not in rows or not COMPLETE.fullmatch(rows[step][3].strip().strip("*"))
    ]
    if pending:
        raise ValueError(f"说明中尚未验收的步骤：{', '.join(pending)}")
    final_row = rows.get("10")
    if not final_row:
        raise ValueError("说明中缺少第 10 步进度行")

    existing_status = COMPLETE.fullmatch(final_row[3].strip().strip("*"))
    if existing_status:
        completed_on = existing_status[1] or final_row[4].strip()
        date.fromisoformat(completed_on)
    else:
        final_line = f"| {final_row[1].strip()} | 已完成 | {completed_on} |"
        summary = summary[:final_row.start()] + final_line + summary[final_row.end():]

    summary, count = re.subn(
        r"^- 当前进度：[^\n]*",
        f"- 当前进度：**全部完成**（第 10 步 {completed_on} 验收通过）",
        summary, flags=re.M,
    )
    if count != 1:
        raise ValueError("说明中应有且只有一行「当前进度」")

    preview_block = "- 我方商品预览："
    if len(previews) == 1:
        preview_block += previews[0][1]
    else:
        preview_block += "".join(f"\n  - {store}：{url}" for store, url in previews)
    preview_pattern = r"^- 我方商品预览：[^\n]*(?:\n  - [^：\n]+：https?://[^\n]+)*"
    previews_before = re.search(preview_pattern, summary, re.M)
    saved_stores = set()
    if previews_before:
        saved_stores = {
            line[4:].partition("：")[0].strip().casefold()
            for line in previews_before[0].splitlines()[1:]
        }
    if saved_stores - {store.strip().casefold() for store, _ in previews}:
        raise ValueError("本轮预览参数遗漏了说明里已记录的店铺")
    summary, count = re.subn(preview_pattern, lambda match: preview_block, summary, flags=re.M)
    if count != 1:
        raise ValueError("说明中应有且只有一个「我方商品预览」")
    return summary, completed_on


def replace_text(path, original, updated):
    if original == updated:
        return
    if path.read_text(encoding="utf-8") != original:
        raise ValueError(f"{path.name} 自检查后已变化，请读取最新版本再续跑")
    temp = tempfile.NamedTemporaryFile(
        dir=path.parent, prefix=".decoration-", delete=False, mode="w", encoding="utf-8"
    )
    temp_path = Path(temp.name)
    try:
        with temp:
            temp.write(updated)
        temp_path.chmod(path.stat().st_mode & 0o777)
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)


def finalize(args):
    requested = args.directory.absolute()
    if requested.name.startswith("1-1-"):
        raise ValueError("目录已重复添加 1-，请先核对实际目录")
    original_dir = requested.with_name(requested.name.removeprefix("1-"))
    final_dir = original_dir.with_name(f"1-{original_dir.name}")
    if any(directory.is_symlink() for directory in (original_dir, final_dir)):
        raise ValueError("请传入实际商品目录")
    if original_dir.exists() and final_dir.exists():
        raise ValueError("带前缀和不带前缀的目录均存在，请先核对来源")
    current_dir = final_dir if final_dir.exists() else original_dir
    if not current_dir.is_dir():
        raise ValueError(f"找不到实际商品目录 {current_dir}")

    manifest_path = args.manifest.absolute()
    if current_dir == final_dir and manifest_path.is_relative_to(original_dir):
        manifest_path = final_dir / manifest_path.relative_to(original_dir)
    manifest_text = manifest_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)
    if not isinstance(manifest, dict) or not is_http_url(manifest.get("source_url")):
        raise ValueError("采集清单缺少有效的 source_url")
    folder = manifest.get("folder_name", manifest.get("folder"))
    if folder not in {original_dir.name, final_dir.name}:
        raise ValueError("采集清单中的目录名与本轮目录不一致")
    gallery = manifest.get("gallery")
    details = manifest.get("details")
    if not isinstance(gallery, list) or not isinstance(details, list) or any(
        not isinstance(item, dict) for item in details
    ):
        raise ValueError("采集清单缺少有效的 gallery 或 details 数组")

    for name in REQUIRED_FILES:
        file = current_dir / name
        if not file.is_file() or not file.stat().st_size:
            raise ValueError(f"交付目录中缺少有效文件 {name}")
    gallery_files = verify_media(current_dir / "轮播图", len(gallery))
    detail_count = sum(item.get("type") in {"image", "gif", "video"} for item in details)
    verify_media(current_dir / "详情图", detail_count)
    for file in sorted(gallery_files, key=lambda file: int(file.stem)):
        if file.suffix in IMAGE_TYPES:
            cover = current_dir / f"封面{file.suffix}"
            if not cover.is_file() or not cover.stat().st_size:
                raise ValueError(f"交付目录中缺少有效文件 {cover.name}")
            break

    preview_stores = set()
    for store, url in args.preview:
        if not store.strip() or not store.isprintable() or "：" in store or not is_http_url(url):
            raise ValueError("请提供店铺名及已核对的 HTTP(S) 预览地址")
        if store.strip().casefold() in preview_stores:
            raise ValueError(f"店铺 {store} 有重复的预览地址")
        preview_stores.add(store.strip().casefold())

    summary_path = current_dir / SUMMARY
    summary_text = summary_path.read_text(encoding="utf-8")
    updated_summary, completed_on = update_summary(
        summary_text, manifest["source_url"], args.preview, args.date.isoformat()
    )
    updated_manifest = manifest_text
    if manifest.get("folder_name") != final_dir.name:
        manifest["folder_name"] = final_dir.name
        updated_manifest = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"

    if args.apply:
        if current_dir != final_dir:
            current_dir.rename(final_dir)
            if manifest_path.is_relative_to(current_dir):
                manifest_path = final_dir / manifest_path.relative_to(current_dir)
        replace_text(manifest_path, manifest_text, updated_manifest)
        replace_text(final_dir / SUMMARY, summary_text, updated_summary)

    print(json.dumps({
        "status": "completed" if args.apply else "ready",
        "directory": str(final_dir),
        "summary": str(final_dir / SUMMARY),
        "completed_on": completed_on,
        "previews": dict(args.preview),
    }, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="本轮商品目录")
    parser.add_argument("--manifest", type=Path, required=True, help="本轮已验收的采集清单")
    parser.add_argument("--preview", nargs=2, action="append", required=True, metavar=("店铺", "网址"))
    parser.add_argument("--date", type=date.fromisoformat, required=True, help="当地验收日期 YYYY-MM-DD")
    parser.add_argument("--apply", action="store_true", help="实际归档，省略此参数仅检查")
    args = parser.parse_args()
    try:
        finalize(args)
    except (OSError, ValueError) as error:
        parser.exit(1, f"交付归档失败：{error}\n")


if __name__ == "__main__":
    main()
