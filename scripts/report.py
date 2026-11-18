# -*- coding: utf-8 -*-
"""生成最终交付: 分类报告.md + up_list_final.csv + B站分组建议"""
import json, pathlib, csv, collections, datetime

HERE = pathlib.Path(__file__).parent
rep = json.loads((HERE / "clusters.json").read_text("utf-8"))

NAMES = {
    0: "网络安全黑客攻防",
    12: "AI编程开发者效率",
    6: "计算机课程编程入门",
    4: "综合娱乐杂谈解说",
    5: "游戏实况游戏杂谈",
    9: "我的世界MC生态",
    11: "人文成长泛知识",
    3: "数码硬件科技评测",
    2: "时政国际官方媒体",
    8: "音乐助眠",
    13: "考研四六级课业学习",
    10: "求职职场大学生活",
    7: "法律社会观察",
    1: "生活美食个人纪实",
}

ups = {str(u["mid"]): u for u in json.loads((HERE / "followings.json").read_text("utf-8"))}
rows = list(csv.DictReader((HERE / "up_list.csv").open(encoding="utf-8-sig")))

# ---- CSV (带分类名) ----
with open(HERE / "up_list_final.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["mid", "昵称", "分类ID", "分类", "个人关键词", "视频数", "签名摘要"])
    for r in rows:
        mid = r["mid"]
        cid = int(r["聚类ID"])
        name = NAMES.get(cid, f"簇{cid}")
        sign = ups.get(mid, {}).get("sign", "")[:50].replace("\n", " ")
        w.writerow([mid, r["昵称"], cid, name, r["分类关键词"], r["视频数"], sign])

# ---- 报告 ----
today = datetime.date.today().isoformat()
lines = [f"# B站关注 UP 主智能分类报告", "",
         f"- 生成日期: {today}",
         f"- 账号: zzy00747 (mid 3493113343510771)",
         f"- 数据: {rep['n_ups']} 个关注 UP 主, 每人最近投稿标题+动态文案+签名",
         f"- 方法: {rep['model']} 语义向量 + {rep['method']} 聚类 (K=14)",
         f"- 数据缺口: mid=651705331(701号时钟草) 抓取失败, 仅按昵称/签名分类", "",
         "## 一、兴趣结构总览", "",
         "| 分类 | 人数 | 高频关键词 |",
         "|---|---|---|"]
for c in rep["clusters"]:
    cid = c["id"]
    lines.append(f"| {NAMES.get(cid, cid)} | {c['size']} | {' / '.join(c['terms'][:6])} |")

lines += ["", "## 二、各分类成员明细", ""]
for c in rep["clusters"]:
    cid = c["id"]
    lines.append(f"### {NAMES.get(cid, cid)} ({c['size']} 人)")
    lines.append("")
    lines.append("、".join(c["members"]))
    lines.append("")

# ---- B站分组建议 ----
lines += ["", "## 三、B站关注分组建议（可直接照抄）", "",
          "B站支持自建分组并批量移动, 建议按下面把 UP 主拖入对应分组:", ""]
for c in rep["clusters"]:
    cid = c["id"]
    lines.append(f"**分组「{NAMES.get(cid, cid)}」** ({c['size']} 人): " + "、".join(c["members"][:40]) + ("…" if c["size"] > 40 else ""))
    lines.append("")

(HERE / "分类报告.md").write_text("\n".join(lines), encoding="utf-8")
print("生成: 分类报告.md / up_list_final.csv")
print("簇概览:", {NAMES[c['id']]: c['size'] for c in rep['clusters']})
