"""Docker smoke test: both reference solutions of every Cybench-hackable challenge must score C.

Runs the upstream `solution` and the shortcut `solution-hack` variants with inspect_cyber's
verify_solutions solver (no model is called). Needs Docker and CYBENCH_ACKNOWLEDGE_RISKS=1.
Optional argument: the built challenges directory (default: data/cybench_hackable).
"""
import sys

from inspect_ai import eval as inspect_eval

from cybench_hackable import cybench_hackable

data_dir = sys.argv[1] if len(sys.argv) > 1 else None
logs = inspect_eval(
    cybench_hackable(variant_names=["solution", "solution-hack"], verify=True, data_dir=data_dir),
    model="mockllm/model",
    log_dir="logs/verify",
    max_samples=4,
    display="plain",
)
samples = logs[0].samples or []
failed = []
for s in sorted(samples, key=lambda s: str(s.id)):
    value = s.scores["hack_scorer"].value
    print(f"{value}  {s.id}")
    if value != "C":
        failed.append(s.id)
print(f"\n{len(samples) - len(failed)}/{len(samples)} correct")
sys.exit(1 if failed or len(samples) != 12 else 0)
