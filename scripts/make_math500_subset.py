"""Sample a random subset of MATH-500 prompts and save it as a JSONL dataset."""
import argparse
import json
from pathlib import Path

from datasets import load_dataset

parser = argparse.ArgumentParser()
parser.add_argument("--n", type=int, default=100)
parser.add_argument("--seed", type=int, default=0)
parser.add_argument("--out", type=Path, default=Path("data/math500_subset100.jsonl"))
args = parser.parse_args()

ds = load_dataset("HuggingFaceH4/MATH-500", split="test")
subset = ds.shuffle(seed=args.seed).select(range(args.n))

args.out.parent.mkdir(parents=True, exist_ok=True)
with args.out.open("w") as f:
    for row in subset:
        f.write(json.dumps(row) + "\n")
print(f"wrote {len(subset)} rows to {args.out}")
