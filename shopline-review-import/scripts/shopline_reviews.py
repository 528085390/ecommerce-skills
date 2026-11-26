#!/usr/bin/env python3
"""Validate review data and create or verify a SHOPLINE import workbook."""

import argparse
import csv
from datetime import date
import io
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile


TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "line-importCommentList.xlsx"
COLUMNS = (
    "handle", "name", "email", "rating", "title", "content", "image_urls",
    "review_time", "helpful_times", "good_review", "visibility",
)
MAX_UPLOAD_BYTES = 40_000_000
XML_NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
MAIN_NS = XML_NS["s"]
ElementTree.register_namespace("", MAIN_NS)


def template_headers():
    with ZipFile(TEMPLATE) as workbook:
        strings = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
        sheet = ElementTree.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
    cells = sheet.findall("s:sheetData/s:row[@r='1']/s:c", XML_NS)
    headers = tuple(
        "".join(strings[int(cell.findtext("s:v", namespaces=XML_NS))].itertext())
        for cell in cells
    )
    if len(headers) != len(COLUMNS):
        raise ValueError("SHOPLINE 模板应包含 11 列。")
    return headers


def product_handle(value):
    if value.startswith(("https://", "http://")):
        url = urlsplit(value)
        match = re.fullmatch(r"/(?:preview/)?products/([^/]+)/?", url.path)
        if not url.hostname or not match:
            raise ValueError("商品链接须包含 /products/商品Handle。")
        value = unquote(match[1])
    if not value or re.search(r"[\s/?#\\%:]", value):
        raise ValueError("handle 必须是商品 Handle 或商品链接。")
    return value


def validate_row(row, target, today):
    if target and row["handle"] and product_handle(row["handle"]) != target:
        raise ValueError("行内 handle 与 --product 指定的商品不一致。")
    row["handle"] = target or product_handle(row["handle"])
    for field, max_length in (("name", 100), ("email", 50), ("title", 500), ("content", 1000)):
        if len(row[field]) > max_length:
            raise ValueError(f"{field} 最多 {max_length} 个字符。")
    if not row["name"].strip():
        raise ValueError("name 不能为空。")
    if not row["title"].strip() or not row["content"].strip():
        raise ValueError("title 和 content 不能为空。")
    if row["rating"] not in ("1", "2", "3", "4", "5"):
        raise ValueError("rating 必须是 1 到 5 的整数。")

    if not re.fullmatch(r"[0-9]{4}([/-])[0-9]{2}\1[0-9]{2}", row["review_time"]):
        raise ValueError("review_time 须使用 YYYY/MM/DD 或 YYYY-MM-DD。")
    try:
        review_date = date.fromisoformat(row["review_time"].replace("/", "-"))
    except ValueError as error:
        raise ValueError("review_time 不是有效日期。") from error
    if review_date > today:
        raise ValueError("review_time 不能晚于今天。")
    row["review_time"] = review_date.isoformat().replace("-", "/")

    image_urls = [line.strip() for line in row["image_urls"].splitlines() if line.strip()]
    if len(image_urls) > 9:
        raise ValueError("image_urls 每条评价最多 9 个图片链接，每行一个。")
    for image_url in image_urls:
        url = urlsplit(image_url)
        if url.scheme not in ("http", "https") or not url.hostname or re.search(r"\s", image_url):
            raise ValueError("image_urls 须使用 HTTP 或 HTTPS 链接。")
    row["image_urls"] = "\n".join(image_urls)

    helpful = row["helpful_times"]
    if helpful and (not re.fullmatch(r"[0-9]{1,6}", helpful) or int(helpful) > 100_000):
        raise ValueError("helpful_times 须留空或为 0 到 100000 的整数。")
    if row["good_review"] not in ("", "Yes"):
        raise ValueError("good_review 须留空或填 Yes。")
    row["visibility"] = row["visibility"] or "1"
    if row["visibility"] not in ("0", "1"):
        raise ValueError("visibility 须填 0（隐藏）或 1（公开）。")
    return tuple(row[column] for column in COLUMNS)


