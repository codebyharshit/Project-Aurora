"""Provider-neutral LLM layer used by every agent.

AURORA_PROVIDER=openai (default) or anthropic. Agents pass content blocks in one
neutral shape ({"type": "text"|"image"|"document", ...}); this module converts them.

Two roles:
- "plan": reasoning agents (Investigator, Plan B, planner explanations, playbook synthesis)
- "exec": execution agents (Document Reader, triage, supplier comms, briefing)
Model per role comes from .env, so swapping models never touches agent code.
"""
from __future__ import annotations

import json
import os
from typing import Any

import aurora.config  # noqa: F401  (loads .env before settings are read)

PROVIDER = os.environ.get("AURORA_PROVIDER", "openai").lower()

MODELS = {
    "openai": {
        "plan": os.environ.get("OPENAI_PLAN_MODEL", ""),
        "exec": os.environ.get("OPENAI_EXEC_MODEL", ""),
    },
    "anthropic": {
        "plan": os.environ.get("AURORA_PLAN_MODEL", "claude-fable-5-1"),
        "exec": os.environ.get("AURORA_EXEC_MODEL", "claude-opus-5-5"),
    },
}

_clients: dict[str, Any] = {}


class LLMUnavailable(RuntimeError):
    pass


def _client():  # noqa: D401
    if PROVIDER in _clients:
        return _clients[PROVIDER]
    if PROVIDER == "openai":
        if not os.environ.get("OPENAI_API_KEY"):
            raise LLMUnavailable("Set OPENAI_API_KEY in .env to enable the reasoning agents.")
        from openai import OpenAI
        _clients[PROVIDER] = OpenAI(max_retries=4)
    else:
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            raise LLMUnavailable("Set ANTHROPIC_API_KEY in .env to enable the reasoning agents.")
        import anthropic
        _clients[PROVIDER] = anthropic.Anthropic(max_retries=4)
    return _clients[PROVIDER]


def available() -> bool:
    try:
        _client()
        return bool(model("exec"))
    except LLMUnavailable:
        return False


def model(role: str) -> str:
    m = MODELS[PROVIDER][role]
    if not m:
        raise LLMUnavailable(f"Set OPENAI_{role.upper()}_MODEL in .env (see `python -m aurora.cli models`).")
    return m


# ---- OpenAI ------------------------------------------------------------------
def _to_openai(content: list[dict] | str) -> list[dict] | str:
    if isinstance(content, str):
        return content
    parts = []
    for b in content:
        if b["type"] == "text":
            parts.append({"type": "text", "text": b["text"]})
        elif b["type"] == "image":
            src = b["source"]
            parts.append({"type": "image_url",
                          "image_url": {"url": f"data:{src['media_type']};base64,{src['data']}", "detail": "high"}})
        elif b["type"] == "document":
            src = b["source"]
            parts.append({"type": "file", "file": {"filename": b.get("title", "document.pdf"),
                                                   "file_data": f"data:{src['media_type']};base64,{src['data']}"}})
    return parts


def _openai_call(system: str, content, role: str, effort: str, schema: dict | None, max_tokens: int) -> str:
    kwargs: dict[str, Any] = {
        "model": model(role),
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": _to_openai(content)}],
        "max_completion_tokens": max_tokens,
    }
    if os.environ.get("OPENAI_REASONING", "1") == "1":
        kwargs["reasoning_effort"] = effort
    if schema:
        kwargs["response_format"] = {"type": "json_schema",
                                     "json_schema": {"name": "result", "schema": schema, "strict": True}}
    try:
        resp = _client().chat.completions.create(**kwargs)
    except Exception as e:  # models without reasoning support reject reasoning_effort
        if "reasoning_effort" in kwargs and "reasoning" in str(e).lower():
            kwargs.pop("reasoning_effort")
            resp = _client().chat.completions.create(**kwargs)
        else:
            raise
    choice = resp.choices[0]
    if getattr(choice.message, "refusal", None):
        raise RuntimeError(f"Model declined: {choice.message.refusal}")
    if choice.finish_reason == "length":
        raise RuntimeError("Output truncated; raise max_tokens for this call.")
    return choice.message.content or ""


