---
name: bilibili-up-classify
description: 把 B站「我的关注」UP 主按内容语义自动分类并直接创建/填充分组。当用户提到分类/整理/归纳 B站关注、UP 主太多想分组、想看自己关注了什么领域的 UP、生成关注清单/兴趣星图、或想把某批 UP 主批量移入 B站分组时使用本 skill——即使用户只说"帮我整理下 B站关注"这类模糊表述也应触发。覆盖：抓取关注列表与每个 UP 主的投稿语料、中文语义聚类(bge 向量 + KMeans)、生成分类报告/CSV/散点图、以及直接调用 B站关系 API 建分组并批量移人。
---

# Bilibili UP 主关注分类

把用户的 B站关注列表做语义聚类分类, 并可选地直接在 B站账号上创建分组、批量移动 UP 主入组。

## 何时走哪条路

- 用户只要"分类/看看我关注了啥" → 执行 抓取 → 聚类 → 报告(第 1-3 步)。
- 用户要"直接在 B站上分组/帮我建分组" → 继续执行第 4 步(apply_groups.py)。
- 动手前先读 `references/api-notes.md`——所有接口细节、风控坑、Cookie 获取方式都在里面, 不读必踩坑。

## 前置条件

- Python 3.10+, 依赖: `requests numpy scikit-learn jieba matplotlib sentence-transformers torch(CPU 即可)`。
  PyPI 直连常被重置, 优先用 `-i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com`;
  HuggingFace 模型下载用 `HF_ENDPOINT=https://hf-mirror.com`。
- 登录态 Cookie: 需要用户提供或从浏览器提取(SESSDATA 是 httpOnly, `document.cookie` 拿不到, 详见 api-notes.md 的「Cookie 获取」)。写到 `scripts/` 同目录的 `cookies.json`:
  ```json
  {"SESSDATA": "...", "bili_jct": "...", "DedeUserID": "...", "buvid3": "...", "buvid4": "..."}
  ```

## 工作流

### 1. 抓关注列表

```bash
python scripts/fetch_followings.py        # -> followings.json (mid/uname/sign/mtime)
```
注意: 翻页必须循环到空页为止, `data.rever` 是剩余数不是总数, 用它判停会漏抓。

### 2. 抓每个 UP 主的投稿语料

```bash
python scripts/fetch_dynamics.py 2        # -> videos.json, failures.json
```
用**动态流接口** `polymer/web-dynamic/v1/feed/space` 拿最近投稿标题+文案。不要尝试空间投稿接口 `x/space/wbi/arc/search`——它的签名是私有算法, 标准 wbi 签名必 -403, 且 wts 时效只有几分钟(完整分析见 api-notes.md)。
节奏控制: 每请求 1.5~2.5s, 遇 -352 冷却 60s; 连续快抓 ~150 次就会触发风控。脚本支持断点续抓, 失败重跑即可。

### 3. 聚类 + 报告

```bash
python scripts/cluster.py                 # -> up_list.csv, clusters.json, up_map.png
python scripts/report.py                  # -> 分类报告.md, up_list_final.csv
```
- 嵌入: `BAAI/bge-small-zh-v1.5`(512 维, CPU 可跑); 语料 = 昵称 + 清洗后签名(去商务联系方式) + 投稿标题 + 动态文案。
- 聚类用 **KMeans(k≈14, n_init=20)**。HDBSCAN 在这种真实重叠分布上要么塌缩要么噪声过半, 已实测放弃。k 可按 `len(followings)/40` 自适应调整。
- cluster.py 内置 TF-IDF+LSA 降级路径: sentence-transformers 加载失败时自动切换。
- 产物: 带"分类ID/分类名/个人关键词"的 CSV、每簇成员+关键词的报告、按簇着色的 PCA 散点图(用户一眼能看出兴趣结构)。
- 簇名(KMeans 是无监督的, 簇号会变): 读 clusters.json 每簇的 top terms + 成员名单给簇起名, 然后**把名字填进 report.py 的 NAMES 映射再跑**。

### 4. 直接在 B站建分组(用户明确要求时)

```bash
python scripts/apply_groups.py            # 创建分组 + 批量移人, 幂等可重跑
```
- 列分组: `GET /x/relation/tags?only_master=false`
- 建分组: `POST /x/relation/tag/create`(注意单数 tag!), 表单字段名是 `tag`
- 移人: `POST /x/relation/tags/addUsers`(复数 tags!), `fids` 逗号分隔每批 ≤20
- 分组名**不允许特殊字符**(·、标点等, 报 22101), 用纯汉字/字母/数字
- 含"已注销账号"的批次整批失败(22013), 脚本已内置逐个重试的降级逻辑, 注销账号会被自动跳过留在默认分组
- 每请求间隔 0.8~1.3s, 全程约 1~2 分钟

## 输出格式

最终交付四件套, 全部放进用户指定目录(默认 `bili-up-classify/`):
1. `分类报告.md` — 兴趣结构总览表 + 各分类成员明细 + B站分组建议
2. `up_list_final.csv` — mid/昵称/分类/关键词/视频数(UTF-8-SIG, Excel 直接打开不乱码)
3. `up_map.png` — 兴趣星图(PCA 二维散点, 越近越相似, 中文字体设 Microsoft YaHei)
4. B站实际分组状态(如执行了第 4 步)

## 失败排查速查

| 症状 | 处置 |
|---|---|
| 接口返回非 JSON(HTML) | 请求缺 UA 或 Referer, 见 api-notes.md |
| -352 / -412 | 风控, 冷却 60s+ 放慢节奏; 连续风控就歇 5 分钟再跑 |
| 22101 分组名特殊字符 | 改纯文字名 |
| 22013 账号已注销 | 无法移入自定义分组, 跳过即可 |
| sentence-transformers 加载失败 | cluster.py 自动降级 TF-IDF+LSA, 无需干预 |
| PyPI 安装超时/重置 | 换阿里云镜像; HF 换 hf-mirror.com |
