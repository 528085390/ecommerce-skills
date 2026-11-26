#!/usr/bin/env python3
"""用本轮店铺的授权读取指定 SHOPLINE 商品。"""

import argparse
from http.client import HTTPException
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

from check_env import RejectRedirect


def read_product(store, product_id, token):
    query = urllib.parse.urlencode({"fields": "id,title,status"})
    url = f"https://{store}/admin/openapi/v20260901/products/{product_id}.json?{query}"
    request = urllib.request.Request(url, method="GET", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
    })
    try:
        with urllib.request.build_opener(RejectRedirect()).open(request, timeout=10) as response:
            if response.status != 200:
                raise RuntimeError(f"商品接口返回 HTTP {response.status}")
            result = json.load(response)
    except urllib.error.HTTPError as error:
        status = error.code
        error.close()
        if status in (401, 403):
            raise RuntimeError(f"HTTP {status}，请检查本轮店铺的 token 和 read_products 权限") from None
        if status == 404:
            raise RuntimeError("HTTP 404，请在本轮店铺后台核对商品 ID") from None
        raise RuntimeError(f"商品接口返回 HTTP {status}") from None
    except (OSError, ValueError, HTTPException):
        raise RuntimeError("商品接口请求失败或响应无法解析，请检查网络并核对后台") from None

    product = result.get("product") if isinstance(result, dict) else None
    if not isinstance(product, dict) or str(product.get("id")) != product_id:
        raise RuntimeError("响应中的商品 ID 与本轮请求不符，请在目标后台核对")
    if not isinstance(product.get("title"), str) or not product["title"].strip():
        raise RuntimeError("响应缺少商品标题，请在目标后台核对")
    return product


def main():
    parser = argparse.ArgumentParser(description="只读核对目标 SHOPLINE 店铺的商品 ID 和上架状态")
    parser.add_argument("--store", required=True, help="本轮店铺的后台域名，如 example.myshopline.com")
    parser.add_argument("--id", required=True, help="该店铺的商品 ID，可用第 4 步的 rel_id")
    args = parser.parse_args()
    store = args.store.strip().lower()
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.myshopline\.com", store):
        parser.error("请提供本轮店铺的完整 SHOPLINE 后台域名")
    if not re.fullmatch(r"[0-9]{1,64}", args.id):
        parser.error("请提供本轮店铺的数字商品 ID")

    token = os.environ.get("SHOPLINE_ACCESS_TOKEN", "").strip()
    if not token:
        print("缺少 SHOPLINE_ACCESS_TOKEN，请用已登录的目标后台按 ID 核对", file=sys.stderr)
        return 1
    try:
        product = read_product(store, args.id, token)
    except RuntimeError as error:
        print(f"SHOPLINE 商品核对：{error}", file=sys.stderr)
        return 1

    print(json.dumps({
        "store": store,
        "product_id": args.id,
        "title": product["title"],
        "status": product.get("status"),
        "admin_url": f"https://{store}/admin/products/{args.id}/edit",
    }, ensure_ascii=False, indent=2))
    if product.get("status") != "active":
        print("商品未确认已上架，请核对后台状态", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
