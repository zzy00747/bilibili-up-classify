# 触发评测（description 优化记录）

`description` 是 skill 唯一的触发依据。本目录用 20 条真实口径的 query（10 条应触发 + 10 条 near-miss 不应触发）验证它能被正确唤起。

## 方法

用 `run_trigger_eval.py` 驱动真实 agent 环境：把 skill 放进 `~/.claude/skills/<name>/`，
每条 query 跑一次 `claude -p`，扫描 stream 里是否出现 `"skill":"<name>"` 的 Skill 调用。
为保证判定无副作用，探针禁用 `Bash/Edit/Write/Read/Glob/Grep/WebFetch/...`，且一旦观察到触发立即 kill 进程。

```bash
# 1) 让 agent 能看到这个 skill
cp -r . ~/.claude/skills/bilibili-up-classify

# 2) 跑评测
python evals/run_trigger_eval.py \
  --evals evals/trigger-evals.json \
  --skill bilibili-up-classify \
  --model <your-model-id> \
  --workers 4 --out evals/result.json
```

> 若 `claude -p` 报 `tools.defer_loading` 类错误，说明该环境的 Claude Code 走了不支持延迟工具加载的中转：
> 用一个只含 `ENABLE_TOOL_SEARCH=false` 的 settings 覆盖文件，通过 `--settings` 传入即可。

## 结果

| 版本 | description 要点 | 准确率 | 漏触发 | 误触发 |
|---|---|---|---|---|
| v1 | 首版：按"关注/分类/分组"关键词列举 | **80%** (16/20) | 0 | 4 |
| **v2（采用）** | 明确"核心意图=给关注的人归类/分组/整理"，并点出 5 类反例（下载/取关/推送/单UP主分析/收藏夹） | **95%** (19/20) | 0 | 1 |
| v3 | 在 v2 上把反例扩写成显式"不要用"清单 | 85% (17/20) | 0 | 3 |

### 结论

- **v2 胜出**：正例 10/10 全中，near-miss 只误触发 1 条（`用yt-dlp把B站上关注的UP主最近更新的视频下载下来`）。
- **v3 是反面教材**：把反例写成 `收藏夹`/`分组`/`取关` 这类强关键词清单后，这些词本身反而成了新的触发线索，
  误触发从 1 条回到 3 条。description 里堆负面词会污染词面信号。
- 有效做法是**写清"核心意图是什么"**（给关注的人归类），而不是罗列一堆"不要做什么"。

逐条结果见 `result-v1.json` / `result-v2.json` / `result-v3.json`。

## 复现注意

- 单次运行有采样噪声（模型非确定性）。要比较两个版本，建议 `--runs 3 --workers 4` 取触发率后再判定。
- 判定阈值：`trigger_rate >= 0.5` 记为"会触发"。
