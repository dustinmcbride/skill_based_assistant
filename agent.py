import logging
from typing import Literal

import anthropic

import memory as memory_module
from config import AGENT_MODEL, MAX_TOKENS, MODE_PROMPTS, SOUL_CONTENT, SYSTEM_PROMPT
from mcp_servers import MCP_SERVERS
from skill_loader import (
    load_skill_instructions,
    select_skill,
)
from skills import dispatch, get_tools
from user_context import UserContext

logger = logging.getLogger(__name__)


_SERVER_SIDE_TYPES = {"server_tool_use", "server_tool_result"}


def _serialize_content(content) -> list[dict]:
    """Convert SDK content blocks (TextBlock, ToolUseBlock, etc.) to plain dicts.

    Filters out server_tool_use and server_tool_result blocks — the API produces
    these for MCP calls but rejects them if sent back in subsequent turns.
    """
    result = []
    for block in content:
        if isinstance(block, dict):
            if block.get("type") in _SERVER_SIDE_TYPES:
                continue
            result.append(block)
        else:
            if getattr(block, "type", None) in _SERVER_SIDE_TYPES:
                continue
            result.append(block.model_dump())
    return result


def build_system_prompt(
    user: "UserContext | None",
    mode: str,
    skill_name: str | None,
    skill_instructions: str | None,
) -> str:
    parts = [SYSTEM_PROMPT]
    if SOUL_CONTENT:
        parts.append(f"\n## Identity\n{SOUL_CONTENT}")
    if user is not None:
        user_section = f"\n## User\nName: {user.display_name}"
        if user.persona:
            user_section += f"\n\n{user.persona}"
        parts.append(user_section)
        if user.cross_channel_summary:
            parts.append(f"\n{user.cross_channel_summary}")
    parts.append(f"\n## Mode\n{MODE_PROMPTS[mode]}")
    if skill_instructions:
        parts.append(f"\n## Active skill: {skill_name}\n\n{skill_instructions}")
    return "\n".join(parts)


def run(
    history: list[dict],
    user: "UserContext | None",
    mode: Literal["command", "chat"],
) -> tuple[str, str | None, list[str]]:
    """
    Run the agentic loop.

    Returns:
        (response_text, skill_name_or_None, list_of_actions_taken)

    Mutates history in place.
    """
    # Extract last user message for routing
    last_user_msg = ""
    for msg in reversed(history):
        if msg.get("role") == "user":
            content = msg["content"]
            if isinstance(content, str):
                last_user_msg = content
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        last_user_msg = block["text"]
                        break
            break

    # Route to skill — check user override first, then global
    skill_name = select_skill(last_user_msg)
    skill_instructions = load_skill_instructions(skill_name) if skill_name else None

    system = build_system_prompt(user, mode, skill_name, skill_instructions)
    tools = get_tools()
    client = anthropic.Anthropic()

    actions_taken: list[str] = []

    # Trim history before sending to stay within context
    working_history = memory_module.trim(list(history))

    max_iterations = 25
    iteration = 0
    while True:
        iteration += 1
        if iteration > max_iterations:
            logger.warning("Agent loop hit max_iterations=%d, breaking", max_iterations)
            return "", skill_name, actions_taken
        kwargs: dict = dict(
            model=AGENT_MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            tools=tools,
            messages=working_history,
        )
        if MCP_SERVERS:
            kwargs["mcp_servers"] = MCP_SERVERS
            kwargs["betas"] = ["mcp-client-2025-04-04"]
            response = client.beta.messages.create(**kwargs)
        else:
            response = client.messages.create(**kwargs)

        logger.info("LLM usage: model=%s input_tokens=%d output_tokens=%d", AGENT_MODEL, response.usage.input_tokens, response.usage.output_tokens)

        # Append assistant turn to both histories (serialize SDK objects to plain dicts)
        assistant_turn = {"role": "assistant", "content": _serialize_content(response.content)}
        working_history.append(assistant_turn)
        history.append(assistant_turn)

        if response.stop_reason == "end_turn":
            text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    text = block.text
                    break
            logger.info("Agent end_turn: %s", text[:500] if text else "(no text)")
            return text, skill_name, actions_taken

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                actions_taken.append(block.name)
                logger.info("Tool call: %s(%s)", block.name, block.input)
                try:
                    result = dispatch(block.name, block.input)
                except Exception as e:
                    result = f"Error running {block.name}: {e}"
                logger.info("Tool result [%s]: %s", block.name, str(result)[:500])
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    }
                )

            tool_turn = {"role": "user", "content": tool_results}
            working_history.append(tool_turn)
            history.append(tool_turn)
            continue

        # Unexpected stop reason — return whatever text we have
        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text = block.text
                break
        return text, skill_name, actions_taken
