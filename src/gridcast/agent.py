"""Agent loop: the model calls tools until it has enough to answer."""

import json
import os
from datetime import UTC, datetime

import anthropic
from dotenv import load_dotenv

from gridcast.tools import DISPATCH, TOOLS

load_dotenv()

MODEL = "claude-haiku-4-5-20251001"
MAX_TURNS = 6

SYSTEM_TEMPLATE = """Today is {today}. You answer questions about Belgian
electricity grid load using the tools provided. Measured data ends about 2 hours
behind real time.

Rules:
- Always use a tool. Never answer load questions from your own knowledge.
- Quote numbers with units (MW) and state the period they cover.
- When asked about forecast accuracy, use get_model_info and report the
  confidence interval, not just the point estimate.
- If a tool returns an error, say what went wrong rather than guessing."""


def _strip_descriptions(schema: dict) -> dict:
    """Remove parameter descriptions, keeping names, types and enums."""
    out = {"type": "object", "properties": {}, "required": schema.get("required", [])}
    for name, spec in schema.get("properties", {}).items():
        out["properties"][name] = {
            k: v for k, v in spec.items() if k != "description"
        }
    return out


def run(question: str, verbose: bool = True, degraded: bool = False) -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    messages = [{"role": "user", "content": question}]
    calls = []

    if degraded:
        system = ""
        tools = [
            {"name": t["name"], "description": t["name"],
             "input_schema": _strip_descriptions(t["input_schema"])}
            for t in TOOLS
        ]
    else:
        today = datetime.now(UTC).date().isoformat()
        system = SYSTEM_TEMPLATE.format(today=today)
        tools = TOOLS

    for turn in range(MAX_TURNS):
        resp = client.messages.create(
            model=MODEL,
            max_tokens=1500,
            system=system,
            tools=tools,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason != "tool_use":
            text = "".join(b.text for b in resp.content if b.type == "text")
            return {"answer": text, "tool_calls": calls, "turns": turn + 1}

        results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            calls.append({"name": block.name, "input": block.input})
            if verbose:
                print(f"  -> {block.name}({block.input})")
            try:
                out = DISPATCH[block.name](**block.input)
                is_error = "error" in out
            except Exception as e:  # tool errors are returned to the model
                out, is_error = {"error": str(e)}, True
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(out)[:20000],
                "is_error": is_error,
            })
        messages.append({"role": "user", "content": results})

    return {"answer": "Stopped: too many tool calls.", "tool_calls": calls,
            "turns": MAX_TURNS}


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "What was peak load last February?"
    r = run(q)
    print("\n" + r["answer"])
    print(f"\n[{r['turns']} turns, {len(r['tool_calls'])} tool calls]")
