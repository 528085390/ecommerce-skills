#!/usr/bin/env python3
"""1688 以图搜同款 —— 纯接口实现（不点 UI）

原理（2026-11 实测）：
  1. 上传与搜索是同一个 mtop 接口
     POST https://h5api.m.1688.com/h5/mtop.relationrecommend.wirelessrecommend.recommend/2.0/
  2. 上传：params.method=uploadBase64WithRequest，图片以 base64 塞进 params.imageBase64
     -> 返回 data.data.imageId
  3. 等 5~8 秒（服务端要建索引，立刻查会返回空），再查：
     params.method=getImageSearchPreResult + imageId
     -> data.data.OFFER.items[]（每项在 .data 里）

依赖：
  - 一个已登录 1688 的 Chromium 调试实例（Playwright 或 Chrome 均可，带 CDP 端口）
  - playwright（python -m pip install playwright && python -m playwright install chromium）
  cookie 从该浏览器直接读，签名用 _m_h5_tk 现算，无需手抄。

可配置（换机器/换端口时改环境变量即可）：
  AGENT_BROWSER_PORT   CDP 端口，默认 9223
  AGENT_BROWSER_HOST   CDP 主机，默认 127.0.0.1

用法：
  python3 1688_image_search.py --img /path/to/10.jpg --out /path/to/商品目录
  python3 1688_image_search.py --img 10.jpg --cdp 9223 --top 30
"""
import argparse
import base64
import csv
import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request

APPKEY = "12574478"
API = "mtop.relationrecommend.wirelessrecommend.recommend"
BASE = f"https://h5api.m.1688.com/h5/mtop.relationrecommend.wirelessrecommend.recommend/2.0/"
UA_FALLBACK = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/158.0.0.0 Safari/537.36")
CDP_HOST = os.environ.get("AGENT_BROWSER_HOST", "127.0.0.1")
CDP_PORT = os.environ.get("AGENT_BROWSER_PORT", "9223")


def md5(s):
    return hashlib.md5(s.encode()).hexdigest()


class Mtop:
    def __init__(self, cookie_header, token, ua):
        self.cookie_header = cookie_header
        self.token = token
        self.ua = ua

    def call(self, params_obj, timeout=40):
        data = json.dumps(
            {"appId": 32517, "params": json.dumps(params_obj, ensure_ascii=False, separators=(",", ":"))},
            ensure_ascii=False, separators=(",", ":"),
        )
        t = str(int(time.time() * 1000))
        sign = md5(f"{self.token}&{t}&{APPKEY}&{data}")
        q = urllib.parse.urlencode({
            "jsv": "2.7.2", "appKey": APPKEY, "t": t, "sign": sign,
            "api": API, "v": "2.0", "type": "originaljson",
            "dataType": "json", "timeout": "20000",
        })
        body = urllib.parse.urlencode({"data": data}).encode()
        req = urllib.request.Request(f"{BASE}?{q}", data=body, method="POST", headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Cookie": self.cookie_header,
            "User-Agent": self.ua,
            "Origin": "https://www.1688.com",
            "Referer": "https://www.1688.com/",
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "ignore"))


def read_cookies(cdp):
    """从已登录的调试浏览器里读 cookie。"""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://{CDP_HOST}:{cdp}")
        ctx = browser.contexts[0]
        cookies = ctx.cookies("https://h5api.m.1688.com")
        ua = UA_FALLBACK
        try:
            if ctx.pages:
                ua = ctx.pages[0].evaluate("navigator.userAgent")
        except Exception:
            pass
    if not cookies:
        sys.exit(f"未取到 1688 cookie：请确认 {cdp} 端口上的浏览器已登录 1688")
    ck = {c["name"]: c["value"] for c in cookies}
    token = ck.get("_m_h5_tk", "").split("_")[0]
    if not token:
        sys.exit("缺少 _m_h5_tk cookie：该浏览器未登录 1688，或登录态已失效，请重新登录")
    header = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
    return Mtop(header, token, ua)


