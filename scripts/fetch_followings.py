# -*- coding: utf-8 -*-
"""抓取关注列表 -> followings.json
用法: python 01_fetch_followings.py [cookies.json]
cookies.json 由 fetch_cookies.py 或手工生成: {"SESSDATA": "...", "buvid3": "...", "bili_jct": "...", "DedeUserID": "..."}
"""
import json, sys, time, pathlib
import requests

HERE = pathlib.Path(__file__).parent
CK = json.loads((HERE / (sys.argv[1] if len(sys.argv) > 1 else "cookies.json")).read_text("utf-8"))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Referer": "https://space.bilibili.com/",
    "Origin": "https://space.bilibili.com",
}
s = requests.Session()
s.headers.update(HEADERS)
s.cookies.update(CK)

MY_MID = CK.get("DedeUserID")
assert MY_MID, "cookies.json 缺少 DedeUserID"

def get(url, **kw):
    for i in range(5):
        try:
            r = s.get(url, timeout=15, **kw)
            if r.status_code == 200:
                j = r.json()
                if j.get("code") == 0:
                    return j["data"]
                if j.get("code") == -412:
                    print("  风控 -412, 休眠 10s 重试", i + 1)
                    time.sleep(10)
                    continue
                print("  code:", j.get("code"), j.get("message"))
                return None
        except Exception as e:
            print("  网络错误:", e)
        time.sleep(3)
    return None

all_items, pn = [], 1
while pn <= 20:
    d = get(f"https://api.bilibili.com/x/relation/followings?vmid={MY_MID}&pn={pn}&ps=50&order=desc&jsonp=jsonp")
    if not d or not d.get("list"):
        break
    all_items.extend(d["list"])
    print(f"page {pn}: +{len(d['list'])} (total {len(all_items)})")
    if len(d["list"]) < 50:
        break
    pn += 1
    time.sleep(0.8)

ups = [{
    "mid": it["mid"],
    "uname": it["uname"],
    "sign": it.get("sign", ""),
    "face": it.get("face", ""),
    "mtime": it.get("mtime"),
    "special": it.get("special", 0),
} for it in all_items]
(HERE / "followings.json").write_text(json.dumps(ups, ensure_ascii=False, indent=1), "utf-8")
print(f"完成: {len(ups)} 个 UP 主 -> followings.json")
