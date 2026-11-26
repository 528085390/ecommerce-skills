#!/usr/bin/env python3
"""Resolve Shopify products and create/check/publish Judge.me reviews.

The private API token is read from a local file and is never printed.
"""

import argparse
import csv
import json
import re
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlencode, urlsplit
from urllib.request import Request, urlopen


API_BASE = "https://api.judge.me/api/v1"


def die(message):
    raise SystemExit(f"ERROR: {message}")


def print_json(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def load_token(path):
    p = Path(path).expanduser()
    if not p.is_file():
        die(f"token 文件不存在：{p}")
    text = p.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"JUDGEME_TOKEN\s*=\s*[\"']?([A-Za-z0-9_-]{10,})", text)
    if match:
        return match.group(1)
    candidates = re.findall(r"[A-Za-z0-9_-]{20,}", text)
    if not candidates:
        die(f"未在 token 文件中找到可用字符串：{p}")
    return max(candidates, key=len)


def derive_shop_domain(value):
    value = value.strip()
    if value.startswith(("http://", "https://")):
        parts = urlsplit(value)
        host = (parts.hostname or "").lower()
        match = re.search(r"/store/([^/]+)", parts.path)
        if match:
            return f"{match.group(1)}.myshopify.com"
        if host.endswith(".myshopify.com"):
            return host
        if "shopifypreview.com" in host:
            die("预览店域名无法用于 Judge.me 核对，请提供 Shopify 后台链接（/store/<handle>/）。")
        die(f"无法从链接推导 shop domain：{value}")
    if value.endswith(".myshopify.com"):
        return value
    if re.fullmatch(r"[a-z0-9][a-z0-9-]*", value):
        return f"{value}.myshopify.com"
    die(f"无法识别店铺标识：{value}")


def extract_handle(url):
    if not url:
        return ""
    parts = urlsplit(url)
    match = re.match(r"^/(?:preview/)?products/([^/]+)/?$", parts.path)
    return unquote(match.group(1)) if match else ""


def keyword_from_handle(handle):
    cleaned = re.sub(r"[^0-9A-Za-z]+", "-", handle or "").strip("-")
    parts = [part for part in cleaned.split("-") if part]
    if len(parts) >= 6:
        return "-".join(parts[3:6])
    return "-".join(parts[:4])


def extract_judgeme_product_id(value):
    """Extract a Judge.me internal product ID from an admin URL or a bare number."""
    if not value:
        return None
    value = str(value).strip()
    if value.isdigit():
        return int(value)
    parts = urlsplit(value)
    match = re.search(r"/apps/judgeme/settings/reviews/products/(\d+)", parts.path)
    if match:
        return int(match.group(1))
    for segment in reversed([s for s in parts.path.split("/") if s]):
        if segment.isdigit():
            return int(segment)
    return None


