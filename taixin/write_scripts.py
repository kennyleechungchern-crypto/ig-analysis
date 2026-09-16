#!/usr/bin/env python3
"""Step 3 · 逐字稿 → Kenny 口播稿（Claude API）→ scripts/<id>.md + scripts/INDEX.md

用法:
  python write_scripts.py            # 所有还没写过稿的逐字稿
  python write_scripts.py --ids abc  # 指定
  python write_scripts.py --model claude-sonnet-5 --force

需要 ANTHROPIC_API_KEY（或 `ant auth login`）。
"""
import argparse
import re
from datetime import datetime

import anthropic

from common import PROMPT_DIR, SCRIPT_DIR, load_transcripts

DEFAULT_MODEL = "claude-opus-5"


def build_user_message(rec: dict) -> str:
    return (
        f"以下是一条短视频的逐字稿（来源：{rec.get('url')}，标题：{rec.get('title') or '无'}，"
        f"播放量：{rec.get('views')}）。\n\n"
        "请按 system 里的规范，提取主题并写成 Kenny 的口播稿。\n\n"
        "<transcript>\n" + rec["transcript"] + "\n</transcript>"
    )


def write_one(client: anthropic.Anthropic, system: str, rec: dict, model: str) -> str:
    with client.messages.stream(
        model=model,
        max_tokens=8000,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": build_user_message(rec)}],
    ) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason == "refusal":
        raise RuntimeError("model refused")
    return "".join(b.text for b in msg.content if b.type == "text").strip()


def header(rec: dict) -> str:
    return (
        f"# {rec.get('title') or rec['id']}\n\n"
        f"- 灵感来源: {rec.get('url')}（@{rec.get('channel')}，播放 {rec.get('views')}）\n"
        f"- 生成: {datetime.now():%Y-%m-%d}\n\n"
    )


def rebuild_index() -> None:
    rows = ["# Kenny 口播稿索引\n", "| 文件 | 主题 | 金句 |", "|---|---|---|"]
    for p in sorted(SCRIPT_DIR.glob("*.md")):
        if p.name == "INDEX.md":
            continue
        text = p.read_text(encoding="utf-8")
        topic = re.search(r"## 主题\s*\n+(.+)", text)
        quote = re.search(r"## 金句\s*\n+(.+)", text)
        rows.append(f"| [{p.stem}]({p.name}) | {topic.group(1).strip() if topic else ''} | {quote.group(1).strip() if quote else ''} |")
    (SCRIPT_DIR / "INDEX.md").write_text("\n".join(rows) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="+")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    system = (PROMPT_DIR / "kenny_voice.md").read_text(encoding="utf-8")
    transcripts = load_transcripts()
    SCRIPT_DIR.mkdir(parents=True, exist_ok=True)

    ids = args.ids or list(transcripts)
    todo = [i for i in ids if i in transcripts and (args.force or not (SCRIPT_DIR / f"{i}.md").exists())]
    if args.limit:
        todo = todo[: args.limit]
    print(f"✍️  待写 {len(todo)} 条（model={args.model}）")

    client = anthropic.Anthropic()
    for n, vid in enumerate(todo, 1):
        rec = transcripts[vid]
        print(f"[{n}/{len(todo)}] {vid} · {rec.get('title', '')[:30]}")
        try:
            body = write_one(client, system, rec, args.model)
        except anthropic.RateLimitError as e:
            print(f"  [rate-limit] {e}; 稍后重跑即可")
            break
        except anthropic.APIStatusError as e:
            print(f"  [api {e.status_code}] {e.message}")
            continue
        (SCRIPT_DIR / f"{vid}.md").write_text(header(rec) + body + "\n", encoding="utf-8")
        print("  ✅")
    rebuild_index()
    print(f"索引 → {SCRIPT_DIR / 'INDEX.md'}")


if __name__ == "__main__":
    main()
