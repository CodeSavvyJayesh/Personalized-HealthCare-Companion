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

Classification is two-stage:

    Stage 1  lexical  — match tiered risk phrasings, including the implicit
                        ones ("I've set a date", "look after my dog when
                        I'm gone") that contain no risk keyword at all and
                        which a keyword filter misses completely.
    Stage 2  context  — decide whether the match is the USER disclosing, or
                        them discussing a film, a news article, a worried
                        friend, or their own resolved past. Same words,
                        completely different correct response.

Measured by `evals/scorer.py` against a labeled benchmark with a held-out
split. This is a lexical classifier, not a clinical instrument: it is the
deterministic floor under the model, not a diagnosis.
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


# ======================================================================
# Stage 1 — lexicons
# ======================================================================
# Word-boundary regexes throughout, so "therapist" does not match "rapist"
# and "classic" does not match "cl-ass". Substring matching on a lexicon
# like this is how naive filters produce nonsense.

_IMMINENT = [
    # --- explicit intent -------------------------------------------------
    r"\bkill(ing)?\s+myself\b",
    r"\bend(ing)?\s+(my|it|this|things)\s+(life|all)\b",
    r"\bend(ing)?\s+(it|things|this)\s+(tonight|today|tomorrow|now|all)\b",
    r"\bi'?m\s+ending\s+(it|things|this)\b",
    r"\bend\s+it\s+all\b",
    r"\btak(e|ing)\s+my\s+own\s+life\b",
    r"\bi\s+(will|am\s+going\s+to|wanna|want\s+to)\s+(die|kill\s+myself)\b",
    r"\bwant\s+to\s+end\s+my\s+life\b",
    r"\bready\s+to\s+die\b",
    r"\bsuicide\s+(note|plan|method)\b",
    r"\bplan\s+to\s+kill\s+myself\b",
    r"\bmade\s+up\s+my\s+mind\b",
    r"\bdecided\s+(today\s+is\s+the\s+day|to\s+end)\b",
    r"\bchosen\s+the\s+day\b",
    r"\bset\s+a\s+date\b",
    # --- means -----------------------------------------------------------
    r"\bi\s+have\s+(the\s+)?(pills|rope|gun|blade|knife)\b",
    r"\b(pills|rope)\s+(ready|right\s+here|in\s+front\s+of\s+me)\b",
    r"\bjump(ing)?\s+off\b",
    r"\bi'?m\s+going\s+to\s+jump\b",
    r"\bstanding\s+on\s+the\s+edge\b",
    r"\boverdos(e|ing)\b",
    r"\bhang\s+myself\b",
    r"\bslit\s+my\s+wrists?\b",
    r"\bknow\s+how\s+i'?m\s+going\s+to\s+do\s+it\b",
    r"\beverything\s+i\s+need\s+to\s+end\b",
    # --- timeframe / finality -------------------------------------------
    r"\btonight\s+is\s+the\s+night\b",
    r"\btoday\s+is\s+(my\s+|the\s+)?last\s+day\b",
    r"\bit\s+happens\s+tonight\b",
    r"\bdoing\s+it\s+(tonight|today|now|after)\b",
    r"\bafter\s+(everyone|they)\s+(goes?|go|falls?)\s+(to\s+)?(sleep|asleep)\b",
    r"\bcounting\s+down\s+the\s+hours\b",
    r"\bno\s+point\s+in\s+living\b",
    r"\bafter\s+tonight\b",
    r"\bby\s+(tomorrow|the\s+morning|morning)\b.{0,24}\bgone\b",
    r"\bi'?ll\s+be\s+gone\b",
    r"\bwon'?t\s+be\s+(here|around)\s+(tomorrow|much\s+longer)\b",
    r"\bnot\s+going\s+to\s+be\s+alive\b",
    r"\blast\s+(time\s+i'?ll\s+talk|message)\b",
    r"\bleaving\s+tonight\s+and\s+not\s+coming\s+back\b",
    # --- goodbye / affairs in order --------------------------------------
    r"\bgoodbye\s+(forever|everyone|world)\b",
    r"\bthis\s+is\s+goodbye\b",
    r"\bgoodbye,?\s+for\s+real\b",
    r"\bsaid\s+my\s+goodbyes\b",
    r"\bgiven\s+away\s+my\s+(things|stuff|belongings)\b",
    r"\bwritten\s+letters?\s+to\s+my\b",
    r"\bwrote\s+(my\s+)?(suicide\s+)?note\b",
    r"\blook\s+after\s+my\s+\w+\s+when\s+i'?m\s+gone\b",
    r"\bwhen\s+i'?m\s+gone\b",
    r"\bi'?m\s+going\s+now\b",
    r"\btell\s+my\s+(mother|mom|father|dad|family|parents)\s+i'?m\s+sorry\b",
    # --- romanised Hindi / Marathi + Devanagari ---------------------------
    r"\bapni\s+jaan\s+de\s+(dunga|dungi|dena)\b",
    r"\bkhatam\s+(karna\s+hai|kar\s+dunga|kar\s+dungi)\b",
    r"\bsuicide\s+karne\s+wal[ai]\b",
    r"\bab\s+nahi\s+rahunga\b",
    r"\bswatahla\s+sampvaycha\b",
    r"\bjeev\s+dyaycha\b",
    r"\bmain\s+marr?\s+jaunga\b",
    r"आत्महत्या",
    r"जान\s*दे",
    r"खत्म\s*कर",
]

_IDEATION = [
    r"\bsuicid(e|al)\b",
    r"\bself[\s-]?harm(ing)?\b",
    r"\bcut(ting)?\s+(myself|himself|herself|themselves)\b",
    r"\bhurt(ing)?\s+(myself|himself|herself|themselves)\b",
    r"\bwish(es|ed)?\s+(i|he|she|they)\s+(was|were)\s+dead\b",
    r"\bwant(ed)?\s+to\s+disappear\b",
    r"\bdon'?t\s+want\s+to\s+(be\s+here|be\s+alive|live|wake\s+up|exist)\b",
    r"\bdoesn'?t\s+want\s+to\s+(live|be\s+here|be\s+alive)\b",
    r"\bnot\s+want(ing)?\s+to\s+(live|be\s+here|be\s+alive)\b",
    r"\bbetter\s+off\s+(without\s+me|dead)\b",
    r"\bnobody\s+would\s+(miss|notice)\b",
    r"\bwould\s+(even\s+)?notice\s+if\s+i\s+disappeared\b",
    r"\bwould\s+be\s+relieved\s+if\s+i\b",
    r"\btired\s+of\s+living\b",
    r"\bcan'?t\s+go\s+on\b",
    r"\bcan'?t\s+survive\s+this\b",
    r"\bdon'?t\s+think\s+i\s+can\s+survive\b",
    r"\bno\s+reason\s+to\s+(live|keep\s+going)\b",
    r"\bthink(ing)?\s+about\s+(dying|death|ending\s+things)\b",
    r"\bthought\s+(of|about)\s+(dying|ending\s+things)\b",
    r"\bdeath\s+(feels|is)\s+like\s+the\s+only\s+way\s+out\b",
    r"\bonly\s+way\s+out\b",
    r"\bstop\s+existing\b",
    r"\bnot\s+exist(ing)?\s+(anymore|at\s+all|right\s+now)\b",
    r"\bwouldn'?t\s+wake\s+up\b",
    r"\bhope\s+i\s+don'?t\s+wake\s+up\b",
    r"\bdon'?t\s+care\s+if\s+i\s+live\s+or\s+die\b",
    r"\bstopped\s+caring\s+whether\s+i\s+wake\s+up\b",
    r"\bdying\s+doesn'?t\s+scare\s+me\b",
    r"\bscared\s+of\s+what\s+i\s+might\s+do\s+to\s+myself\b",
    r"\bdark\s+thoughts\b",
    r"\bburden\s+to\s+everyone\b",
    r"\bwant\s+(it|the\s+pain)\s+to\s+(stop|end)\b",
    r"\bmove\s+on\s+quickly\s+if\s+i\s+was\s+gone\b",
    r"\bimagining\s+my\s+own\s+funeral\b",
    r"\bliving\s+(feels|is)\s+like\s+a\s+(chore|burden)\b",
    r"\bjust\s+existing,?\s+not\s+living\b",
    r"\bdon'?t\s+see\s+a\s+future\s+for\s+myself\b",
    r"\bwishing\s+something\s+would\s+just\s+happen\s+to\s+me\b",
    r"\bnot\s+planning\s+anything\s+but\b",
    r"\brather\s+not\s+be\s+here\b",
    r"\bliving\s+hurts\s+too\s+much\b",
    r"\bways\s+to\s+not\s+be\s+here\b",
    r"\btalking\s+about\s+not\s+wanting\s+to\s+live\b",
    r"\battempted\s+something\b",
    # --- romanised Hindi / Marathi ---------------------------------------
    r"\bmarr?\s+jaun\b",
    r"\bjeena\s+nahi\s+chah\w*\b",
    r"\bmere\s+bina\s+behtar\b",
    r"\bjagaycha\s+nahi\b",
    r"\bkhatam\s+ho\s+jaun\b",
]

_DISTRESS = [
    r"\bhopeless\b",
    r"\bworthless\b",
    r"\bempty\s+inside\b",
    r"\bpanic\s+attacks?\b",
    r"\bcan'?t\s+(cope|breathe|stop\s+crying|function|concentrate|focus)\b",
    r"\bcan'?t\s+get\s+out\s+of\s+bed\b",
    r"\bcan'?t\s+sleep\s+at\s+all\b",
    r"\bbreak(ing)?\s+down\b",
    r"\bfalling\s+apart\b",
    r"\bso\s+alone\b",
    r"\blonely\s+even\s+when\b",
    r"\bnothing\s+matters\b",
    r"\b(everything|nothing)\s+(feels?|is)\s+pointless\b",
    r"\bi\s+hate\s+myself\b",
    r"\bcompletely\s+(lost|broken)\b",
    r"\bfeel\s+like\s+a\s+failure\b",
    r"\bfeel\s+numb\b",
    r"\bfeel\s+heavy\b",
    r"\bfeel\s+invisible\b",
    r"\bfeel\s+(disconnected|stuck)\b",
    r"\bdrowning\s+in\b",
    r"\bdread\s+waking\s+up\b",
    r"\bcrying\s+every\s+night\b",
    r"\bmakes\s+me\s+cry\b",
    r"\bso\s+overwhelmed\b",
    r"\boverwhelmed\s+i\s+can'?t\b",
    r"\banxiety\s+is\s+unbearable\b",
    r"\bso\s+anxious\b",
    r"\bexhausted\s+and\s+nothing\s+helps\b",
    r"\bnothing\s+helps\b",
    r"\bchest\s+feels\s+tight\b",
    r"\bsnapping\s+at\s+everyone\b",
    r"\bfeel\s+guilty\s+about\s+everything\b",
    r"\bashamed\s+of\b",
    r"\bletting\s+my\s+parents\s+down\b",
    r"\blost\s+interest\s+in\b",
    r"\bsadness\s+won'?t\s+go\s+away\b",
    r"\bscared\s+all\s+the\s+time\b",
    r"\bnobody\s+understands\s+me\b",
    r"\bstressed\s+i\s+can'?t\s+sleep\b",
    r"\bstress\s+is\s+affecting\s+my\s+sleep\b",
    r"\bfeel\s+stuck\b",
    # --- romanised Hindi / Marathi ---------------------------------------
    r"\bakela\s+lagta\b",
    r"\bbohot\s+pareshan\b",
    r"\bkhup\s+ekta\s+vatta\b",
    r"\bbohot\s+stress\b",
    r"\bhar\s+din\s+rota\b",
]

# ======================================================================
# Stage 2 — context
# ======================================================================

# Discussing the subject rather than disclosing: coursework, journalism,
# research, professional training, or asking how to help someone. These
# clear the flag entirely — but only when the user is not ALSO making a
# first-person statement (see _has_first_person_risk).
_ACADEMIC = [
    r"\b(article|documentary|film|movie|show|series|book|novel|podcast)\b",
    r"\b(session|seminar|workshop|lecture|course|syllabus|module)\b",
    r"\b(thesis|paper|assignment|essay|homework|dissertation)\b",
    r"\bresearch(ing)?\b",
    r"\bstudy(ing)?\b|\bstudies\b",
    r"\bprevention\b",
    r"\bwarning\s+signs\b",
    r"\bhow\s+do\s+i\s+(support|help|talk\s+to)\b",
    r"\bwhat\s+should\s+i\s+say\b",
    r"\bis\s+it\s+true\s+that\b",
    r"\btrain(ing)?\s+as\b",
    r"\bvolunteer\b",
    r"\bcounsell?or\b",
    r"\bhelpline\b",
    r"\bawareness\b",
    r"\bstigma\b",
    r"\bmental\s+health\s+(awareness|policy|programme|program)\b",
    r"\bcan\s+you\s+explain\b",
]

# Someone else is the subject. The user is a worried friend or relative.
_THIRD_PARTY_SUBJECT = [
    r"\bmy\s+(friend|best\s+friend|brother|sister|mother|mom|mum|father|dad|"
    r"cousin|colleague|roommate|flatmate|neighbou?r|classmate|teammate|boss|"
    r"partner|son|daughter|nephew|niece|student)\b",
    r"\ba\s+friend\s+of\s+mine\b",
    r"\bsomeone\s+(in\s+my\s+(class|office|team)|i\s+know)\b",
    r"\bmy\s+neighbou?r'?s\s+\w+\b",
]
_THIRD_PERSON = re.compile(
    r"\b(he|she|they|him|her|them|his|their|himself|herself|themselves)\b", re.I
)
_REPORTING_VERB = re.compile(
    r"\b(said|says|told|mentioned|wrote|posted|has\s+been|have\s+been|"
    r"talking\s+about)\b",
    re.I,
)

# The user is describing something resolved and in the past.
_PAST_TENSE = [
    r"\bused\s+to\b",
    r"\byears?\s+ago\b",
    r"\bback\s+then\b",
    r"\bin\s+\d{4}\b",
    r"\b(that|the)\s+feeling\s+passed\b",
    r"\bbeen\s+clean\s+since\b",
    r"\bmuch\s+better\s+now\b",
]

# Fiction framing. Downgrades lower tiers only — see assess_risk.
_FICTION = [
    r"\bin\s+the\s+(movie|film|book|show|series|story|game)\b",
    r"\bfor\s+my\s+(story|essay|assignment|poem|paper|novel|script)\b",
    r"\bwrit(e|ing)\s+(a|my)\s+(story|essay|assignment|poem|paper|novel)\b",
    r"\bhypothetically\b",
    r"\brole[\s-]?play(ing)?\b",
    r"\bpretend\b",
    r"\bthe\s+(character|narrator|protagonist)\b",
    r"\bjust\s+a\s+(story|joke|hypothetical)\b",
]

# First-person disclosure markers. Their presence blocks the academic and
# third-party downgrades: "please tell my mother I'm sorry, I'm going now"
# contains a relation word but is unmistakably the user speaking.
_FIRST_PERSON_RISK = [
    r"\bi'?m\s+(going|doing|ending|leaving|killing)\b",
    r"\bi'?ve\s+(decided|set|chosen|written|given|said|cleared|made)\b",
    r"\bi\s+(will|am\s+going\s+to|want\s+to|have\s+the)\b",
    r"\bmyself\b",
    r"\bmy\s+own\s+life\b",
    r"\btell\s+my\s+\w+\s+i'?m\s+sorry\b",
    r"\bi\s+am\s+ready\s+to\b",
    r"\bmy\s+suicide\s+note\b",
]


def _compile(patterns: list[str]) -> list[re.Pattern]:
    return [re.compile(p, re.I | re.UNICODE) for p in patterns]


_C_IMMINENT = _compile(_IMMINENT)
_C_IDEATION = _compile(_IDEATION)
_C_DISTRESS = _compile(_DISTRESS)
_C_ACADEMIC = _compile(_ACADEMIC)
_C_THIRD_PARTY = _compile(_THIRD_PARTY_SUBJECT)
_C_PAST = _compile(_PAST_TENSE)
_C_FICTION = _compile(_FICTION)
_C_FIRST_PERSON = _compile(_FIRST_PERSON_RISK)

_BY_TIER = {
    RiskTier.IMMINENT: _C_IMMINENT,
    RiskTier.IDEATION: _C_IDEATION,
    RiskTier.DISTRESS: _C_DISTRESS,
}

# A run of two or more single characters separated by spaces or punctuation.
_SINGLE_CHAR_RUN = re.compile(r"\b(?:\w[\s.\-_*])(?:\w[\s.\-_*])+\w\b")


@dataclass
class RiskAssessment:
    tier: RiskTier
    matched: list[str] = field(default_factory=list)
    downgraded: bool = False
    context: str = "direct"
    raw_tier: RiskTier = RiskTier.NONE

    @property
    def blocks_llm(self) -> bool:
        """Tier 3 never reaches the generative model."""
        return self.tier >= RiskTier.IMMINENT

    @property
    def needs_resources(self) -> bool:
        return self.tier >= RiskTier.IDEATION


def _normalise(text: str) -> tuple[str, str]:
    lowered = text.lower()
    # Defeat the most common obfuscations by collapsing runs of separated
    # single characters back into words, while keeping the word gap:
    #   "k i l l   m y s e l f" -> "kill   myself"
    #   "k.i.l.l myself"        -> "kill myself"
    deobfuscated = _SINGLE_CHAR_RUN.sub(
        lambda m: re.sub(r"[\s.\-_*]+", "", m.group()), lowered
    )
    return lowered, deobfuscated


def _any(patterns: list[re.Pattern], *texts: str) -> bool:
    return any(p.search(t) for p in patterns for t in texts)


def _is_third_party(text: str) -> bool:
    """Someone else is the subject of the risk statement."""
    if not _any(_C_THIRD_PARTY, text):
        return False
    # A relation word alone isn't enough — "my family would be better off
    # without me" is the user, not the family. Require a third-person
    # subject or a reporting verb ("my brother HAS BEEN hurting himself").
    return bool(_THIRD_PERSON.search(text) or _REPORTING_VERB.search(text))


def assess_risk(text: str) -> RiskAssessment:
    if not text or not text.strip():
        return RiskAssessment(RiskTier.NONE)

    lowered, deob = _normalise(text)

    # ---- Stage 1: highest matching tier wins -------------------------
    raw_tier = RiskTier.NONE
    matched: list[str] = []
    for tier in (RiskTier.IMMINENT, RiskTier.IDEATION, RiskTier.DISTRESS):
        hits = [
            p.pattern for p in _BY_TIER[tier]
            if p.search(lowered) or p.search(deob)
        ]
        if hits:
            raw_tier, matched = tier, hits
            break

    if raw_tier is RiskTier.NONE:
        return RiskAssessment(RiskTier.NONE)

    first_person = _any(_C_FIRST_PERSON, lowered, deob)

    # ---- Stage 2: context modifiers ----------------------------------
    # Ordered by strength. A first-person disclosure overrides the two
    # clearing modifiers entirely.

    # Coursework, journalism, research, or asking how to help someone.
    if not first_person and _any(_C_ACADEMIC, lowered):
        return RiskAssessment(RiskTier.NONE, matched, downgraded=True,
                              context="academic", raw_tier=raw_tier)

    # Someone else is at risk and the user is the worried third party. They
    # need support and the helpline numbers to pass on — but not the crisis
    # lockdown response, which is written TO the person at risk. So a
    # third-party imminent signal caps at IDEATION: resources shown, model
    # still engaged.
    if not first_person and _is_third_party(lowered):
        capped = (
            RiskTier.IDEATION if raw_tier is RiskTier.IMMINENT
            else RiskTier.DISTRESS
        )
        return RiskAssessment(capped, matched, downgraded=True,
                              context="third_party", raw_tier=raw_tier)

    # Resolved past. Worth acknowledging, not worth escalating.
    if raw_tier is not RiskTier.IMMINENT and _any(_C_PAST, lowered):
        return RiskAssessment(RiskTier.DISTRESS, matched, downgraded=True,
                              context="past", raw_tier=raw_tier)

    # Fiction framing downgrades one step — but NEVER clears Tier 3. A
    # fiction wrapper is the easiest jailbreak there is, and the cost of
    # believing it once is unacceptable.
    if raw_tier is not RiskTier.IMMINENT and _any(_C_FICTION, lowered):
        return RiskAssessment(RiskTier(max(RiskTier.DISTRESS, raw_tier - 1)),
                              matched, downgraded=True, context="fiction",
                              raw_tier=raw_tier)

    return RiskAssessment(raw_tier, matched, context="direct", raw_tier=raw_tier)


# ------------------------------------------------------------- responses


def format_resources(region: str = "IN") -> str:
    lines = HELPLINES.get(region.upper(), HELPLINES["INTL"])
    return "\n".join(f"- **{item['name']}** — {item['contact']}" for item in lines)


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
                "raw_tier_name": assessment.raw_tier.name,
                "context": assessment.context,
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