def prepare(source, headers, target, minimum_date=None, expected_count=None):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(headers)
    counts = {}
    identities = {}
    titles = {}
    contents = {}
    public_count = 0
    errors = []
    today = date.today()
    with source.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, strict=True)
        names = next(reader, [])
        aliases = dict(zip(headers, COLUMNS))
        columns = [aliases.get(name, name.strip().lower()) for name in names]
        if invalid := set(columns) - set(COLUMNS):
            raise ValueError(f"无法识别的列：{', '.join(sorted(invalid))}。")
        if len(columns) != len(set(columns)):
            raise ValueError("表头存在重复列。")
        required = {"name", "rating", "review_time"}
        if not target:
            required.add("handle")
        if missing := required - set(columns):
            raise ValueError(f"缺少必填列：{', '.join(sorted(missing))}。")

        line = reader.line_num + 1
        for values in reader:
            row_start = line
            line = reader.line_num + 1
            if not values or (len(values) == len(columns) and not any(value.strip() for value in values)):
                continue
            try:
                if len(values) != len(columns):
                    raise ValueError("数据列数与表头不一致。")
                row = dict.fromkeys(COLUMNS, "")
                row.update(zip(columns, values))
                for field in ("handle", "rating", "review_time", "helpful_times", "good_review", "visibility"):
                    row[field] = row[field].strip()
                values = validate_row(row, target, today)
                if minimum_date and date.fromisoformat(row["review_time"].replace("/", "-")) < minimum_date:
                    raise ValueError(f"review_time 不能早于 {minimum_date.isoformat()}。")
                for field, seen in (("title", titles), ("content", contents)):
                    normalized = " ".join(row[field].split()).casefold()
                    if normalized in seen:
                        raise ValueError(f"{field} 与第 {seen[normalized]} 行重复。")
                    seen[normalized] = row_start
                identity = tuple(row[key] for key in ("handle", "name", "email", "rating", "title", "content", "review_time"))
                if identity in identities:
                    raise ValueError(f"与第 {identities[identity]} 行的评价重复。")
                identities[identity] = row_start
                counts[row["handle"]] = counts.get(row["handle"], 0) + 1
                public_count += row["visibility"] == "1"
                writer.writerow(values)
            except ValueError as error:
                errors.append(f"第 {row_start} 行：{error}")
    if errors:
        raise ValueError("\n".join(errors))
    if not counts:
        raise ValueError("没有可导入的评价。")
    if expected_count is not None and sum(counts.values()) != expected_count:
        raise ValueError(f"评价条数应为 {expected_count}，实际为 {sum(counts.values())}。")
    payload = output.getvalue().encode("utf-8-sig")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise ValueError("导入文件超过 SHOPLINE 的 40 MB 限制，请拆分批次。")
    return payload, counts, public_count


def workbook_bytes(payload):
    records = list(csv.reader(io.StringIO(payload.decode("utf-8-sig"), newline="")))
    with ZipFile(TEMPLATE) as template:
        sheet = ElementTree.fromstring(template.read("xl/worksheets/sheet1.xml"))
        data = sheet.find(f"{{{MAIN_NS}}}sheetData")
        for row in list(data):
            if row.attrib.get("r") != "1":
                data.remove(row)
        for row_number, record in enumerate(records[1:], start=2):
            row = ElementTree.SubElement(data, f"{{{MAIN_NS}}}row", {"r": str(row_number), "spans": "1:11"})
            for index, value in enumerate(record):
                if value == "":
                    continue
                cell = ElementTree.SubElement(row, f"{{{MAIN_NS}}}c", {"r": f"{chr(65 + index)}{row_number}"})
                if index in (3, 8, 10):
                    ElementTree.SubElement(cell, f"{{{MAIN_NS}}}v").text = value
                else:
                    cell.set("t", "inlineStr")
                    inline = ElementTree.SubElement(cell, f"{{{MAIN_NS}}}is")
                    text = ElementTree.SubElement(inline, f"{{{MAIN_NS}}}t")
                    text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                    text.text = value
        sheet.find(f"{{{MAIN_NS}}}dimension").set("ref", f"A1:K{len(records)}")
        output = io.BytesIO()
        with ZipFile(output, "w") as workbook:
            for info in template.infolist():
                content = ElementTree.tostring(sheet, encoding="utf-8", xml_declaration=True) if info.filename == "xl/worksheets/sheet1.xml" else template.read(info.filename)
                workbook.writestr(info, content)
    return output.getvalue()


