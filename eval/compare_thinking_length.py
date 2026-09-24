"""Compare thinking length between two runs of measure_thinking_length.py, paired by problem."""
import argparse
import json
import random
import statistics
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("runs", nargs="+", type=Path, help="result JSONL files; the first is the reference")
parser.add_argument("--bootstrap", type=int, default=10000)
args = parser.parse_args()


def load(path: Path) -> dict:
    return {r["unique_id"]: r for r in map(json.loads, path.open())}


def summary(rows: list[dict]) -> str:
    t = [r["thinking_tokens"] for r in rows]
    trunc = sum(r["finish_reason"] == "length" for r in rows)
    return f"median={statistics.median(t):7.0f}  mean={statistics.mean(t):7.1f}  n={len(t)}  truncated={trunc}"


runs = {p.stem: load(p) for p in args.runs}
ref_name, ref = next(iter(runs.items()))
for name, run in runs.items():
    print(f"{name:55s} {summary(list(run.values()))}")

rng = random.Random(0)
for name, run in list(runs.items())[1:]:
    ids = sorted(set(ref) & set(run))
    diffs = [run[i]["thinking_tokens"] - ref[i]["thinking_tokens"] for i in ids]
    ratios = [run[i]["thinking_tokens"] / ref[i]["thinking_tokens"] for i in ids]
    boot = sorted(
        statistics.median(run[i]["thinking_tokens"] for i in s) - statistics.median(ref[i]["thinking_tokens"] for i in s)
        for s in ([rng.choice(ids) for _ in ids] for _ in range(args.bootstrap))
    )
    lo, hi = boot[int(0.025 * len(boot))], boot[int(0.975 * len(boot))]
    shorter = sum(d < 0 for d in diffs)
    print(f"\n{name} vs {ref_name} (paired, n={len(ids)}):")
    print(f"  difference of medians: {statistics.median(run[i]['thinking_tokens'] for i in ids) - statistics.median(ref[i]['thinking_tokens'] for i in ids):+.0f} tokens "
          f"(95% bootstrap CI [{lo:+.0f}, {hi:+.0f}])")
    print(f"  median per-problem difference: {statistics.median(diffs):+.0f} tokens; median ratio: {statistics.median(ratios):.3f}")
    print(f"  shorter on {shorter}/{len(ids)} problems, longer on {sum(d > 0 for d in diffs)}")
