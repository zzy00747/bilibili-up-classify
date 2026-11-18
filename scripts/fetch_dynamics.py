# -*- coding: utf-8 -*-
"""抓每个 UP 主的动态流(含视频标题+文案) -> videos.json
无需 wbi 签名, 走 polymer 动态接口。断点续抓, 失败记录 failures.json
用法: python 02b_fetch_dynamics.py [PAGES=4]
"""
import json, sys, time, pathlib, random
import requests

HERE = pathlib.Path(__file__).parent
CK = json.loads((HERE / "cookies.json").read_text("utf-8"))
PAGES = int(sys.argv[1]) if len(sys.argv) > 1 else 4

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Referer": "https://space.bilibili.com/",
})
s.cookies.update(CK)

def get(url):
    for i in range(5):
        try:
            r = s.get(url, timeout=15)
            if r.status_code == 200:
                j = r.json()
                c = j.get("code")
                if c == 0:
                    return j["data"]
                if c in (-412, -352, -799):
                    print("  风控", c, "冷却 60s", i + 1, flush=True)
                    time.sleep(60)
                    continue
                return {"__code": c, "__msg": j.get("message")}
        except Exception as e:
            print("  err:", e, flush=True)
        time.sleep(6)
    return {"__code": -1, "__msg": "retry exhausted"}

ups = json.loads((HERE / "followings.json").read_text("utf-8"))
vpath = HERE / "videos.json"
out = json.loads(vpath.read_text("utf-8")) if vpath.exists() else {}
fail = []

for idx, up in enumerate(ups, 1):
    mid = str(up["mid"])
    if mid in out:
        continue
    titles, texts, offset = [], [], ""
    ok = True
    for p in range(PAGES):
        d = get(f"https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space?host_mid={mid}&offset={offset}")
        if d is None or "__code" in (d or {}):
            ok = False
            fail.append({"mid": mid, "uname": up["uname"], "r": d})
            print(f"[{idx}/{len(ups)}] FAIL {up['uname']}: {d}", flush=True)
            break
        items = d.get("items") or []
        for it in items:
            try:
                md = it["modules"]["module_dynamic"]
                desc_t = ((md.get("desc") or {}).get("text") or "").strip()
                major = md.get("major") or {}
                if major.get("type") == "MAJOR_TYPE_ARCHIVE":
                    arch = major["archive"]
                    titles.append(arch.get("title", ""))
                    if desc_t:
                        texts.append(desc_t[:80])
                elif desc_t and it.get("type") in ("DYNAMIC_TYPE_DRAW", "DYNAMIC_TYPE_WORD"):
                    texts.append(desc_t[:80])
            except Exception:
                pass
        pag = d.get("pagination") or {}
        offset = pag.get("next_offset") or ""
        if not offset or not items:
            break
        time.sleep(1.4 + random.random() * 0.6)
    if ok:
        vids = [{"title": t, "desc": "", "tname": ""} for t in titles]
        out[mid] = {"videos": vids, "texts": texts[:30]}
        print(f"[{idx}/{len(ups)}] OK {up['uname']}: {len(vids)} 视频, {len(texts)} 文案", flush=True)
    if idx % 15 == 0 or fail:
        vpath.write_text(json.dumps(out, ensure_ascii=False), "utf-8")
        (HERE / "failures.json").write_text(json.dumps(fail, ensure_ascii=False, indent=1), "utf-8")
    time.sleep(1.5 + random.random() * 1.0)

vpath.write_text(json.dumps(out, ensure_ascii=False), "utf-8")
(HERE / "failures.json").write_text(json.dumps(fail, ensure_ascii=False, indent=1), "utf-8")
print(f"完成: 成功 {len(out)} / {len(ups)}, 失败 {len(fail)}", flush=True)
