"""
LLM provider for the Copilot Agent — provider-swappable via COPILOT_LLM_PROVIDER.
Implements Mistral (OpenAI-compatible chat completions) and Google Gemini
(native REST), both with function/tool-calling. No SDK dependency; httpx only.
"""
import json

import httpx

from app.config import settings

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
MISTRAL_BASE = "https://api.mistral.ai/v1"


class LLMUnavailable(Exception):
    """Raised when no LLM provider is configured — callers should fall back."""


def llm_available() -> bool:
    if settings.COPILOT_LLM_PROVIDER == "mistral":
        return bool(settings.MISTRAL_API_KEY)
    if settings.COPILOT_LLM_PROVIDER == "gemini":
        return bool(settings.GEMINI_API_KEY)
    return False


def _to_gemini_contents(messages: list[dict]) -> list[dict]:
    """Convert generic chat messages to Gemini `contents` format.

    Supported message shapes:
      {"role": "user"|"assistant", "content": str}
      {"role": "assistant", "tool_call": {"name": str, "args": dict}}
      {"role": "tool", "name": str, "result": dict}
    """
    contents = []
    for m in messages:
        if m["role"] == "tool":
            contents.append({
                "role": "user",
                "parts": [{"functionResponse": {"name": m["name"], "response": {"result": m["result"]}}}],
            })
        elif m["role"] == "assistant" and "tool_call" in m:
            contents.append({
                "role": "model",
                "parts": [{"functionCall": {"name": m["tool_call"]["name"], "args": m["tool_call"]["args"]}}],
            })
        else:
            role = "model" if m["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})
    return contents


async def chat(
    messages: list[dict],
    system: str = "",
    tools: list[dict] | None = None,
    temperature: float = 0.2,
) -> dict:
    """Run one LLM turn. Returns {"content": str|None, "tool_call": {"name", "args"}|None}.

    `tools` is a list of function declarations:
      {"name": ..., "description": ..., "parameters": {JSON schema}}
    """
    if not llm_available():
        raise LLMUnavailable("No LLM provider configured (set MISTRAL_API_KEY or GEMINI_API_KEY).")

    if settings.COPILOT_LLM_PROVIDER == "mistral":
        return await _chat_mistral(messages, system, tools, temperature)
    return await _chat_gemini(messages, system, tools, temperature)


# ── Mistral (OpenAI-compatible) ─────────────────────────────────────────
_TOOL_CALL_ID = "copilot001"  # Mistral requires a 9+ char alphanumeric id per call


def _to_mistral_messages(messages: list[dict], system: str) -> list[dict]:
    out: list[dict] = []
    if system:
        out.append({"role": "system", "content": system})
    for m in messages:
        if m["role"] == "tool":
            out.append({
                "role": "tool",
                "name": m["name"],
                "content": json.dumps(m["result"]),
                "tool_call_id": _TOOL_CALL_ID,
            })
        elif m["role"] == "assistant" and "tool_call" in m:
            out.append({
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": _TOOL_CALL_ID,
                    "type": "function",
                    "function": {
                        "name": m["tool_call"]["name"],
                        "arguments": json.dumps(m["tool_call"]["args"]),
                    },
                }],
            })
        else:
            out.append({"role": m["role"], "content": m["content"]})
    return out


async def _chat_mistral(messages: list[dict], system: str, tools: list[dict] | None, temperature: float) -> dict:
    body: dict = {
        "model": settings.MISTRAL_MODEL,
        "messages": _to_mistral_messages(messages, system),
        "temperature": temperature,
    }
    if tools:
        body["tools"] = [{"type": "function", "function": t} for t in tools]
        body["tool_choice"] = "auto"

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{MISTRAL_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {settings.MISTRAL_API_KEY}", "Content-Type": "application/json"},
            json=body,
        )
        if resp.status_code != 200:
            raise LLMUnavailable(f"Mistral API error ({resp.status_code}): {resp.text[:300]}")
        data = resp.json()

    choices = data.get("choices") or []
    if not choices:
        raise LLMUnavailable(f"Mistral returned no choices: {json.dumps(data)[:300]}")

    msg = choices[0].get("message") or {}
    tool_call = None
    tool_calls = msg.get("tool_calls") or []
    if tool_calls:
        fn = tool_calls[0].get("function") or {}
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        tool_call = {"name": fn.get("name", ""), "args": args}

    content = msg.get("content")
    if isinstance(content, list):  # content-parts variant
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))

    return {"content": (content or "").strip() or None, "tool_call": tool_call}


# ── Gemini (native REST) ─────────────────────────────────────────────────
async def _chat_gemini(messages: list[dict], system: str, tools: list[dict] | None, temperature: float) -> dict:
    body: dict = {
        "contents": _to_gemini_contents(messages),
        "generationConfig": {"temperature": temperature},
    }
    if system:
        body["system_instruction"] = {"parts": [{"text": system}]}
    if tools:
        body["tools"] = [{"function_declarations": tools}]

    url = f"{GEMINI_BASE}/models/{settings.GEMINI_MODEL}:generateContent"
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            url,
            params={"key": settings.GEMINI_API_KEY},
            headers={"Content-Type": "application/json"},
            json=body,
        )
        if resp.status_code != 200:
            raise LLMUnavailable(f"Gemini API error ({resp.status_code}): {resp.text[:300]}")

        data = resp.json()

    candidates = data.get("candidates") or []
    if not candidates:
        raise LLMUnavailable(f"Gemini returned no candidates: {json.dumps(data)[:300]}")

    parts = (candidates[0].get("content") or {}).get("parts") or []
    text_chunks = []
    tool_call = None
    for p in parts:
        if "text" in p:
            text_chunks.append(p["text"])
        elif "functionCall" in p and tool_call is None:
            fc = p["functionCall"]
            tool_call = {"name": fc.get("name", ""), "args": fc.get("args") or {}}

    return {"content": "".join(text_chunks).strip() or None, "tool_call": tool_call}
