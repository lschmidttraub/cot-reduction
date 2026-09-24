"""Score GSM8K final answers in result JSONL files against the reference answers.

The final answer is the number on the last `#### ...` line, falling back to the last \\boxed{...}
(some prompts ask for \\boxed{}, and models sometimes use it anyway). Answers are compared numerically.
"""
import argparse
import json
import re
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("runs", nargs="+", type=Path)
parser.add_argument("--common", action="store_true", help="only score problems present in every run")
args = parser.parse_args()


def last_boxed(s: str) -> str | None:
    i = s.rfind("\\boxed{")
    if i < 0:
        return None
    j = k = i + len("\\boxed{")
    depth = 1
    while k < len(s) and depth:
        depth += {"{": 1, "}": -1}.get(s[k], 0)
        k += 1
    return s[j:k - 1]


def final_answer(content: str) -> float | None:
    hashes = re.findall(r"####\s*(.+)", content or "")
    text = hashes[-1] if hashes else last_boxed(content or "")
    number = re.search(r"-?\d[\d,]*(?:\.\d+)?|-?\.\d+", text or "")
    return float(number.group().replace(",", "")) if number else None


runs = {p.stem: {r["unique_id"]: r for r in map(json.loads, p.open())} for p in args.runs}
ids = set.intersection(*(set(r) for r in runs.values())) if args.common else None
for name, run in runs.items():
    rows = [run[i] for i in sorted(ids)] if ids is not None else list(run.values())
    correct = sum(final_answer(r["content"]) == float(r["answer"]) for r in rows)
    n_hash = sum(bool(re.search(r"####\s*\S", r["content"] or "")) for r in rows)
    print(f"{name:55s} n={len(rows):3d}  correct={correct:3d} ({100 * correct / len(rows):.0f}%)  used ####={n_hash}")
