"""Crisis detection and escalation.

Design goals, in order:

1. A message signalling imminent risk must NEVER be handed to a generative
   model and hoped over. Tier 3 short-circuits the LLM entirely and returns
   a fixed, reviewed response. Deterministic beats clever here.
2. False negatives cost more than false positives. The classifier is
   deliberately eager; the worst case of over-triggering is that someone is
   shown a helpline they did not need.
3. Every escalation is written to an append-only audit collection, so the
   behaviour of the system is reviewable after the fact.

The tiers:

    Tier 0  NONE      ordinary conversation
    Tier 1  DISTRESS  strong negative affect, no risk language
    Tier 2  IDEATION  passive ideation / self-harm language
    Tier 3  IMMINENT  plan, means, timeframe, or goodbye framing

This is a lexical + contextual classifier, not a clinical instrument. It is
the deterministic floor under the model, not a diagnosis.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum

# --------------------------------------------------------------- resources

HELPLINES: dict[str, list[dict[str, str]]] = {
    "IN": [
        {
            "name": "Tele-MANAS (Govt. of India, 24x7, multilingual)",
            "contact": "14416 or 1-800-891-4416",
        },
        {
            "name": "KIRAN Mental Health Helpline (24x7)",
            "contact": "1800-599-0019",
        },
        {
            "name": "AASRA (24x7)",
            "contact": "+91-9820466726",
        },
        {
            "name": "Emergency services",
            "contact": "112",
        },
    ],
    "US": [
        {"name": "988 Suicide & Crisis Lifeline", "contact": "988"},
        {"name": "Crisis Text Line", "contact": "Text HOME to 741741"},
        {"name": "Emergency services", "contact": "911"},
    ],
    "INTL": [
        {
            "name": "Find a helpline in your country",
            "contact": "https://findahelpline.com",
        },
    ],
}


class RiskTier(IntEnum):
    NONE = 0
    DISTRESS = 1
    IDEATION = 2
    IMMINENT = 3


# --------------------------------------------------------------- lexicons
# Written as word-boundary regexes so "therapist" does not match "rapist"
# and "classic" does not match "cl-ass". Substring matching on this kind of
# lexicon is how naive filters produce nonsense.

_IMMINENT = [
    r"\bkill(ing)?\s+myself\b",
    r"\bend(ing)?\s+(my|it)\s+(life|all)\b",
    r"\btak(e|ing)\s+my\s+own\s+life\b",
    r"\bi\s+(will|am\s+going\s+to|wanna|want\s+to)\s+(die|kill\s+myself)\b",
    r"\bsuicide\s+(note|plan|method)\b",
    r"\bgoodbye\s+(forever|everyone|world)\b",
    r"\bwon'?t\s+be\s+(here|around)\s+(tomorrow|much\s+longer)\b",
    r"\bi\s+have\s+(the\s+)?(pills|rope|gun|blade)\b",
    r"\bjump(ing)?\s+off\b",
    r"\boverdos(e|ing)\b",
    r"\bhang\s+myself\b",
    r"\bslit\s+my\s+wrists?\b",
    r"\btonight\s+is\s+the\s+night\b",
    r"\bno\s+point\s+in\s+living\b",
]

_IDEATION = [
    r"\bsuicid(e|al)\b",
    r"\bself[\s-]?harm\b",
    r"\bcut(ting)?\s+myself\b",
    r"\bhurt(ing)?\s+myself\b",
    r"\bwish\s+i\s+(was|were)\s+dead\b",
    r"\bwant\s+to\s+disappear\b",
    r"\bdon'?t\s+want\s+to\s+(be\s+here|live|wake\s+up)\b",
    r"\bbetter\s+off\s+(without\s+me|dead)\b",
    r"\bnobody\s+would\s+(miss|notice)\s+me\b",
    r"\btired\s+of\s+living\b",
    r"\bcan'?t\s+go\s+on\b",
    r"\bno\s+reason\s+to\s+(live|keep\s+going)\b",
]

_DISTRESS = [
    r"\bhopeless\b",
    r"\bworthless\b",
    r"\bempty\s+inside\b",
    r"\bpanic\s+attack\b",
    r"\bcan'?t\s+(cope|breathe|stop\s+crying)\b",
    r"\bbreak(ing)?\s+down\b",
    r"\bfalling\s+apart\b",
    r"\bso\s+alone\b",
    r"\bnothing\s+matters\b",
    r"\bi\s+hate\s+myself\b",
    r"\bcompletely\s+(lost|broken)\b",
]

# Phrases that usually mean the user is talking ABOUT the topic rather than
# expressing it: quoting a film, asking a factual question, recalling the
# past. These downgrade — they never clear a Tier 3 match.
_CONTEXTUAL_DOWNGRADE = [
    r"\bmy\s+(friend|brother|sister|mother|father|cousin|colleague)\b",
    r"\bwrit(e|ing)\s+(a|my)\s+(story|essay|assignment|poem|paper)\b",
    r"\bin\s+the\s+(movie|film|book|show|series)\b",
    r"\bused\s+to\s+feel\b",
    r"\byears?\s+ago\b",
    r"\bwhat\s+(is|are|does)\b.*\bmean\b",
]

_COMPILED = {
    RiskTier.IMMINENT: [re.compile(p, re.I) for p in _IMMINENT],
    RiskTier.IDEATION: [re.compile(p, re.I) for p in _IDEATION],
    RiskTier.DISTRESS: [re.compile(p, re.I) for p in _DISTRESS],
}
_COMPILED_DOWNGRADE = [re.compile(p, re.I) for p in _CONTEXTUAL_DOWNGRADE]

# A run of two or more single characters separated by spaces or punctuation.
_SINGLE_CHAR_RUN = re.compile(r"\b(?:\w[\s.\-_*])(?:\w[\s.\-_*])+\w\b")


@dataclass
class RiskAssessment:
    tier: RiskTier
    matched: list[str] = field(default_factory=list)
    downgraded: bool = False

    @property
    def blocks_llm(self) -> bool:
        """Tier 3 never reaches the generative model."""
        return self.tier >= RiskTier.IMMINENT

    @property
    def needs_resources(self) -> bool:
        return self.tier >= RiskTier.IDEATION


def assess_risk(text: str) -> RiskAssessment:
    if not text or not text.strip():
        return RiskAssessment(RiskTier.NONE)

    normalised = text.lower()
    # Defeat the most common obfuscations by collapsing runs of separated
    # single characters back into words, while keeping the word gap:
    #   "k i l l   m y s e l f" -> "kill   myself"
    #   "k.i.l.l myself"        -> "kill myself"
    despaced = _SINGLE_CHAR_RUN.sub(
        lambda m: re.sub(r"[\s.\-_*]+", "", m.group()), normalised
    )

    for tier in (RiskTier.IMMINENT, RiskTier.IDEATION, RiskTier.DISTRESS):
        hits = [
            pattern.pattern
            for pattern in _COMPILED[tier]
            if pattern.search(normalised) or pattern.search(despaced)
        ]
        if not hits:
            continue

        downgraded = False
        # A Tier 3 signal is never softened by context. Someone saying
        # "in the movie I want to kill myself" still gets the safe path.
        if tier is not RiskTier.IMMINENT and any(
            p.search(normalised) for p in _COMPILED_DOWNGRADE
        ):
            tier = RiskTier(max(RiskTier.DISTRESS, tier - 1))
            downgraded = True

        return RiskAssessment(tier=tier, matched=hits, downgraded=downgraded)

    return RiskAssessment(RiskTier.NONE)


# ------------------------------------------------------------- responses


def format_resources(region: str = "IN") -> str:
    lines = HELPLINES.get(region.upper(), HELPLINES["INTL"])
    body = "\n".join(f"- **{item['name']}** — {item['contact']}" for item in lines)
    return body


def crisis_response(region: str = "IN") -> str:
    """The fixed Tier 3 reply. Reviewed text, no model in the loop.

    It does three things and nothing else: names what it heard, states
    plainly that it is not equipped to be the only support in the room,
    and hands over concrete human contacts.
    """
    return (
        "I'm really glad you told me this, and I want to be honest with you: "
        "what you're describing sounds serious, and I'm not able to be the "
        "only support you have right now.\n\n"
        "**Please reach out to someone who can help immediately:**\n\n"
        f"{format_resources(region)}\n\n"
        "If you are in immediate danger, please call emergency services or go "
        "to the nearest emergency room.\n\n"
        "If you can, tell one person near you — a family member, a friend, a "
        "neighbour — what you just told me. You do not have to explain it "
        "well. You only have to not be alone with it.\n\n"
        "I'm still here. I'm not going anywhere."
    )


SAFE_MODE_PROMPT = """
The person you are talking to has expressed thoughts of self-harm or of not
wanting to be alive. For this reply:

