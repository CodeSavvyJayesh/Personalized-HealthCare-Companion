"""Conversation memory.

Before: `/chat` sent the system prompt plus the single current message.
The companion had no idea what was said one turn earlier — every message
started a brand new relationship. For a mental health companion that is
the single worst product flaw, because the entire value proposition is
continuity.

Now, two layers:

1. **Short term** — the last N turns are replayed verbatim.
2. **Long term** — once the conversation is longer than the window, the
   older turns are compressed into a rolling summary stored on the session
   document and injected as context. Cost stays bounded, continuity does
   not.

The summary is deliberately factual and short; it is context for the model,
not a clinical note.
"""

from __future__ import annotations

import logging

from config import settings
from llm import LLMUnavailable, chat

log = logging.getLogger(__name__)

SUMMARY_PROMPT = """Summarise the conversation below into at most 6 short
bullet points that a supportive companion would need in order to continue
naturally. Capture: what the person is dealing with, what they have already
tried, what they said helps, and anything they asked you to remember.

Do not diagnose. Do not add advice. Do not invent details. Write only the
bullets.

Conversation:
{transcript}"""


def build_messages(
    system_prompt: str,
    history: list[dict],
    current_message: str,
    summary: str | None = None,
) -> list[dict[str, str]]:
    """Assemble the payload sent to the model."""
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]

    if summary:
        messages.append(
            {
                "role": "system",
                "content": (
                    "Context from earlier in your conversation with this "
                    f"person:\n{summary}"
                ),
            }
        )

    window = history[-(settings.CHAT_WINDOW_TURNS * 2) :]
    for msg in window:
        role = "assistant" if msg.get("sender") == "bot" else "user"
        text = (msg.get("text") or "").strip()
        if text:
            messages.append({"role": role, "content": text})

    messages.append({"role": "user", "content": current_message})
    return messages


def _transcript(messages: list[dict]) -> str:
    lines = []
    for msg in messages:
        who = "Companion" if msg.get("sender") == "bot" else "Person"
        lines.append(f"{who}: {(msg.get('text') or '').strip()}")
    return "\n".join(lines)


def maybe_summarise(
    sessions_collection,
    session_id: str,
    history: list[dict],
    existing_summary: str | None,
) -> str | None:
    """Compress everything older than the live window into a summary.

    Returns the (possibly updated) summary. Never raises: if summarisation
    fails the conversation simply keeps its short-term window.
    """
    if len(history) < settings.SUMMARISE_AFTER_TURNS:
        return existing_summary

    older = history[: -(settings.CHAT_WINDOW_TURNS * 2)]
    if not older:
        return existing_summary

    transcript = _transcript(older)[-6000:]
    if existing_summary:
        transcript = f"Previous summary:\n{existing_summary}\n\n{transcript}"

    try:
        summary = chat(
            [{"role": "user", "content": SUMMARY_PROMPT.format(transcript=transcript)}],
            temperature=0.3,
            max_tokens=300,
            timeout=30,
        )
    except LLMUnavailable:
        return existing_summary

    try:
        from bson import ObjectId

        sessions_collection.update_one(
            {"_id": ObjectId(session_id)},
            {"$set": {"summary": summary, "summary_turns": len(history)}},
        )
    except Exception as exc:
        log.warning("Could not persist summary: %s", exc)

    return summary


def load_summary(sessions_collection, session_id: str) -> str | None:
    try:
        from bson import ObjectId

        doc = sessions_collection.find_one({"_id": ObjectId(session_id)})
        return (doc or {}).get("summary")
    except Exception:
        return None
