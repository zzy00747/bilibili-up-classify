# bilibili-up-classify

把 B站「我的关注」UP 主按内容语义自动分类，并直接调用 B站关系 API 创建分组、批量移人。

这是一个 [Agent Skill](https://github.com/anthropics/skills)（SKILL.md 规范）：把本次任务沉淀为可复用技能包——
SKILL.md 描述触发条件与工作流，`scripts/` 是开箱即用的 Python 脚本，`references/api-notes.md` 是实测踩坑笔记。

## 功能

- 📥 抓取关注列表 + 每个 UP 主的最近投稿语料（标题/动态文案/签名）
- 🧠 中文语义聚类（`BAAI/bge-small-zh-v1.5` 嵌入 + KMeans），内置 TF-IDF+LSA 降级路径
- 📄 交付：分类报告 Markdown、明细 CSV、兴趣星图散点图
- 📂 一键在 B站账号上创建 14 个分组并把全部 UP 主批量移入（幂等、可断点重跑）

## 使用（Agent 视角）

把本仓库放入 skills 目录（如 `~/.dsh/skills/bilibili-up-classify`），Agent 在用户提到
"分类/整理 B站关注、UP 主分组"等场景时会自动触发；人工使用则直接按顺序跑 `scripts/`：

```bash
pip install -r requirements.txt
# 1. 准备 cookies.json（SESSDATA/bili_jct/DedeUserID/buvid3/buvid4）
python scripts/fetch_followings.py     # 关注列表
python scripts/fetch_dynamics.py 2     # 每个 UP 的投稿语料（断点续抓）
python scripts/cluster.py              # 聚类 -> up_list.csv / clusters.json / up_map.png
python scripts/report.py               # -> 分类报告.md / up_list_final.csv
python scripts/apply_groups.py         # 可选：直接建分组并移人
```

## 实测要点（详见 references/api-notes.md）

- 空间投稿接口的 wbi 签名已是私有算法，标准签名必 -403 → 改用**动态流接口**（无需签名）
- 动态流 ~0.5s/请求抓 150 个 UP 就会触发 -352 → 1.5~2.5s/请求 + 冷却 60s 可稳定跑完
- 建分组是 `POST /x/relation/tag/create`（**单数**，字段名 `tag`）；移人是 `POST /x/relation/tags/addUsers`（**复数**，每批 ≤20）
- 分组名不允许 `·` 等特殊字符（22101）；含注销账号的批次整批失败（22013），脚本会自动降级为逐个重试
- 国内环境：PyPI 走阿里云镜像，HuggingFace 走 hf-mirror.com

## 效果示例（548 个关注）

| 分类 | 人数 |
|---|---|
| 网络安全黑客攻防 | 72 |
| AI编程开发者效率 | 61 |
| 计算机课程编程入门 | 58 |
| 综合娱乐杂谈解说 | 56 |
| 游戏实况游戏杂谈 | 52 |
| 我的世界MC生态 | 46 |
| …共 14 类 | … |

## ⚠️ 免责声明

仅操作**自己账号**的关注关系；请遵守 B站用户协议，控制请求频率（脚本已内置限速与退避）。
`cookies.json` 含登录凭证，绝不提交到任何仓库（已加入 .gitignore）。