def gql_escape(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def public_product(shop_domain, handle):
    """Read a product from Shopify's public product JSON, without CLI or auth."""
    if not handle:
        return None
    url = f"https://{shop_domain}/products/{quote(handle, safe='')}.js"
    data = None

    # curl handles Shopify's redirects and TLS more reliably across Python versions.
    try:
        proc = subprocess.run(
            ["curl", "-sS", "-L", "-m", "20", "-A", "Mozilla/5.0", url],
            capture_output=True, text=True, timeout=25,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            data = json.loads(proc.stdout)
    except (FileNotFoundError, subprocess.SubprocessError, json.JSONDecodeError, ValueError):
        data = None

    if data is None:
        request = Request(url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
        for attempt in range(3):
            try:
                with urlopen(request, timeout=20) as response:
                    data = json.loads(response.read().decode("utf-8", "replace"))
                break
            except HTTPError as error:
                if error.code == 429 and attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                return None
            except (URLError, json.JSONDecodeError, ValueError):
                return None
        else:
            return None

    product = data.get("product", data)
    if not product.get("id") or not product.get("title"):
        return None
    result = simplify_product(product)
    result.update({
        "description_html": product.get("description") or "",
        "images": product.get("images") or [],
        "options": product.get("options") or [],
        "source_url": url,
    })
    return result


def api_call(method, path, *, token=None, shop_domain=None, params=None, payload=None):
    all_params = {}
    if shop_domain:
        all_params["shop_domain"] = shop_domain
    if params:
        all_params.update(params)
    url = API_BASE + path
    if all_params:
        url += "?" + urlencode(all_params)

    headers = {"Accept": "application/json", "User-Agent": "workbuddy-judgeme-review-import"}
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["X-Api-Token"] = token

    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8", "replace")
            status = response.status
    except HTTPError as error:
        raw = error.read().decode("utf-8", "replace")
        status = error.code
        die(f"Judge.me API HTTP {status}: {raw[:500]}")
    except URLError as error:
        die(f"无法连接 Judge.me API：{error}")

    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        parsed = {"raw": raw[:1000]}
    return status, parsed


def find_shopify_cli():
    """Return a callable CLI path: PATH first, then the stable user-level wrapper."""
    from shutil import which
    in_path = which("shopify")
    if in_path:
        return in_path
    wrapper = Path.home() / ".local/bin/shopify"
    if wrapper.is_file():
        return str(wrapper)
    return None


def shopify_products(store_domain, handle=None, keyword=None):
    queries = []
    if handle:
        queries.append(
            'query { products(first: 10, query: "handle:'
            + gql_escape(handle)
            + '") { nodes { id title handle status variants(first: 5) { nodes { id sku title } } } } }'
        )
    if keyword:
        queries.append(
            'query { products(first: 10, query: "'
            + gql_escape(keyword)
            + '") { nodes { id title handle status variants(first: 5) { nodes { id sku title } } } } }'
        )
    if not queries:
        die("需要 --handle、--product-url 或 --keyword 之一来定位商品。")

    cli = find_shopify_cli()
    if not cli:
        die("未找到 shopify CLI。请安装 Shopify CLI，或创建 ~/.local/bin/shopify 包装脚本。")

    for query in queries:
        command = [cli, "store", "execute", "--store", store_domain, "--query", query]
        try:
            proc = subprocess.run(command, capture_output=True, text=True, timeout=90)
        except FileNotFoundError:
            die("未找到 shopify CLI，请先安装并登录 Shopify CLI。")
        except subprocess.TimeoutExpired:
            die("Shopify CLI 查询超时。")
        if proc.returncode != 0:
            die(f"Shopify CLI 查询失败：{(proc.stderr or proc.stdout)[:800]}")
        output = proc.stdout
        start = output.find("\n{")
        if start < 0:
            start = output.find("{")
        if start < 0:
            die(f"无法解析 Shopify CLI 输出：{output[:500]}")
        try:
            data = json.loads(output[start:])
        except json.JSONDecodeError:
            die(f"无法解析 Shopify CLI JSON：{output[start:start+500]}")
        nodes = (data.get("products") or {}).get("nodes") or []
        if nodes:
            return nodes
    return []


def simplify_product(product):
    result = {
        "shopify_product_id": int(str(product.get("id", "")).rstrip("/").split("/")[-1]),
        "title": product.get("title"),
        "handle": product.get("handle"),
        "status": product.get("status"),
        "variants": [],
    }
    variants = product.get("variants") or []
    nodes = variants.get("nodes", []) if isinstance(variants, dict) else variants
    for variant in nodes:
        result["variants"].append({
            "id": variant.get("id"),
            "sku": variant.get("sku"),
            "title": variant.get("title"),
        })
    return result


def validate_import_row(raw, row, line, args, seen):
    if None in raw or any(value is None for value in raw.values()):
        die(f"CSV 第 {line} 行列数与表头不一致。")
    if raw.get("product_handle", "").strip() != args.product_handle:
        die(f"CSV 第 {line} 行 product_handle 与本批目标不一致。")
    product_id = raw.get("product_id", "").strip()
    if product_id and product_id != str(args.product_id):
        die(f"CSV 第 {line} 行 product_id 与本批目标不一致。")
    if raw.get("curated", "").strip() != args.curated:
        die(f"CSV 第 {line} 行 curated 与本批可见性不一致。")

    review_date = raw.get("review_date", "").strip()
    try:
        parsed_date = datetime.strptime(review_date, "%d/%m/%Y").date()
    except ValueError:
        die(f"CSV 第 {line} 行 review_date 须为有效的 DD/MM/YYYY 日期。")
    if parsed_date > date.today():
        die(f"CSV 第 {line} 行 review_date 不能是未来日期。")

    for field in ("title", "body"):
        value = " ".join(row[field].split()).casefold()
        if not value:
            die(f"CSV 第 {line} 行 {field} 不能为空。")
        if value in seen[field]:
            die(f"CSV 第 {line} 行的 {field} 与第 {seen[field][value]} 行重复。")
        seen[field][value] = line


def read_review_csv(path, *, allow_email=False, import_args=None):
    p = Path(path).expanduser()
    if not p.is_file():
        die(f"评价 CSV 不存在：{p}")
    rows = []
    seen = {"title": {}, "body": {}}
    with p.open(encoding="utf-8-sig", newline="") as stream:
        if import_args is not None and stream.buffer.peek(3).startswith(b"\xef\xbb\xbf"):
            die("评价 CSV 必须使用无 BOM 的 UTF-8 编码。")
        reader = csv.DictReader(stream, strict=True)
        if reader.fieldnames and len(set(reader.fieldnames)) != len(reader.fieldnames):
            die("评价 CSV 有重复列名，请修正后再校验。")
        for index, raw in enumerate(reader, start=2):
            def get(*names):
                for name in names:
                    value = raw.get(name)
                    if value is not None and str(value).strip():
                        return str(value).strip()
                return ""

            name = get("reviewer_name", "name")
            email = get("reviewer_email", "email")
            if not allow_email and any(
                str(value or "").strip()
                for column, value in raw.items()
                if column and column.strip().lower() in {"reviewer_email", "email"}
            ):
                die(f"CSV 第 {index} 行邮箱必须留空。仅在用户明确允许填写邮箱时使用 --allow-email。")
            rating_text = get("rating")
            if not rating_text.isdigit() or not 1 <= int(rating_text) <= 5:
                die(f"CSV 第 {index} 行 rating 必须是 1 到 5 的整数。")
            body = get("body", "review", "content")
            if not body:
                die(f"CSV 第 {index} 行 body 不能为空。")
            if len(body) > 1000:
                die(f"CSV 第 {index} 行 body 超过 1000 字符。")
            pictures_text = get("picture_urls", "pictures")
            pictures = [line.strip() for line in re.split(r"[\n;|]", pictures_text) if line.strip()]
            rows.append({
                "title": get("title"),
                "body": body,
                "rating": int(rating_text),
                "reviewer_name": name,
                "reviewer_email": email,
                "picture_urls": pictures,
            })
            if import_args is not None:
                validate_import_row(raw, rows[-1], index, import_args, seen)
    if not rows:
        die("评价 CSV 没有数据行。")
    return rows


def build_payloads(shop_domain, product_id, rows):
    payloads = []
    for row in rows:
        payload = {
            "shop_domain": shop_domain,
            "platform": "shopify",
            "id": int(product_id),
            "name": row["reviewer_name"],
            "email": row["reviewer_email"],
            "rating": row["rating"],
            "body": row["body"],
        }
        if row["title"]:
            payload["title"] = row["title"]
        if row["picture_urls"]:
            payload["picture_urls"] = row["picture_urls"]
        payloads.append(payload)
    return payloads


def summarize_review(review):
    keys = (
        "id", "title", "rating", "curated", "hidden", "verified",
        "created_at", "updated_at", "product_external_id", "product_title",
    )
    return {key: review.get(key) for key in keys if key in review}


def command_resolve(args):
    store_domain = derive_shop_domain(args.store)
    handle = args.handle or extract_handle(args.product_url)
    keyword = args.keyword or (keyword_from_handle(handle) if handle else "")
    if not handle and not keyword:
        die("请提供 --product-url、--handle 或 --keyword。")
    source = "public_product_json"
    products = []
    if handle:
        public = public_product(store_domain, handle)
        if public:
            products = [public]
    if not products:
        source = "shopify_cli"
        products = [
            simplify_product(product)
            for product in shopify_products(store_domain, handle=handle, keyword=keyword)
        ]
    if not products:
        die("未在目标店铺找到匹配商品，请核对店铺、handle 或关键词。")
    print_json({
        "shop_domain": store_domain,
        "source": source,
        "searched_handle": handle,
        "searched_keyword": keyword,
        "products": products,
    })


def command_resolve_judgeme(args):
    store_domain = derive_shop_domain(args.store)
    token = load_token(args.token_file)
    internal_id = args.judgeme_product_id or extract_judgeme_product_id(args.judgeme_url)
    if not internal_id:
        die("无法从 Judge.me 后台链接提取内部商品 ID，请检查 --judgeme-url。")
    _, data = api_call(
        "GET", f"/products/{internal_id}", token=token, shop_domain=store_domain
    )
    product = data.get("product", data) if isinstance(data, dict) else {}
    print_json({
        "shop_domain": store_domain,
        "judgeme_internal_id": internal_id,
        "shopify_product_id": product.get("external_id"),
        "title": product.get("title"),
        "handle": product.get("handle"),
        "vendor": product.get("vendor"),
    })


def command_validate_csv(args):
    require_import_checks = any(value is not None for value in (args.product_handle, args.product_id, args.expected_count, args.curated))
    if require_import_checks and not (args.product_handle and args.expected_count and args.expected_count > 0 and args.curated):
        die("上传前校验须提供 --product-handle、正整数 --expected-count 和 --curated。")
    rows = read_review_csv(args.csv, allow_email=args.allow_email, import_args=args if require_import_checks else None)
    if require_import_checks and len(rows) != args.expected_count:
        die(f"评价条数应为 {args.expected_count}，实际为 {len(rows)}。")
    print_json({"count": len(rows), "nonempty_email_count": sum(bool(row["reviewer_email"]) for row in rows)})


def command_create(args):
    shop_domain = derive_shop_domain(args.shop_domain)
    rows = read_review_csv(args.csv, allow_email=args.allow_email)
    payloads = build_payloads(shop_domain, args.product_id, rows)
    if args.dry_run:
        print_json({"shop_domain": shop_domain, "product_id": args.product_id, "payloads": payloads})
        return
    results = []
    for payload in payloads:
        status, response = api_call("POST", "/reviews", payload=payload)
        results.append({
            "title": payload.get("title", ""),
            "email": payload.get("email"),
            "rating": payload.get("rating"),
            "http_status": status,
            "response": response,
        })
    print_json({"shop_domain": shop_domain, "product_id": args.product_id, "results": results})


def command_check(args):
    if not args.review_id and not args.product_id:
        die("请提供 --review-id 或 --product-id。")
    token = load_token(args.token_file)
    shop_domain = derive_shop_domain(args.shop_domain)

    if args.review_id:
        _, data = api_call(
            "GET", f"/reviews/{args.review_id}", token=token, shop_domain=shop_domain
        )
        review = data.get("review", data)
        reviews = [review]
    else:
        _, product_data = api_call(
            "GET", "/products", token=token, shop_domain=shop_domain,
            params={"external_id": args.product_id},
        )
        products = product_data.get("products") or []
        target = next(
            (p for p in products if str(p.get("external_id")) == str(args.product_id)), None
        )
        if not target:
            die(f"Judge.me 中未找到 Shopify 商品 ID {args.product_id} 对应的商品。")
        _, review_data = api_call(
            "GET", "/reviews", token=token, shop_domain=shop_domain,
            params={"product_id": target["id"], "per_page": args.per_page},
        )
        reviews = review_data.get("reviews") or []
        if args.title:
            reviews = [r for r in reviews if args.title.lower() in (r.get("title") or "").lower()]

    print_json({
        "shop_domain": shop_domain,
        "judgeme_product_id": target["id"] if not args.review_id else None,
        "count": len(reviews),
        "reviews": [summarize_review(review) for review in reviews],
    })


def command_publish(args):
    token = load_token(args.token_file)
    shop_domain = derive_shop_domain(args.shop_domain)
    _, response = api_call(
        "PUT", f"/reviews/{args.review_id}", token=token, shop_domain=shop_domain,
        payload={"curated": args.state},
    )
    _, verify = api_call(
        "GET", f"/reviews/{args.review_id}", token=token, shop_domain=shop_domain
    )
    review = verify.get("review", verify)
    print_json({
        "shop_domain": shop_domain,
        "update_response": response,
        "review": summarize_review(review),
    })


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    resolve = subparsers.add_parser("resolve", help="用 Shopify CLI 解析商品 ID")
    resolve.add_argument("--store", required=True, help="后台链接或 <handle>.myshopify.com")
    resolve.add_argument("--product-url", help="商品前台或预览链接")
    resolve.add_argument("--handle", help="商品 handle；提供时优先使用")
    resolve.add_argument("--keyword", help="搜索关键词")
    resolve.set_defaults(func=command_resolve)

    resolve_j = subparsers.add_parser(
        "resolve-judgeme", help="从 Judge.me 后台商品链接解析 Shopify 商品 ID"
    )
    resolve_j.add_argument("--store", required=True, help="后台链接或 <handle>.myshopify.com")
    resolve_j.add_argument("--token-file", required=True, help="本地 private token 文件路径")
    resolve_j.add_argument("--judgeme-url", help="Judge.me 后台商品评价设置链接")
    resolve_j.add_argument("--judgeme-product-id", type=int, help="Judge.me 内部商品 ID")
    resolve_j.set_defaults(func=command_resolve_judgeme)

    validate_csv = subparsers.add_parser("validate-csv", help="在本地校验评价 CSV")
    validate_csv.add_argument("--csv", required=True, help="评价 CSV 路径")
    validate_csv.add_argument("--allow-email", action="store_true", help="仅在用户明确允许时接受非空邮箱")
    validate_csv.add_argument("--product-handle", help="上传前校验的目标商品句柄")
    validate_csv.add_argument("--product-id", type=int, help="CSV 填写商品 ID 时用于校验")
    validate_csv.add_argument("--expected-count", type=int, help="本批预期评价条数")
    validate_csv.add_argument("--curated", choices=("ok", "spam", "not-yet"), help="本批预期可见性")
    validate_csv.set_defaults(func=command_validate_csv)

    create = subparsers.add_parser("create", help="创建 Judge.me 评价")
    create.add_argument("--shop-domain", required=True, help="shop domain 或后台链接")
    create.add_argument("--product-id", required=True, type=int, help="Shopify 商品数字 ID")
    create.add_argument("--csv", required=True, help="评价 CSV 路径")
    create.add_argument("--dry-run", action="store_true", help="只打印 payload，不提交")
    create.add_argument("--allow-email", action="store_true", help="仅在用户明确允许时接受非空邮箱")
    create.set_defaults(func=command_create)

    check = subparsers.add_parser("check", help="只读核对评价状态")
    check.add_argument("--shop-domain", required=True)
    check.add_argument("--token-file", required=True, help="本地 private token 文件路径")
    check.add_argument("--review-id", type=int, help="Judge.me 评价内部 ID")
    check.add_argument("--product-id", type=int, help="Shopify 商品数字 ID")
    check.add_argument("--title", help="按标题关键词过滤")
    check.add_argument("--per-page", type=int, default=50)
    check.set_defaults(func=command_check)

    publish = subparsers.add_parser("publish", help="发布或隐藏评价")
    publish.add_argument("--shop-domain", required=True)
    publish.add_argument("--token-file", required=True)
    publish.add_argument("--review-id", required=True, type=int)
    publish.add_argument("--state", choices=("ok", "spam"), default="ok", help="ok=发布, spam=隐藏")
    publish.set_defaults(func=command_publish)

    return parser


def main():
    args = build_parser().parse_args()
    try:
        args.func(args)
    except (csv.Error, UnicodeDecodeError) as error:
        die(f"无法读取评价 CSV：{error}")


if __name__ == "__main__":
    main()
