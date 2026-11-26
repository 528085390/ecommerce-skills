#!/usr/bin/env python3
"""Compare recorded SHOPLINE counts and receipts without opening the store."""

import argparse
import json
from pathlib import Path


def counts(record, field):
    pair = record.get(field)
    if not isinstance(pair, dict):
        return None
    public, hidden = pair.get("public"), pair.get("hidden")
    if any(type(value) is not int or value < 0 for value in (public, hidden)):
        return None
    return public, hidden


def reconcile(record):
    expected = record.get("expected")
    if type(expected) is not int or expected < 1:
        raise ValueError("expected 须为正整数。")
    receipt = record.get("receipt")
    before, after = counts(record, "before"), counts(record, "after")
    deltas = [end - start for start, end in zip(before, after)] if before and after else None
    reasons = []
    if not isinstance(receipt, dict):
        reasons.append("缺少导入回执")
    elif (
        receipt.get("status") != "completed"
        or type(receipt.get("success")) is not int
        or receipt["success"] != expected
        or type(receipt.get("failure")) is not int
        or receipt["failure"] != 0
    ):
        reasons.append("导入回执与目标条数不符")
    if deltas is None:
        reasons.append("缺少有效的导入前后计数")
    elif deltas != [expected, 0]:
        reasons.append("公开或隐藏评价增量不符")
    return {
        "product_id": record["product_id"],
        "status": "needs_agent" if reasons else "counts_match",
        "public_delta": deltas[0] if deltas is not None else None,
        "hidden_delta": deltas[1] if deltas is not None else None,
        "reasons": reasons,
    }


def main():
    parser = argparse.ArgumentParser(description="批量核对已采集的评价计数和回执。")
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    try:
        records = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(records, list) or not records:
            raise ValueError("输入须为非空商品记录数组。")
        ids, results = set(), []
        for record in records:
            product_id = record.get("product_id") if isinstance(record, dict) else None
            if not isinstance(product_id, str) or not product_id.strip() or product_id in ids:
                raise ValueError("每款商品须提供唯一的字符串 product_id。")
            ids.add(product_id)
            results.append(reconcile(record))
    except (OSError, ValueError) as error:
        parser.exit(1, f"核对失败：{error}\n")
    matched = sum(result["status"] == "counts_match" for result in results)
    print(json.dumps({"counts_match": matched, "needs_agent": len(results) - matched, "products": results}, ensure_ascii=False))
    return 0 if matched == len(results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
