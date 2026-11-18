# B站接口实战笔记（2026-11 实测）

本文件记录整条链路实测踩坑结论。接口随时间可能变化, 出现新错误码时先抓真实浏览器请求对比。

## Cookie 获取

- SESSDATA 是 **httpOnly**, 页面里 `document.cookie` 拿不到。
- 可行方式:
  1. DevTools Network 面板任选一个 api.bilibili.com 请求 → 复制请求头 `Cookie` 整段 → 拆出需要的键。
  2. 让用户 F12 → Application → Cookies → 手抄 SESSDATA / bili_jct / DedeUserID / buvid3 / buvid4。
  3. 自动化浏览器可用 CDP `Network.getCookies`。
- 必需键: `SESSDATA`(登录态), `bili_jct`(csrf, POST 必带), `DedeUserID`(自己的 mid)。
  建议同时带 `buvid3/buvid4/buvid_fp/b_nut/_uuid/bili_ticket`(部分风控校验依赖设备指纹类 Cookie)。
- SESSDATA 有效期约 2 年, 失效表现为 nav 接口 `isLogin: false`。

## 登录态 / 用户信息

- `GET https://api.bilibili.com/x/web-interface/nav` — 校验登录态 + 拿 mid。
  **必须带 UA**, 否则返回 HTML 而非 JSON(这是"JSONDecodeError"最常见原因)。

## 关注列表

- `GET https://api.bilibili.com/x/relation/followings?vmid={mid}&pn={pn}&ps=50&order=desc`
- **翻页陷阱**: 响应里的 `data.rever` 是"剩余数"而非总数, 用 `len(all) >= rever` 判停会在第一页就退出。
  正确做法: 循环到 `list` 为空或长度 < ps, 上限设 20 页兜底。
- 无需 wbi, 带 Cookie 即可。

## 每个UP主的投稿语料

### ✅ 可用: 动态流(推荐)

`GET https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space?host_mid={mid}&offset={offset}`

- 无需 wbi 签名, 带 Cookie 直连。
- 每页 ~12 条, `data.pagination.next_offset` 翻页, 空串/无则到底。
- 视频动态: `modules.module_dynamic.major.type == "MAJOR_TYPE_ARCHIVE"`, 标题在 `major.archive.title`;
  UP 文案在 `modules.module_dynamic.desc.text`。纯文字动态(DYNAMIC_TYPE_DRAW/WORD)的 desc 也是有用语料。
- **风控节奏**: 约 0.5s/请求连抓 150 个 UP 后触发 -352。改为 1.5~2.5s/请求 + -352 时冷却 60s 后基本稳定。
  548 个 UP × 2 页 × ~2s ≈ 25 分钟。脚本必须支持断点续抓(结果落盘, 跳过已抓 mid)。

### ❌ 不可用: 空间投稿接口

`GET https://api.bilibili.com/x/space/wbi/arc/search?...&w_rid={md5}&wts={ts}`

2024 年后实测结论(多次实验验证):
1. 标准 wbi 签名(mixin key 表打乱 img_key+sub_key 后取 32 位, md5(sorted_query+key))**总是 -403 访问权限不足**, 即使参数与真实页面请求完全一致。
2. 真实页面能通过——说明它用的是私有签名算法, 非 MD5 wbi; 且对同一 w_rid:
   - wts 距今 ~3 分钟 → 放行; ~10 分钟 → -403。时效窗口只有几分钟。
   - 疑似与浏览器侧 gaia 校验(ExClimbCongLing)绑定。
3. 结论: **不要浪费时间逆向该签名**, 动态流接口完全够用。

## 关注分组(可直接写账号)

- 列分组: `GET https://api.bilibili.com/x/relation/tags?only_master=false`
  (注意: 不是 `/tags/list`, 会返回 HTML)。特殊 tagid: `-10` 特别关注, `-2` 悄悄关注, `0` 默认分组。
- **建分组**: `POST https://api.bilibili.com/x/relation/tag/create` —— 单数 `tag`!
  表单: `tag={名称}&csrf={bili_jct}`。字段名是 `tag` 不是 `tagname`。
  **分组名不允许特殊字符**(·、标点等), 违反报 `22101 分组名称命名不允许包含特殊字符`, 用纯汉字/字母/数字, ≤16 字。
- **批量移人**: `POST https://api.bilibili.com/x/relation/tags/addUsers` —— 复数 `tags`!
  表单: `fids={mid1,mid2,...}&tagids={tagid}&csrf={bili_jct}`, 每批 ≤20 个 fid。
  同一 UP 可属于多个分组; 移入自定义分组后会从默认分组移除。
- **注销账号陷阱**: 批次中含已注销账号 → 整批失败 `22013 账号已注销，无法完成操作`。
  降级策略: 整批失败后逐个重试, 跳过注销账号。
- 建议全部请求带 `Referer: https://space.bilibili.com/{mid}/relation/follow`(实测无 Referer 也能过, 但带上更稳)。
- 幂等性: 重复 create 同名分组会报错(捕获即可), 重复 addUsers 无副作用。

## 通用约定

- 所有请求带: UA(Chrome 桌面版) + 上述 Cookie。GET 也要带。
- 风控错误码: `-352` 风控校验失败, `-412` 请求被拦截, `-799` 频率限制。统一策略: 冷却 40~60s 重试, 最多 3~5 次。
- 响应体约定: `code == 0` 成功; 其余看 `message`。

## 环境依赖(国内网络实测)

- PyPI 直连 ConnectionReset → 用 `-i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com`。
- HuggingFace 不可达 → `HF_ENDPOINT=https://hf-mirror.com` 下载 `BAAI/bge-small-zh-v1.5`(~100MB)。
- torch: Windows 上 PyPI 的 wheel 即 CPU 版, ~200MB, 阿里云镜像可拉。

## 聚类选型实测结论

- 数据特点: 548 个 UP, 每人 10~40 条标题+文案, 类目天然重叠(如"AI编程"vs"计算机课程")。
- **HDBSCAN(min_cluster_size 4~12)**: 要么塌缩成 2~4 个巨簇, 要么 50%+ 噪声点, 不可用。
- **KMeans(k=14, n_init=20) on bge-small-zh 嵌入**: 轮廓系数仅 ~0.03(真实重叠分布的常态), 但簇语义清晰, 人工检查全部成立。
- 结论: 别追求轮廓系数, 以簇关键词+成员的可读性为准; k 取 10~16, 按 `len(ups)/40` 微调。
- 语料配方: 昵称 + 清洗后签名(正则去"商务/合作/微信/群/邮箱…"及联系方式) + 投稿标题 + 动态文案。签名里的话题描述对低产 UP 很关键。
- 降级路径: sentence-transformers 不可用时 TF-IDF(jieba 分词) + TruncatedSVD + normalize, 质量略降但可用。
