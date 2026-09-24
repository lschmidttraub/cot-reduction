"""Measure thinking length on a JSONL prompt set via a vLLM OpenAI-compatible server.

The server must run with a reasoning parser (e.g. `--reasoning-parser qwen3` or `gemma4`) so the
thinking text comes back in `reasoning_content`. Thinking length is counted in tokens with the server's /tokenize.
"""
import argparse
import asyncio
import json
import statistics
from pathlib import Path

import httpx
import openai
from openai import AsyncOpenAI

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", required=True, nargs="+",
                    help="e.g. https://<pod>-8000.proxy.runpod.net; with several, requests are spread round-robin")
parser.add_argument("--api-key", required=True)
parser.add_argument("--model", default="Qwen/Qwen3-8B")
parser.add_argument("--data", type=Path, default=Path("data/gsm8k_subset100.jsonl"))
parser.add_argument("--out", type=Path, default=Path("eval/results/qwen3-8b_gsm8k_subset100.jsonl"))
parser.add_argument("--max-tokens", type=int, default=30000)
parser.add_argument("--concurrency", type=int, default=100)
parser.add_argument("--seed", type=int, default=0)
parser.add_argument("--temperature", type=float, default=0.6)
parser.add_argument("--top-p", type=float, default=0.95)
parser.add_argument("--top-k", type=int, default=20)
parser.add_argument("--chat-template-kwargs", type=json.loads, default=None,
                    help='JSON passed to the chat template, e.g. \'{"enable_thinking": true}\' for Gemma 4')
parser.add_argument("--prompt-template", default="{problem}\n\nPlease reason step by step, and put your final answer within \\boxed{}.",
                    help="user prompt; {problem} is replaced with the problem text")
parser.add_argument("--suffix", default="", help="text appended to the end of each prompt, after a blank line")
args = parser.parse_args()

# Defaults are Qwen3's recommended thinking-mode sampling; Gemma 4 uses temperature 1.0, top_k 64.
SAMPLING = dict(temperature=args.temperature, top_p=args.top_p, extra_body={"top_k": args.top_k, "min_p": 0.0})
if args.chat_template_kwargs:
    SAMPLING["extra_body"]["chat_template_kwargs"] = args.chat_template_kwargs

# The timeout bounds each wait for the next streamed chunk, not the whole generation, so a
# connection that dies silently is abandoned (and retried) after 5 minutes instead of hanging.
clients = [AsyncOpenAI(base_url=f"{url}/v1", api_key=args.api_key, timeout=300, max_retries=0) for url in args.base_url]
http = httpx.AsyncClient(base_url=args.base_url[0], headers={"Authorization": f"Bearer {args.api_key}"}, timeout=120)


async def count_tokens(text: str, attempts: int = 10) -> int:
    # Retried separately so a transient proxy error doesn't throw away the finished generation.
    for attempt in range(attempts):
        try:
            r = await http.post("/tokenize", json={"model": args.model, "prompt": text, "add_special_tokens": False})
            r.raise_for_status()
            return r.json()["count"]
        except httpx.HTTPError as e:
            if attempt == attempts - 1:
                raise
            print(f"tokenize retry {attempt + 1}/{attempts}: {e!r}"[:200], flush=True)
            await asyncio.sleep(min(60, 5 * 2**attempt))


async def run_one(row: dict, sem: asyncio.Semaphore, attempts: int = 10) -> dict:
    # Keep --concurrency within what the server can run at once: requests left waiting in vLLM's
    # queue send no bytes, and the Runpod proxy drops connections that stay silent for ~100s.
    for attempt in range(attempts):
        try:
            return await generate(row, sem)
        except (openai.APIConnectionError, openai.APIStatusError) as e:
            print(f"retry {attempt + 1}/{attempts} for {row['unique_id']}: {e!r}"[:200], flush=True)
            await asyncio.sleep(min(60, 5 * 2**attempt))
    raise RuntimeError(f"{row['unique_id']} failed after {attempts} attempts")


async def generate(row: dict, sem: asyncio.Semaphore) -> dict:
    # Stream so the Runpod proxy (~100s idle/response timeout) doesn't cut off long generations.
    reasoning, content, finish_reason, usage = [], [], None, None
    prompt = args.prompt_template.replace("{problem}", row["problem"])
    if args.suffix:
        prompt += "\n\n" + args.suffix
    async with sem:
        stream = await clients[row["server"]].chat.completions.create(
            model=args.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=args.max_tokens,
            seed=args.seed,
            stream=True,
            stream_options={"include_usage": True},
            **SAMPLING,
        )
        async for chunk in stream:
            if chunk.usage:
                usage = chunk.usage
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            reasoning.append(getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None) or "")
            content.append(delta.content or "")
            finish_reason = chunk.choices[0].finish_reason or finish_reason
    reasoning = "".join(reasoning)
    return {
        "unique_id": row["unique_id"],
        "seed": args.seed,
        "subject": row["subject"],
        "answer": row["answer"],
        "prompt": prompt,
        "reasoning": reasoning,
        "content": "".join(content),
        "finish_reason": finish_reason,
        "completion_tokens": usage.completion_tokens if usage else None,
        "thinking_tokens": await count_tokens(reasoning) if reasoning else 0,
    }


async def main():
    rows = [json.loads(line) for line in args.data.open()]
    # Results are appended as they arrive, so an interrupted run resumes where it left off.
    args.out.parent.mkdir(parents=True, exist_ok=True)
    results = [json.loads(line) for line in args.out.open()] if args.out.exists() else []
    done = {r["unique_id"] for r in results}
    todo = [{**r, "server": i % len(clients)} for i, r in enumerate(r for r in rows if r["unique_id"] not in done)]
    print(f"{len(done)} already done, {len(todo)} to run", flush=True)

    sem = asyncio.Semaphore(args.concurrency)
    with args.out.open("a") as f:
        for coro in asyncio.as_completed([run_one(r, sem) for r in todo]):
            res = await coro
            results.append(res)
            f.write(json.dumps(res) + "\n")
            f.flush()
            print(f"[{len(results)}/{len(rows)}] {res['unique_id']}: {res['thinking_tokens']} thinking tokens ({res['finish_reason']})", flush=True)

    lens = [r["thinking_tokens"] for r in results]
    truncated = sum(r["finish_reason"] == "length" for r in results)
    print(f"\nn={len(lens)}  mean thinking tokens={statistics.mean(lens):.1f}  "
          f"median={statistics.median(lens):.0f}  stdev={statistics.stdev(lens):.1f}  "
          f"min={min(lens)}  max={max(lens)}  truncated={truncated}")


asyncio.run(main())
