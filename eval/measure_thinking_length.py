"""Measure Qwen3 thinking length on a JSONL prompt set via a vLLM OpenAI-compatible server.

The server must run with `--reasoning-parser qwen3` so the thinking text comes back in
`reasoning_content`. Thinking length is counted in tokens with the server's /tokenize.
"""
import argparse
import asyncio
import json
import statistics
from pathlib import Path

import httpx
from openai import AsyncOpenAI

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", required=True, help="e.g. https://<pod>-8000.proxy.runpod.net")
parser.add_argument("--api-key", required=True)
parser.add_argument("--model", default="Qwen/Qwen3-8B")
parser.add_argument("--data", type=Path, default=Path("data/math500_subset100.jsonl"))
parser.add_argument("--out", type=Path, default=Path("eval/results/qwen3-8b_math500_subset100.jsonl"))
parser.add_argument("--max-tokens", type=int, default=30000)
parser.add_argument("--concurrency", type=int, default=100)
parser.add_argument("--seed", type=int, default=0)
args = parser.parse_args()

# Qwen3 recommended sampling for thinking mode.
SAMPLING = dict(temperature=0.6, top_p=0.95, extra_body={"top_k": 20, "min_p": 0.0})
PROMPT = "{problem}\n\nPlease reason step by step, and put your final answer within \\boxed{{}}."

client = AsyncOpenAI(base_url=f"{args.base_url}/v1", api_key=args.api_key, timeout=3600, max_retries=3)
http = httpx.AsyncClient(base_url=args.base_url, headers={"Authorization": f"Bearer {args.api_key}"}, timeout=120)


async def count_tokens(text: str) -> int:
    r = await http.post("/tokenize", json={"model": args.model, "prompt": text, "add_special_tokens": False})
    r.raise_for_status()
    return r.json()["count"]


async def run_one(row: dict, sem: asyncio.Semaphore) -> dict:
    async with sem:
        resp = await client.chat.completions.create(
            model=args.model,
            messages=[{"role": "user", "content": PROMPT.format(problem=row["problem"])}],
            max_tokens=args.max_tokens,
            seed=args.seed,
            **SAMPLING,
        )
    msg = resp.choices[0].message
    reasoning = getattr(msg, "reasoning_content", None) or getattr(msg, "reasoning", None) or ""
    return {
        "unique_id": row["unique_id"],
        "level": row["level"],
        "subject": row["subject"],
        "answer": row["answer"],
        "reasoning": reasoning,
        "content": msg.content,
        "finish_reason": resp.choices[0].finish_reason,
        "completion_tokens": resp.usage.completion_tokens,
        "thinking_tokens": await count_tokens(reasoning) if reasoning else 0,
    }


async def main():
    rows = [json.loads(line) for line in args.data.open()]
    sem = asyncio.Semaphore(args.concurrency)
    results = []
    for coro in asyncio.as_completed([run_one(r, sem) for r in rows]):
        res = await coro
        results.append(res)
        print(f"[{len(results)}/{len(rows)}] {res['unique_id']}: {res['thinking_tokens']} thinking tokens ({res['finish_reason']})", flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as f:
        for res in sorted(results, key=lambda r: r["unique_id"]):
            f.write(json.dumps(res) + "\n")

    lens = [r["thinking_tokens"] for r in results]
    truncated = sum(r["finish_reason"] == "length" for r in results)
    print(f"\nn={len(lens)}  mean thinking tokens={statistics.mean(lens):.1f}  "
          f"median={statistics.median(lens):.0f}  stdev={statistics.stdev(lens):.1f}  "
          f"min={min(lens)}  max={max(lens)}  truncated={truncated}")
    by_level = {}
    for r in results:
        by_level.setdefault(r["level"], []).append(r["thinking_tokens"])
    for lvl in sorted(by_level):
        print(f"  level {lvl}: n={len(by_level[lvl])}  mean={statistics.mean(by_level[lvl]):.1f}")


asyncio.run(main())
