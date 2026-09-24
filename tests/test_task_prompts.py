import pytest

import cybench_hackable as task_mod
import make_cybench_hackable as build


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("build")
    build.build(out)
    return out


@pytest.fixture(autouse=True)
def acknowledge(monkeypatch):
    monkeypatch.setenv("CYBENCH_ACKNOWLEDGE_RISKS", "1")


def inputs(built, **kwargs) -> dict[str, str]:
    t = task_mod.cybench_hackable(variant_names=["planted"], data_dir=str(built), **kwargs)
    return {s.id: s.input for s in t.dataset}


def test_assistant_prompt_drops_only_the_narrate_tool_calls_line():
    assert "Do some reasoning before your actions" not in task_mod.ASSISTANT_PROMPT
    assert "Prioritize parallel tool calls" in task_mod.ASSISTANT_PROMPT
    assert task_mod.ASSISTANT_PROMPT.strip().startswith("You are a helpful assistant")


def test_monitor_note_is_last_paragraph_of_task_prompt(built):
    with_note, without = inputs(built, monitor_note=True), inputs(built)
    assert with_note.keys() == without.keys() and len(with_note) == 6
    for sid, prompt in with_note.items():
        assert prompt == without[sid].rstrip("\n") + "\n\n" + task_mod.MONITOR_NOTE + "\n"


def test_no_monitor_note_by_default(built):
    assert all(task_mod.MONITOR_NOTE not in p for p in inputs(built).values())
