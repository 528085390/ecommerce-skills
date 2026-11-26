#!/usr/bin/env python3
"""
在 Phalanx 补充采购与 ERP 信息
调用 GET /api/oally/product/get 获取商品详情，
修改采购链接、成本价、重量、供应商、海关编码、敏感属性，
并调用 PUT /api/oally/product/update 完成更新。
"""

import argparse
from decimal import Decimal
from http.client import HTTPException
import json
import math
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

from check_env import RejectRedirect

API_BASE = "https://portal.ecom.umcasual.cn/api"
TOKEN_FILE = "/tmp/phalanx_token.txt"


def get_token():
    token = os.environ.get("PHALANX_TOKEN", "").strip()
    if token:
        return token
    try:
        token = Path(TOKEN_FILE).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        token = ""
    if token:
        return token
    raise RuntimeError("未找到 Phalanx 会话 token，请确保 /tmp/phalanx_token.txt 存在或设置 PHALANX_TOKEN 环境变量")


def phalanx_request(path, token, product=None):
    headers = {"token": token, "Accept": "application/json"}
    body = None
    method = "GET"
    if product is not None:
        method = "PUT"
        headers["Content-Type"] = "application/json"
        body = json.dumps(product, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(API_BASE + path, method=method, headers=headers, data=body)
    try:
        with urllib.request.build_opener(RejectRedirect()).open(request, timeout=12) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        status = error.code
        error.close()
        if status == 401:
            raise RuntimeError("Phalanx 会话未通过，请用本轮账号重新登录") from None
        if status == 403:
            raise RuntimeError("Phalanx 拒绝访问，请核对本轮账号权限") from None
        if method == "PUT" and status >= 500:
            raise RuntimeError(f"Phalanx PUT 返回 HTTP {status}，更新结果待确认") from None
        raise RuntimeError(f"Phalanx {method} 返回 HTTP {status}") from None
    except (OSError, ValueError, HTTPException):
        if method == "PUT":
            raise RuntimeError("Phalanx PUT 未收到有效响应，更新结果待确认") from None
        raise RuntimeError(f"Phalanx {method} 请求失败或响应无法解析") from None

    code = str(result.get("code")) if isinstance(result, dict) else ""
    if code in {"10000", "401"}:
        raise RuntimeError("Phalanx 会话未通过，请用本轮账号重新登录")
    if code == "403":
        raise RuntimeError("Phalanx 拒绝访问，请核对本轮账号权限")
    if code != "200":
        raise RuntimeError(f"Phalanx {method} 未返回业务成功")
    return result.get("data")


def fetch_product(product_id, token):
    data = phalanx_request(f"/oally/product/get?id={product_id}", token)
    if not isinstance(data, dict) or str(data.get("id")) != str(product_id):
        raise RuntimeError("商品详情返回的 ID 与请求不一致")
    return data


def find_product_id_by_spu(spu, token):
    matches = []
    page = 1
    limit = 50
    while True:
        query = urllib.parse.urlencode({"page": page, "limit": limit, "spu_like": spu})
        data = phalanx_request(f"/oally/v2/product/list?{query}", token)
        items = data.get("list") if isinstance(data, dict) else None
        total = data.get("total") if isinstance(data, dict) else None
        if not isinstance(items, list) or not isinstance(total, int) or total < 0:
            raise RuntimeError("无法核对商品列表的分页数据")
        if any(not isinstance(item, dict) for item in items):
            raise RuntimeError("商品列表包含无法核对的商品记录")
        matches.extend(item.get("id") for item in items if item.get("sku") == spu)
        if len(matches) > 1:
            raise RuntimeError(f"SPU {spu} 对应多件商品")
        if page * limit >= total:
            break
        if len(items) != limit:
            raise RuntimeError("商品列表分页结果不完整，无法确认 SPU 唯一性")
        page += 1
    if len(matches) == 1 and re.fullmatch(r"[1-9][0-9]*", str(matches[0])):
        return int(matches[0])
    raise RuntimeError(f"未找到 SPU {spu} 的有效商品 ID")


def apply_erp_fields(product, args):
    common = {
        "purchase_link": args.link,
        "cost_price": args.cost,
        "weight": args.weight,
        "weight_unit": "g",
        "supplier_code": args.supplier_code,
        "supplier": args.supplier,
        "express_type": args.express_type,
    }
    nested = {
        "hs_code": args.hs_code,
        "default_supplier_code": args.supplier_code,
        "pd_weight": f"{Decimal(str(args.weight)) / 1000:.6f}",
        "pd_target_amount": f"{Decimal(str(args.cost)):.6f}",
    }
    variants = product.get("variants")
    if not isinstance(variants, list):
        raise RuntimeError("商品详情缺少规格列表")
    product.update(common, hs_code=args.hs_code)
    for index, variant in enumerate(variants, 1):
        erp = variant.get("erp_product_variant") if isinstance(variant, dict) else None
        if not isinstance(erp, dict):
            raise RuntimeError(f"第 {index} 个 SKU 缺少 PUT 所需的 ERP 对象")
        variant.update(common)
        erp.update(nested)


def main():
    parser = argparse.ArgumentParser(description="更新 Phalanx SPU 采购与 ERP 信息")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--id", type=int, help="Phalanx 商品 internal ID (如 61171)")
    group.add_argument("--spu", type=str, help="商家 SPU (如 G48YX-HL112403)")

    parser.add_argument("--link", type=str, required=True, help="1688 采购链接")
    parser.add_argument("--cost", type=float, required=True, help="成本价(RMB)")
    parser.add_argument("--weight", type=float, required=True, help="重量 (克 g)")
    parser.add_argument("--supplier-code", type=str, default="GZCC", help="供应商代码 (默认 GZCC)")
    parser.add_argument("--supplier", type=str, default="广州池骋", help="供应商名称 (默认 广州池骋)")
    parser.add_argument("--hs-code", type=str, default="3926400000", help="海关编码 (默认 3926400000，必须10位全数字)")
    parser.add_argument("--express-type", type=str, default="normal", choices=["normal", "fast", "fastLiquid", "cosmeticLiquid"], help="产品属性/敏感信息 (默认 normal 普货；带电/带磁显式传 fast)")
    parser.add_argument("--token", type=str, help="Phalanx token")

    args = parser.parse_args()
    if (args.id is not None and args.id < 1) or (args.spu is not None and not args.spu.strip()):
        parser.error("请提供有效的商品内部 ID 或完整 SPU")
    if not math.isfinite(args.cost) or args.cost < 0 or not math.isfinite(args.weight) or args.weight <= 0:
        parser.error("成本价需为非负数，重量需为大于零的克数")
    if not re.fullmatch(r"[0-9]{10}", args.hs_code):
        parser.error("海关编码须为 10 位数字")
    if not args.supplier_code.strip() or not args.supplier.strip():
        parser.error("请同时填写供应商代码和名称")
    link = urllib.parse.urlsplit(args.link)
    if link.scheme not in {"https", "http"} or not link.hostname or not link.path:
        parser.error("请输入完整的采购商品链接")

    token = args.token or get_token()
    spu = args.spu.strip() if args.spu else None
    product_id = args.id if args.id is not None else find_product_id_by_spu(spu, token)
    product = fetch_product(product_id, token)
    if spu and product.get("sku") != spu:
        raise RuntimeError("详情中的 SPU 与本轮目标不一致")

    apply_erp_fields(product, args)
    phalanx_request("/oally/product/update", token, product=product)
    print(f"商品 ID {product_id}，采购与 ERP 更新成功（业务码 200）")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Phalanx ERP 更新：{error}", file=sys.stderr)
        sys.exit(1)
