import logging

import anthropic

from config import AGENT_MODEL
from user_context import UserContext

logger = logging.getLogger(__name__)

_PREFERRED_CHANNELS = ["telegram", "slack", "email"]


def _get_send_target(recipient: UserContext) -> "tuple[str, str] | None":
    """Return (channel_name, channel_id) to send to.

    Uses recipient.active_channel if it has a configured ID, otherwise
    falls through preferred channel order: telegram → slack → email.
    """
    active_id = recipient.channels.get(recipient.active_channel)
    if active_id:
        return (recipient.active_channel, str(active_id))
    for ch in _PREFERRED_CHANNELS:
        ch_id = recipient.channels.get(ch)
        if ch_id:
            return (ch, str(ch_id))
    return None


def _adapt_to_persona(draft: str, persona: str) -> str:
    """Adapt the draft message tone/style using the recipient's persona via Opus.

    Returns the original draft unchanged if the API call fails.
    """
    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=AGENT_MODEL,
            max_tokens=500,
            system=(
                "You are adapting a message to be delivered to a specific person. "
                "Rewrite the message to match their communication style and preferences. "
                "Output only the rewritten message text, nothing else.\n\n"
                f"{persona}"
            ),
            messages=[{"role": "user", "content": draft}],
        )
        return response.content[0].text
    except Exception as e:
        logger.warning("Persona adaptation failed, using original draft: %s", e)
        return draft


def send_message(recipient: UserContext, draft: str) -> str:
    """
    Central dispatch for all agent-initiated outbound messages.

    Steps:
    1. Adapts tone/style using recipient's persona (Opus call).
    2. Routes to recipient's channel (telegram, slack, etc.).
    3. Logs the sent message to recipient's channel history.

    Returns a human-readable confirmation string.
    This function is NOT called for inline session replies — those go through
    the normal agent return path where the persona is already in the system prompt.
    """
    import memory as memory_module

    adapted = _adapt_to_persona(draft, recipient.persona)

    target = _get_send_target(recipient)
    if target is None:
        return f"Cannot send to {recipient.display_name}: no channel configured."

    channel_name, channel_id = target
    ok = False

    if channel_name == "telegram":
        from skills.telegram import send_message as _telegram_send
        ok = _telegram_send(channel_id, adapted)
    elif channel_name == "slack":
        from skills.slack import send_slack_dm
        result = send_slack_dm(channel_id, adapted)
        ok = not str(result).startswith("Error")
    else:
        return f"Channel '{channel_name}' send not yet implemented."

    if not ok:
        return f"Failed to send message to {recipient.display_name} via {channel_name}."

    hist = memory_module.load(recipient)
    hist.append({"role": "assistant", "content": adapted})
    memory_module.save(hist, recipient)

    return f"Message sent to {recipient.display_name} via {channel_name}."
