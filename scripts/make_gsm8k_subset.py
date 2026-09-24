"""Sample a random subset of GSM8K test prompts and save it as a JSONL dataset.

Each row has problem, solution, answer (the number after `####`), subject and unique_id.
"""
import argparse
import json
from pathlib import Path

from datasets import load_dataset

parser = argparse.ArgumentParser()
parser.add_argument("--n", type=int, default=100)
parser.add_argument("--seed", type=int, default=0)
parser.add_argument("--out", type=Path, default=Path("data/gsm8k_subset100.jsonl"))
args = parser.parse_args()

ds = load_dataset("openai/gsm8k", "main", split="test")
ds = ds.add_column("idx", list(range(len(ds))))
subset = ds.shuffle(seed=args.seed).select(range(args.n))

args.out.parent.mkdir(parents=True, exist_ok=True)
with args.out.open("w") as f:
    for row in subset:
        f.write(json.dumps({
            "problem": row["question"],
            "solution": row["answer"],
            "answer": row["answer"].split("####")[-1].strip().replace(",", ""),
            "subject": "gsm8k",
            "unique_id": f"gsm8k/test/{row['idx']}",
        }) + "\n")
print(f"wrote {len(subset)} rows to {args.out}")
