"""Normalise les payloads Cursor / OpenAI pour Imọlẹ (gpt-5.6-*)."""

from __future__ import annotations

import copy
from typing import Any


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

    return out


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
            if isinstance(custom.get("format"), dict):
                body["format"] = custom["format"]
            return {"type": "custom", "custom": body}

        # Format plat Responses/Cursor: {type:custom, name, description, format}
        if tool.get("name"):
            body = {"name": tool["name"]}
            if tool.get("description"):
                body["description"] = tool["description"]
            if isinstance(tool.get("format"), dict):
                body["format"] = tool["format"]
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
