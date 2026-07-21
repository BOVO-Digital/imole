"""Normalise les payloads Cursor / OpenAI pour Imọlẹ (gpt-5.6-*)."""

from __future__ import annotations

import copy
import hashlib
from typing import Any

# Imole / Azure OpenAI : tool_call.id max 64 chars (Cursor envoie souvent ~80+)
MAX_TOOL_CALL_ID_LEN = 64


def sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(payload)

    if isinstance(out.get("tools"), list):
        out["tools"] = _sanitize_tools(out["tools"])
        if not out["tools"]:
            out.pop("tools", None)
            if out.get("tool_choice") not in (None, "none"):
                out.pop("tool_choice", None)

    if "tool_choice" in out:
        out["tool_choice"] = _sanitize_tool_choice(out["tool_choice"])

    id_map: dict[str, str] = {}
    if isinstance(out.get("messages"), list):
        out["messages"] = _sanitize_messages(out["messages"], id_map)
    if isinstance(out.get("input"), list):
        out["input"] = _sanitize_responses_input(out["input"], id_map)

    return out


def _short_tool_call_id(original: str, id_map: dict[str, str]) -> str:
    if original in id_map:
        return id_map[original]
    if len(original) <= MAX_TOOL_CALL_ID_LEN:
        id_map[original] = original
        return original
    digest = hashlib.sha256(original.encode("utf-8")).hexdigest()[:40]
    short = f"call_{digest}"  # 45 chars <= 64
    id_map[original] = short
    return short


def _sanitize_messages(
    messages: list[Any], id_map: dict[str, str]
) -> list[Any]:
    cleaned: list[Any] = []
    for msg in messages:
        if not isinstance(msg, dict):
            cleaned.append(msg)
            continue
        m = dict(msg)

        tool_calls = m.get("tool_calls")
        if isinstance(tool_calls, list):
            fixed_calls = []
            for call in tool_calls:
                if not isinstance(call, dict):
                    continue
                c = dict(call)
                call_id = c.get("id")
                if isinstance(call_id, str) and call_id:
                    c["id"] = _short_tool_call_id(call_id, id_map)
                fixed_calls.append(c)
            m["tool_calls"] = fixed_calls

        tool_call_id = m.get("tool_call_id")
        if isinstance(tool_call_id, str) and tool_call_id:
            m["tool_call_id"] = _short_tool_call_id(tool_call_id, id_map)

        cleaned.append(m)
    return cleaned


def _sanitize_responses_input(
    items: list[Any], id_map: dict[str, str]
) -> list[Any]:
    cleaned: list[Any] = []
    for item in items:
        if not isinstance(item, dict):
            cleaned.append(item)
            continue
        it = dict(item)
        for key in ("call_id", "id"):
            val = it.get(key)
            if isinstance(val, str) and len(val) > MAX_TOOL_CALL_ID_LEN:
                # call_id Responses API a souvent une limite proche ; on aligne
                if key == "call_id" or str(it.get("type", "")).endswith(
                    "tool_call"
                ):
                    it[key] = _short_tool_call_id(val, id_map)
        cleaned.append(it)
    return cleaned


def _sanitize_tools(tools: list[Any]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        fixed = _sanitize_one_tool(tool)
        if fixed is not None:
            cleaned.append(fixed)
    return cleaned


def _sanitize_one_tool(tool: dict[str, Any]) -> dict[str, Any] | None:
    t = str(tool.get("type") or "").lower()

    # Function tool classique
    if t == "function" or ("function" in tool and t in ("", "function")):
        fn = tool.get("function")
        if isinstance(fn, dict) and fn.get("name"):
            return {
                "type": "function",
                "function": {
                    "name": fn["name"],
                    "description": fn.get("description") or "",
                    "parameters": fn.get("parameters")
                    if isinstance(fn.get("parameters"), dict)
                    else {"type": "object", "properties": {}},
                    **(
                        {"strict": fn["strict"]}
                        if isinstance(fn.get("strict"), bool)
                        else {}
                    ),
                },
            }
        # Format plat: {type:function, name, description, parameters}
        if tool.get("name"):
            return {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description") or "",
                    "parameters": tool.get("parameters")
                    if isinstance(tool.get("parameters"), dict)
                    else {"type": "object", "properties": {}},
                },
            }
        return None

    # Custom tool — Imole/Azure exige tools[n].custom.{name,...}
    if t == "custom":
        custom = tool.get("custom")
        if isinstance(custom, dict) and custom.get("name"):
            body: dict[str, Any] = {"name": custom["name"]}
            if custom.get("description"):
                body["description"] = custom["description"]
            format_value = _sanitize_custom_format(custom.get("format"))
            if format_value is not None:
                body["format"] = format_value
            return {"type": "custom", "custom": body}

        # Format plat Responses/Cursor: {type:custom, name, description, format}
        if tool.get("name"):
            body = {"name": tool["name"]}
            if tool.get("description"):
                body["description"] = tool["description"]
            format_value = _sanitize_custom_format(tool.get("format"))
            if format_value is not None:
                body["format"] = format_value
            return {"type": "custom", "custom": body}

        # type=custom sans name → drop (évite model_validation_failed)
        return None

    # Tools Cursor / MCP / divers → tenter conversion en function
    name = tool.get("name") or (
        tool.get("function", {}).get("name")
        if isinstance(tool.get("function"), dict)
        else None
    )
    if name:
        params = tool.get("parameters") or tool.get("input_schema") or {
            "type": "object",
            "properties": {},
        }
        if not isinstance(params, dict):
            params = {"type": "object", "properties": {}}
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": tool.get("description") or "",
                "parameters": params,
            },
        }

    # Types internes non supportés (collaboration, tool_search, etc.) → drop
    return None


def _sanitize_custom_format(format_value: Any) -> dict[str, Any] | None:
    """Convertit le format Cursor plat vers le format OpenAI/Imole."""
    if not isinstance(format_value, dict):
        return None

    format_type = str(format_value.get("type") or "").lower()
    if format_type == "text":
        return {"type": "text"}

    if format_type == "grammar":
        grammar = format_value.get("grammar")
        if isinstance(grammar, dict):
            syntax = grammar.get("syntax")
            definition = grammar.get("definition")
        else:
            syntax = format_value.get("syntax")
            definition = format_value.get("definition")

        if syntax in {"lark", "regex"} and isinstance(definition, str):
            return {
                "type": "grammar",
                "grammar": {
                    "syntax": syntax,
                    "definition": definition,
                },
            }

        # Un format grammar incomplet ne doit pas faire échouer toute la requête.
        return {"type": "text"}

    return None


def _sanitize_tool_choice(choice: Any) -> Any:
    if not isinstance(choice, dict):
        return choice

    t = str(choice.get("type") or "").lower()
    if t == "function":
        fn = choice.get("function")
        if isinstance(fn, dict) and fn.get("name"):
            return {"type": "function", "function": {"name": fn["name"]}}
        if choice.get("name"):
            return {"type": "function", "function": {"name": choice["name"]}}
        return "auto"

    if t == "custom":
        custom = choice.get("custom")
        if isinstance(custom, dict) and custom.get("name"):
            return {"type": "custom", "custom": {"name": custom["name"]}}
        if choice.get("name"):
            return {"type": "custom", "custom": {"name": choice["name"]}}
        return "auto"

    return choice