# ---- Anthropic -----------------------------------------------------------------
def _anthropic_call(system: str, content, role: str, effort: str, schema: dict | None, max_tokens: int) -> str:
    output_config: dict[str, Any] = {"effort": effort}
    if schema:
        output_config["format"] = {"type": "json_schema", "schema": schema}
    resp = _client().beta.messages.create(
        model=model(role), max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": content}],
        output_config=output_config,
        betas=["server-side-fallback-2026-07-01"], fallbacks="default",
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"Model declined: {getattr(resp.stop_details, 'category', None)}")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("Output truncated; raise max_tokens for this call.")
    return "".join(b.text for b in resp.content if b.type == "text")


def _call(**kw) -> str:
    return (_openai_call if PROVIDER == "openai" else _anthropic_call)(**kw)


def structured(*, system: str, content: list[dict] | str, schema: dict, effort: str = "medium",
               max_tokens: int = 16000, role: str = "exec") -> dict[str, Any]:
    """One call that must return JSON matching `schema`."""
    return json.loads(_call(system=system, content=content, role=role, effort=effort,
                            schema=schema, max_tokens=max_tokens))


def text(*, system: str, content: list[dict] | str, effort: str = "medium", max_tokens: int = 8000,
         role: str = "exec") -> str:
    """One call returning prose (briefs, emails)."""
    return _call(system=system, content=content, role=role, effort=effort, schema=None, max_tokens=max_tokens)


def tool_loop(*, system: str, user: str, tools: list[dict], submit: dict, role: str = "plan",
              effort: str = "medium", max_steps: int = 12, on_step=None) -> tuple[dict, list[dict]]:
    """Agent loop: the model chooses tools until it calls `submit` with its structured answer.

    tools: [{"name", "description", "parameters" (JSON schema), "fn" (callable(**args) -> any)}]
    submit: {"name", "description", "parameters"} — calling it ends the loop.
    Returns (submitted_args, trace) where trace lists every tool call and a short result.
    """
    if PROVIDER != "openai":
        raise NotImplementedError("tool_loop is implemented for the OpenAI provider")
    specs = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                               "parameters": t["parameters"]}} for t in tools]
    specs.append({"type": "function", "function": {"name": submit["name"], "description": submit["description"],
                                                   "parameters": submit["parameters"], "strict": True}})
    by_name = {t["name"]: t["fn"] for t in tools}
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    reasoning = effort if os.environ.get("OPENAI_REASONING", "1") == "1" else None
    trace: list[dict] = []
    for step in range(max_steps):
        kwargs: dict[str, Any] = {"model": model(role), "messages": messages, "tools": specs,
                                  "max_completion_tokens": 8000}
        if reasoning:
            kwargs["reasoning_effort"] = reasoning
        if step == max_steps - 1:
            kwargs["tool_choice"] = {"type": "function", "function": {"name": submit["name"]}}
        try:
            resp = _client().chat.completions.create(**kwargs)
        except Exception as e:  # some models refuse tools + reasoning on this endpoint
            if "reasoning_effort" not in str(e):
                raise
            reasoning = "none"
            kwargs["reasoning_effort"] = reasoning
            resp = _client().chat.completions.create(**kwargs)
        msg = resp.choices[0].message
        calls = msg.tool_calls or []
        messages.append({"role": "assistant", "content": msg.content or "",
                         "tool_calls": [c.model_dump() for c in calls] or None})
        if not calls:
            messages.append({"role": "user", "content": f"When you know enough, call {submit['name']}."})
            continue
        for c in calls:
            args = json.loads(c.function.arguments or "{}")
            if c.function.name == submit["name"]:
                trace.append({"tool": "submit", "args": {}})
                return args, trace
            try:
                result = by_name[c.function.name](**args)
            except Exception as e:  # tools never crash the agent; it sees the error and adapts
                result = {"error": str(e)}
            text = json.dumps(result, ensure_ascii=False, default=str)[:6000]
            trace.append({"tool": c.function.name, "args": args, "result_preview": text[:300]})
            if on_step:
                on_step(c.function.name, args)
            messages.append({"role": "tool", "tool_call_id": c.id, "content": text})
    raise RuntimeError("Investigator did not submit findings")
