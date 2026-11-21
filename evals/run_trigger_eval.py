# -*- coding: utf-8 -*-
"""Trigger-accuracy harness for this skill (Claude Code / Agent Skills).

Measures whether a given `description` makes an agent actually load the skill.
It installs nothing: point --skill-dir at the skill folder and make sure the
skill is visible to the agent (e.g. copied into ~/.claude/skills/<name>/), then
each query is sent to `claude -p` and the stream is scanned for a Skill tool call
naming this skill.

Side-effecting tools are disallowed so a trigger can never execute the real
pipeline, and the subprocess is killed the moment a trigger is observed.

Usage:
  python run_trigger_eval.py --evals evals/trigger-evals.json \
      --skill bilibili-up-classify --model <model-id> \
      [--settings <override-settings.json>] [--runs 1] [--workers 4] \
      [--timeout 100] [--out result.json]

Why --settings exists: some Claude Code installs route through a proxy that
rejects deferred tool loading, which makes `claude -p` fail before any skill can
trigger. A minimal override settings file with ENABLE_TOOL_SEARCH=false fixes it.
"""
import argparse
import json
import os
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor

# Tools we never want the probe to actually use: a trigger must be side-effect free.
BLOCKED = "Bash,Edit,Write,NotebookEdit,WebFetch,WebSearch,Task,Read,Glob,Grep"


def find_claude() -> str:
    """Resolve a spawnable claude binary.

    On Windows the npm shim is claude.cmd / claude.ps1, which CreateProcess
    cannot launch directly, so prefer the real claude.exe inside the package.
    """
    appdata = os.environ.get("APPDATA", "")
    cand = os.path.join(appdata, "npm", "node_modules", "@anthropic-ai",
                        "claude-code", "bin", "claude.exe")
    if appdata and os.path.isfile(cand):
        return cand
    for name in ("claude.exe", "claude"):
        p = shutil.which(name)
        if p and not p.lower().endswith((".cmd", ".ps1", ".bat")):
            return p
    return shutil.which("claude") or "claude"


def run_one(query: str, skill: str, model: str, timeout: int,
            settings: str | None) -> bool:
    cmd = [find_claude()]
    if settings:
        cmd += ["--settings", settings]
    cmd += [
        "-p", query,
        "--output-format", "stream-json",
        "--verbose",
        "--include-partial-messages",
        "--model", model,
        "--disallowedTools", BLOCKED,
    ]
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    env["ENABLE_TOOL_SEARCH"] = "false"
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             env=env, text=True, encoding="utf-8", errors="replace")
    except Exception as e:
        print(f"  spawn failed: {e}", flush=True)
        return False

    needle = '"skill":"' + skill + '"'
    triggered = False
    start = time.time()

    def scan(text: str) -> bool:
        return needle in text.replace(" ", "").replace("\t", "")

    try:
        while time.time() - start < timeout:
            line = p.stdout.readline()
            if not line:
                if p.poll() is not None:
                    break
                continue
            if scan(line):
                triggered = True
                break
        if not triggered:
            triggered = scan(p.stdout.read() or "")
    finally:
        for closer in (p.kill, p.stdout.close):
            try:
                closer()
            except Exception:
                pass
    return triggered


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--evals", required=True, help="JSON list of {query, should_trigger}")
    ap.add_argument("--skill", required=True, help="skill name as the agent sees it")
    ap.add_argument("--model", required=True, help="model id for claude -p")
    ap.add_argument("--settings", default=None, help="optional claude --settings override file")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=100)
    ap.add_argument("--out", default="trigger_result.json")
    ap.add_argument("--desc", default="", help="label of the description version under test")
    a = ap.parse_args()

    items = json.loads(open(a.evals, encoding="utf-8").read())
    jobs = [(i, it["query"]) for i, it in enumerate(items) for _ in range(a.runs)]

    lock = threading.Lock()
    hits: dict[int, list[bool]] = {}
    done = [0]

    def work(job):
        idx, q = job
        hit = run_one(q, a.skill, a.model, a.timeout, a.settings)
        with lock:
            hits.setdefault(idx, []).append(hit)
            done[0] += 1
            print(f"[{done[0]}/{len(jobs)}] {'HIT ' if hit else 'miss'} "
                  f"{'should   ' if items[idx]['should_trigger'] else 'shouldNOT'} :: {q[:44]}",
                  flush=True)

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        list(ex.map(work, jobs))

    rows, passed = [], 0
    for idx, it in enumerate(items):
        got = hits.get(idx, [])
        rate = sum(got) / len(got) if got else 0.0
        ok = (rate >= 0.5) == bool(it["should_trigger"])
        passed += ok
        rows.append({"query": it["query"], "should_trigger": bool(it["should_trigger"]),
                     "trigger_rate": round(rate, 2), "pass": ok})

    acc = passed / len(items)
    print("\n" + "=" * 60)
    print(f"accuracy: {passed}/{len(items)} = {acc:.1%}")
    for r in rows:
        if not r["pass"]:
            kind = "漏触发" if r["should_trigger"] else "误触发"
            print(f"  MISS ({kind}): {r['query']}")
    json.dump({"desc_version": a.desc, "skill": a.skill, "model": a.model,
               "accuracy": round(acc, 3), "results": rows},
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"saved -> {a.out}")


if __name__ == "__main__":
    main()
