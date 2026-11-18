# -*- coding: utf-8 -*-
"""方案 B 主算法: 语料 -> TF-IDF/LSA 向量 -> HDBSCAN 聚类 -> 命名 + 报告 + 散点图
用法: python 03_cluster.py
优先用 sentence-transformers(bge-small-zh); 没装好/加载失败自动降级 TF-IDF+LSA。
"""
import json, pathlib, collections, re, sys
import numpy as np

HERE = pathlib.Path(__file__).parent
N_TOP_TERMS = 12

ups = {str(u["mid"]): u for u in json.loads((HERE / "followings.json").read_text("utf-8"))}
vids = json.loads((HERE / "videos.json").read_text("utf-8"))

# ---------- 语料 ----------
import jieba, jieba.analyse
mids, corpus, meta = [], [], []
def clean_sign(s):
    s = re.sub(r"(商务|合作|联系|微信|vx|邮箱|qq|粉丝群|交流群|直播|关注后|私信|备注|公众号)\S*", " ", s, flags=re.I)
    s = re.sub(r"[\w@.-]{6,}", " ", s, flags=re.I)
    return s.strip()
for mid, up in ups.items():
    v = vids.get(mid, {})
    vs = v.get("videos", [])
    texts = v.get("texts", [])
    title_part = "。".join(t for t in [v2["title"] for v2 in vs] if t)
    text_part = " ".join(texts)
    text = f"{up['uname']} {clean_sign(up.get('sign',''))} {title_part} {text_part}".strip() or up["uname"]
    mids.append(mid)
    corpus.append(text)
    meta.append({"mid": mid, "uname": up["uname"], "n_videos": len(vs),
                 "top_tnames": collections.Counter(v2["tname"] for v2 in vs if v2.get("tname")).most_common(3),
                 "latest": vs[0].get("created") if vs else None})
print(f"UP 主 {len(corpus)} 个, 语料平均长度 {int(np.mean([len(c) for c in corpus]))} 字")

# ---------- 向量化 ----------
model_name = None
X = None
try:
    from sentence_transformers import SentenceTransformer
    st = SentenceTransformer("BAAI/bge-small-zh-v1.5")
    X = st.encode(corpus, normalize_embeddings=True, show_progress_bar=False)
    model_name = "bge-small-zh-v1.5"
    print("使用神经向量:", model_name)
except Exception as e:
    print("sentence-transformers 不可用, 降级 TF-IDF/LSA:", type(e).__name__, str(e)[:120])

if X is None:
    import jieba
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.decomposition import TruncatedSVD
    from sklearn.preprocessing import normalize
    tok = lambda t: [w for w in jieba.cut(t) if len(w) > 1 and not re.match(r"^[0-9a-zA-Z\s\W]+$", w)]
    tfv = TfidfVectorizer(tokenizer=tok, token_pattern=None, sublinear_tf=True,
                          min_df=2, max_df=0.4, max_features=20000)
    Xs = tfv.fit_transform(corpus)
    n_comp = max(2, min(80, Xs.shape[0] - 1, Xs.shape[1]))
    svd = TruncatedSVD(n_components=n_comp, random_state=42)
    X = normalize(svd.fit_transform(Xs))
    terms = np.array(tfv.get_feature_names_out())
    print(f"TF-IDF 词表 {Xs.shape[1]}, LSA 降到 {n_comp} 维")

# ---------- 聚类 ----------
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

N_CLUSTERS = 14
km = KMeans(n_clusters=N_CLUSTERS, n_init=20, random_state=42)
final = km.fit_predict(X)
sil = silhouette_score(X, final)
method = f"KMeans(k={N_CLUSTERS})"
print(f"KMeans(k={N_CLUSTERS}): 轮廓 {sil:.3f}")

# ---------- 命名 ----------
def top_terms(corpus_list, k=N_TOP_TERMS):
    import jieba
    cnt = collections.Counter()
    for t in corpus_list:
        for w in jieba.cut(t):
            w = w.strip()
            if len(w) > 1 and not re.match(r"^[\d\W]+$", w):
                cnt[w] += 1
    return [w for w, _ in cnt.most_common(k)]

groups = collections.defaultdict(list)
for i, c in enumerate(final):
    groups[int(c)].append(i)

report = {"method": method, "model": model_name or "tfidf+lsa", "n_ups": len(corpus), "clusters": []}
for c in sorted(groups, key=lambda c: -len(groups[c])):
    idxs = groups[c]
    names = [meta[i]["uname"] for i in idxs]
    terms = top_terms([corpus[i] for i in idxs])
    report["clusters"].append({"id": c, "size": len(idxs), "terms": terms, "members": names})
(HERE / "clusters.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")

# ---------- CSV ----------
import csv
with open(HERE / "up_list.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["mid", "昵称", "聚类ID", "分类关键词", "视频数", "主要分区", "最近更新"])
    for i, c in enumerate(final):
        m = meta[i]
        w.writerow([m["mid"], m["uname"], c, "/".join(top_terms([corpus[i]], 4)),
                    m["n_videos"], ";".join(t[0] for t in m["top_tnames"]), m["latest"]])

# ---------- 散点图 ----------
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "sans-serif"]
    plt.rcParams["axes.unicode_minus"] = False
    from sklearn.decomposition import PCA
    p = PCA(n_components=2).fit_transform(X)
    plt.figure(figsize=(16, 12))
    cmap = plt.get_cmap("tab20")
    for c in sorted(groups):
        idxs = np.array(groups[c])
        plt.scatter(p[idxs, 0], p[idxs, 1], s=40, color=cmap(c % 20), label=f"C{c}({len(idxs)})")
    for i in np.random.RandomState(0).choice(len(p), min(60, len(p)), replace=False):
        plt.annotate(meta[i]["uname"], (p[i, 0], p[i, 1]), fontsize=7, alpha=0.75)
    plt.legend(fontsize=8, markerscale=2)
    plt.title(f"关注 UP 主兴趣星图 ({method})")
    plt.tight_layout()
    plt.savefig(HERE / "up_map.png", dpi=130)
    print("散点图 -> up_map.png")
except ImportError:
    print("matplotlib 未安装, 跳过散点图")

print("完成 -> up_list.csv / clusters.json")