def verify_upload(source, target, minimum_date=None, expected_count=None):
    if source.suffix.lower() != ".xlsx" or source.stat().st_size > 1_000_000:
        raise ValueError("Peakoom 后台的导入工作簿须为小于或等于 1 MB 的 XLSX 文件。")
    with ZipFile(source) as workbook:
        sheets = ElementTree.fromstring(workbook.read("xl/workbook.xml"))
        if len(sheets.findall("s:sheets/s:sheet", XML_NS)) != 1:
            raise ValueError("导入工作簿须只有一个评价工作表。")
        strings = []
        if "xl/sharedStrings.xml" in workbook.namelist():
            strings = [
                "".join(node.text or "" for node in entry.findall(".//s:t", XML_NS))
                for entry in ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
            ]
        sheet = ElementTree.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
    rows = sheet.findall("s:sheetData/s:row", XML_NS)
    headers = template_headers()
    with TemporaryDirectory(prefix="shopline-upload-check-") as directory:
        source_csv = Path(directory) / "check.csv"
        with source_csv.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            for row in rows:
                number = row.attrib["r"]
                values = [""] * len(headers)
                for cell in row.findall("s:c", XML_NS):
                    address = cell.attrib["r"]
                    match = re.fullmatch(r"([A-K])" + number, address)
                    if not match or cell.find("s:f", XML_NS) is not None:
                        raise ValueError(f"{address} 超出模板范围或包含公式。")
                    value = cell.findtext("s:v", default="", namespaces=XML_NS)
                    if cell.get("t") == "s":
                        value = strings[int(value)]
                    if cell.get("t") == "inlineStr":
                        value = "".join(node.text or "" for node in cell.findall(".//s:t", XML_NS))
                    values[ord(match[1]) - ord("A")] = value
                if number == "1" and tuple(values) != headers:
                    raise ValueError("工作簿表头与 SHOPLINE 模板不一致。")
                if number != "1" and any(values):
                    if values[0] != target:
                        raise ValueError(f"第 {number} 行必须属于目标商品。")
                writer.writerow(values)
        _, counts, public_count = prepare(source_csv, headers, target, minimum_date, expected_count)
        if public_count != counts[target]:
            raise ValueError("上传工作簿包含隐藏评价；本流程要求全部公开。")
    return counts[target]


def main():
    parser = argparse.ArgumentParser(
        description="校验评价 CSV，可选生成 SHOPLINE 商品评价导入 XLSX 或 CSV。",
        epilog="简写表头：" + ", ".join(COLUMNS) + "。也接受 SHOPLINE 模板原表头。"
        "单商品可用 --product 代填 handle。visibility 留空时为公开。",
    )
    parser.add_argument("source", type=Path, help="UTF-8 编码的评价 CSV")
    parser.add_argument("--product", help="商品 Handle 或商品链接")
    parser.add_argument("--output", "-o", type=Path, help="导入 XLSX 或 CSV 路径。省略时只校验")
    parser.add_argument("--verify-upload", action="store_true", help="核验待上传的公开评价 XLSX")
    parser.add_argument("--prepare-upload", action="store_true", help="生成并回读待上传 XLSX，校验通过后才写入输出路径")
    parser.add_argument("--start-date", help="允许的最早评价日期，YYYY/MM/DD")
    parser.add_argument("--expected-count", type=int, help="本批应有的评价条数")
    args = parser.parse_args()
    try:
        minimum_date = date.fromisoformat(args.start_date.replace("/", "-")) if args.start_date else None
        if args.expected_count is not None and args.expected_count < 1:
            raise ValueError("--expected-count 必须大于 0。")
        target = product_handle(args.product.strip()) if args.product else None
        if args.prepare_upload and (
            args.verify_upload or not target or not args.output or args.output.suffix.lower() != ".xlsx"
        ):
            raise ValueError("--prepare-upload 须提供 --product 和 XLSX 输出路径，且不能与 --verify-upload 同用。")
        if args.verify_upload:
            if not target or args.output:
                raise ValueError("--verify-upload 须提供 --product，且无需输出路径。")
            print(json.dumps({"handle": target, "count": verify_upload(args.source, target, minimum_date, args.expected_count)}))
            return
        payload, counts, public_count = prepare(args.source, template_headers(), target, minimum_date, args.expected_count)
        if args.output:
            suffix = args.output.suffix.lower()
            if suffix == ".xlsx":
                payload = workbook_bytes(payload)
            elif suffix != ".csv":
                raise ValueError("输出文件扩展名必须是 .xlsx 或 .csv。")
            if len(payload) > MAX_UPLOAD_BYTES:
                raise ValueError("导入文件超过 SHOPLINE 的 40 MB 限制，请拆分批次。")
            if args.prepare_upload:
                with TemporaryDirectory(prefix="shopline-prepare-") as directory:
                    candidate = Path(directory) / "candidate.xlsx"
                    candidate.write_bytes(payload)
                    verified_count = verify_upload(candidate, target, minimum_date, args.expected_count)
            with args.output.open("xb") as stream:
                stream.write(payload)
            if args.prepare_upload:
                print(json.dumps({"handle": target, "count": verified_count, "file": str(args.output.resolve())}))
                return
    except (OSError, ValueError, csv.Error, BadZipFile, KeyError, ElementTree.ParseError) as error:
        parser.exit(1, f"处理失败：{error}\n")

    total = sum(counts.values())
    print(f"校验通过：{len(counts)} 个商品，{total} 条评价。公开 {public_count} 条，隐藏 {total - public_count} 条。")
    for handle, count in counts.items():
        print(f"  {handle}  {count} 条")
    if args.output:
        print(f"导入文件：{args.output.resolve()}")


if __name__ == "__main__":
    main()
