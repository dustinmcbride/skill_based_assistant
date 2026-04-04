from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import os
import re

from skills import register

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")

client = WebClient(token=SLACK_BOT_TOKEN)

_user_cache: dict[str, str] = {}


def _resolve_user_id(user_id: str) -> str:
    """Return a display name for a Slack user ID, falling back to the raw ID."""
    if user_id in _user_cache:
        return _user_cache[user_id]
    try:
        resp = client.users_info(user=user_id)
        profile = resp["user"].get("profile", {})
        name = profile.get("display_name") or profile.get("real_name") or user_id
        _user_cache[user_id] = name
        return name
    except SlackApiError:
        return user_id


def resolve_mentions(text: str) -> str:
    """Replace <@UID> mention tokens with the user's display name."""
    def _replace(m: re.Match) -> str:
        return f"@{_resolve_user_id(m.group(1))}"
    return re.sub(r"<@([A-Z0-9]+)>", _replace, text)


@register
def send_slack_message(channel: str, text: str) -> str:
    """Send a message to a Slack channel (e.g. #general)."""
    try:
        response = client.chat_postMessage(channel=channel, text=text)
        return response["ts"]
    except SlackApiError as e:
        return f"Error: {e.response['error']}"


@register
def list_slack_users() -> str:
    """List all active users in the Slack workspace with their display name and user ID."""
    try:
        members = []
        cursor = None
        while True:
            kwargs = {"limit": 200}
            if cursor:
                kwargs["cursor"] = cursor
            response = client.users_list(**kwargs)
            for member in response["members"]:
                if member.get("deleted") or member.get("is_bot") or member["id"] == "USLACKBOT":
                    continue
                profile = member.get("profile", {})
                name = profile.get("display_name") or profile.get("real_name") or member["name"]
                members.append(f"{name} (id: {member['id']})")
            cursor = response.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
        return "\n".join(members)
    except SlackApiError as e:
        return f"Error: {e.response['error']}"


@register
def send_slack_dm(user_id: str, text: str) -> str:
    """Send a direct message to a Slack user by their user ID."""
    try:
        conv = client.conversations_open(users=user_id)
        channel_id = conv["channel"]["id"]
        response = client.chat_postMessage(channel=channel_id, text=text)
        return response["ts"]
    except SlackApiError as e:
        return f"Error: {e.response['error']}"
