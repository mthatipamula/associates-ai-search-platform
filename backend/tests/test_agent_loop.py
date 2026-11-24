"""Exercise the LLM agent loop with a stubbed model and toolbox (no network)."""

import os
import sys
from pathlib import Path
from types import SimpleNamespace as NS

os.environ.setdefault("EMBED_PROVIDER", "hash")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import agent  # noqa: E402
from app.security import User  # noqa: E402


def test_llm_agent_loop_runs_tools_then_answers(monkeypatch):
    replies = iter([
        NS(stop_reason="tool_use", content=[
            NS(type="tool_use", id="t1", name="find_experts", input={"topic": "pricing"}),
        ]),
        NS(stop_reason="end_turn", content=[NS(type="text", text="Ask Leila Haddad [KP-00052].")]),
    ])
    sent = []

    def fake_create(**kw):
        sent.append(kw)
        return next(replies)

    monkeypatch.setattr(agent, "create_message", fake_create)
    monkeypatch.setattr(agent.Toolbox, "find_experts",
                        lambda self, topic, industry=None: {"experts": [{"name": "Leila Haddad"}]})

    out = agent.run_llm_agent("who knows pricing?", User("associate", ("all-staff",)))

    assert out["answer"] == "Ask Leila Haddad [KP-00052]."
    assert [t["tool"] for t in out["trace"]] == ["find_experts"]
    tool_result = sent[1]["messages"][-1]["content"][0]
    assert tool_result["type"] == "tool_result" and tool_result["tool_use_id"] == "t1"
    assert tool_result["is_error"] is False


def test_toolbox_rejects_private_methods():
    tb = agent.Toolbox(User("associate", ("all-staff",)))
    assert "error" in tb.call("_validated_filters", {})
    assert "error" in tb.call("call", {})