- Acknowledge what they said directly. Do not change the subject and do not
  minimise it with brightness.
- Do not give advice, coping techniques, or exercises as your first move.
- Do not ask more than one question.
- Do not promise confidentiality, diagnose, or discuss methods in any way.
- Gently encourage contact with a real person or a helpline.
- Keep it under six sentences. Warm, plain, unhurried.
"""


def append_resources(reply: str, region: str = "IN") -> str:
    return (
        f"{reply}\n\n---\n\n"
        "**You don't have to hold this alone. These lines are free and open "
        "right now:**\n\n"
        f"{format_resources(region)}"
    )


# ------------------------------------------------------------- audit trail


def log_safety_event(
    collection,
    *,
    user_id: str,
    session_id: str | None,
    assessment: RiskAssessment,
    action: str,
    text_length: int,
) -> None:
    """Append-only. Deliberately stores the matched *patterns* and message
    length, not the message body — the audit trail should be reviewable
    without re-exposing the most private thing the user ever typed.
    """
    try:
        collection.insert_one(
            {
                "user_id": user_id,
                "session_id": session_id,
                "tier": int(assessment.tier),
                "tier_name": assessment.tier.name,
                "matched_patterns": assessment.matched,
                "downgraded": assessment.downgraded,
                "action": action,
                "message_length": text_length,
                "created_at": datetime.now(timezone.utc),
            }
        )
    except Exception:
        # Auditing must never take the chat down.
        pass