def upload_image(m, img_path):
    b64 = base64.b64encode(open(img_path, "rb").read()).decode()
    size_mb = len(b64) * 3 / 4 / 1024 / 1024
    print(f"上传 {os.path.basename(img_path)}（约 {size_mb:.2f} MB）…", flush=True)
    r = m.call({
        "beginPage": 1, "pageSize": 60, "searchScene": "pcImageSearch",
        "method": "uploadBase64WithRequest", "appName": "pctusou", "imageBase64": b64,
    })
    d = (r.get("data") or {})
    if isinstance(d.get("data"), dict) and d["data"].get("imageId"):
        return str(d["data"]["imageId"]), d["data"]
    sys.exit(f"上传失败：{json.dumps(r, ensure_ascii=False)[:400]}")


def search(m, image_id, wait=6):
    print(f"等待索引 {wait}s 后查询…", flush=True)
    time.sleep(wait)
    r = m.call({
        "beginPage": 1, "pageSize": 60, "method": "getImageSearchPreResult",
        "searchScene": "pcImageSearch", "appName": "pctusou",
        "tab": "imageSearch", "imageId": image_id,
    })
    offer = ((r.get("data") or {}).get("data") or {}).get("OFFER")
    if not offer:
        sys.exit(f"查询无数据：{json.dumps(r, ensure_ascii=False)[:400]}")
    return offer


def flatten(offer):
    rows = []
    for i, item in enumerate(offer.get("items") or [], 1):
        d = item.get("data") or {}
        pi = d.get("priceInfo") or {}
        rows.append({
            "rank": i,
            "title": d.get("title") or "",
            "price": pi.get("price") or "",
            "offerId": d.get("offerId") or "",
            "saleQuantity": d.get("saleQuantity") or "",
            "bookedCount": d.get("bookedCount") or "",
            "province": d.get("province") or "",
            "city": d.get("city") or "",
            "url": f"https://detail.1688.com/offer/{d.get('offerId')}.html" if d.get("offerId") else "",
            "pic": d.get("offerPicUrl") or "",
        })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--img", required=True, help="本地图片路径（优先白底、主体清楚的原图）")
    ap.add_argument("--cdp", default=CDP_PORT,
                    help=f"已登录 1688 的浏览器 CDP 端口，默认 {CDP_PORT}（读 AGENT_BROWSER_PORT）")
    ap.add_argument("--out", default=None, help="结果输出目录（通常是素材目录），默认与图片同目录")
    ap.add_argument("--top", type=int, default=20, help="终端展示前 N 条，默认 20")
    ap.add_argument("--wait", type=int, default=6, help="上传后等待索引秒数，默认 6")
    args = ap.parse_args()

    out_dir = args.out or os.path.dirname(os.path.abspath(args.img))
    m = read_cookies(args.cdp)
    image_id, up_data = upload_image(m, args.img)
    print(f"imageId = {image_id}", flush=True)

    offer = search(m, image_id, args.wait)
    rows = flatten(offer)

    # 落盘
    raw_path = os.path.join(out_dir, "1688搜图结果.json")
    payload = {
        "image": os.path.abspath(args.img),
        "imageId": image_id,
        "imageAddress": offer.get("imageAddress"),
        "found": offer.get("found"),
        "aiTabs": [t.get("name") for t in (offer.get("aiTabs") or [])],
        "searchUrl": f"https://s.1688.com/youyuan/index.htm?tab=imageSearch&imageId={image_id}",
        "capturedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "items": rows,
    }
    json.dump(payload, open(raw_path, "w"), ensure_ascii=False, indent=1)

    csv_path = os.path.join(out_dir, "1688搜图结果.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["rank", "title"])
        w.writeheader()
        w.writerows(rows)

    print(f"\n同款货源 {len(rows)} 条（共 {offer.get('found')} 条）")
    print(f"AI 标签：{', '.join(payload['aiTabs'])}")
    print(f"结果页：{payload['searchUrl']}\n")
    print(f"{'#':>3} {'价格':>7} {'销量':>8}  标题 / 供应商")
    for r in rows[:args.top]:
        print(f"{r['rank']:>3} {('¥'+str(r['price'])):>7} {r['saleQuantity']:>8}  {r['title'][:34]} | {r['province']}{r['city']}")
    print(f"\n已保存：{raw_path}\n      {csv_path}")


if __name__ == "__main__":
    main()
