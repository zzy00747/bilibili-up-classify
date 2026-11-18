# -*- coding: utf-8 -*-
"""直接在 B 站创建 14 个分组并把 548 个 UP 主批量移入
1) 列出现有分组  2) 创建缺失分组  3) 批量 addUsers (每批 20 人)  4) 校验
"""
import json, pathlib, time, random
import requests

HERE = pathlib.Path(__file__).parent
CK = json.loads((HERE / "cookies.json").read_text("utf-8"))
CSRF = CK["bili_jct"]

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Referer": "https://space.bilibili.com/3493113343510771/relation/follow",
    "Origin": "https://space.bilibili.com",
})
s.cookies.update(CK)

NAMES = {
    "网络安全黑客攻防": 0, "AI编程开发者效率": 12, "计算机课程编程入门": 6,
    "综合娱乐杂谈解说": 4, "游戏实况游戏杂谈": 5, "我的世界MC生态": 9,
    "人文成长泛知识": 11, "数码硬件科技评测": 3, "时政国际官方媒体": 2,
    "音乐助眠": 8, "考研四六级课业学习": 13, "求职职场大学生活": 10,
    "法律社会观察": 7, "生活美食个人纪实": 1,
}
# 簇id -> 分组名
CID2TAG = {v: k for k, v in NAMES.items()}

def post(url, data):
    for i in range(4):
        r = s.post(url, data=data, timeout=15)
        j = r.json()
        if j.get("code") == 0:
            return j
        if j.get("code") in (-412, -352, -799):
            print("  风控", j["code"], "冷却 40s", flush=True)
            time.sleep(40)
            continue
        return j
    return j

# 0) 会话校验
nav = s.get("https://api.bilibili.com/x/web-interface/nav", timeout=15).json()
assert nav["code"] == 0 and nav["data"]["isLogin"], "登录态失效, 请重新获取 cookies"
print("登录态 OK:", nav["data"]["uname"], flush=True)

# 1) 现有分组
tags = s.get("https://api.bilibili.com/x/relation/tags?only_master=false", timeout=15).json()
existing = {}
if tags.get("code") == 0:
    for t in tags["data"]:
        if t.get("tagid") not in (0, -10):  # 0=默认分组, -10=特别关注
            existing[t["name"]] = t["tagid"]
    print("现有分组:", {k: v for k, v in existing.items()}, flush=True)

# 2) 创建分组
tag_ids = {}
for name in NAMES:
    if name in existing:
        tag_ids[name] = existing[name]
        print(f"已存在: {name} -> {existing[name]}", flush=True)
        continue
    j = post("https://api.bilibili.com/x/relation/tag/create", {"tag": name, "csrf": CSRF})
    if j.get("code") == 0:
        tid = j["data"]["tagid"]
        tag_ids[name] = tid
        print(f"创建: {name} -> {tid}", flush=True)
    else:
        print(f"创建失败: {name}: {j}", flush=True)
    time.sleep(0.8)

# 3) mid -> 分组
rep = json.loads((HERE / "clusters.json").read_text("utf-8"))
mid2tag = {}
for c in rep["clusters"]:
    tagname = CID2TAG[c["id"]]
    for uname in c["members"]:
        pass  # members 是昵称, 需要用 mid 对应
# 用 up_list_final.csv 的 聚类ID 对应
import csv
rows = list(csv.DictReader((HERE / "up_list_final.csv").open(encoding="utf-8-sig")))
groups = {}
for r in rows:
    cid = int(r["分类ID"])
    groups.setdefault(CID2TAG[cid], []).append(r["mid"])

# 4) 批量移入 (每批 20)
fail_log = []
for tagname, mids in groups.items():
    tid = tag_ids.get(tagname)
    if not tid:
        print(f"无分组id: {tagname}, 跳过", flush=True)
        continue
    for i in range(0, len(mids), 20):
        batch = mids[i:i + 20]
        j = post("https://api.bilibili.com/x/relation/tags/addUsers",
                 {"fids": ",".join(batch), "tagids": str(tid), "csrf": CSRF})
        if j.get("code") == 0:
            print(f"{tagname}: +{len(batch)} (累计 {min(i+20, len(mids))}/{len(mids)})", flush=True)
        elif j.get("code") == 22013:
            # 批次里有注销账号 -> 逐个重试
            ok_n, bad = 0, []
            for m in batch:
                jj = post("https://api.bilibili.com/x/relation/tags/addUsers",
                          {"fids": m, "tagids": str(tid), "csrf": CSRF})
                if jj.get("code") == 0:
                    ok_n += 1
                else:
                    bad.append((m, jj.get("code"), jj.get("message")))
                time.sleep(0.4)
            print(f"{tagname}: 逐个重试 +{ok_n}/{len(batch)}, 跳过 {bad}", flush=True)
            if bad:
                fail_log.append({"tag": tagname, "bad": bad})
        else:
            fail_log.append({"tag": tagname, "fids": batch, "resp": j})
            print(f"{tagname}: FAIL {j}", flush=True)
        time.sleep(0.8 + random.random() * 0.5)

# 5) 校验
final = s.get("https://api.bilibili.com/x/relation/tags?only_master=false", timeout=15).json()
if final.get("code") == 0:
    print("\n最终分组:", flush=True)
    for t in final["data"]:
        print(f"  [{t['tagid']}] {t['name']}: {t.get('count')} 人", flush=True)

if fail_log:
    (HERE / "group_failures.json").write_text(json.dumps(fail_log, ensure_ascii=False, indent=1), "utf-8")
    print(f"\n失败 {len(fail_log)} 批 -> group_failures.json (可重跑本脚本续传)", flush=True)
else:
    print("\n全部成功", flush=True)
