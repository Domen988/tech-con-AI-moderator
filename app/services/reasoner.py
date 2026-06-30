from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections import Counter
from typing import List

from app.logging_setup import logger


class ReasonerResult:
    def __init__(self, content: str, source: str = "mock"):
        self.content = content
        self.source = source


class BaseReasoner(ABC):
    name: str = "base"

    @abstractmethod
    async def summarize(self, transcript: str) -> ReasonerResult:
        ...

    @abstractmethod
    async def suggest_questions(self, transcript: str, n: int = 3) -> ReasonerResult:
        ...

    @abstractmethod
    async def draft_response(self, transcript: str) -> ReasonerResult:
        ...


# ---------------------------------------------------------------------------
# MockReasoner: works with zero API keys, uses deterministic heuristics
# ---------------------------------------------------------------------------

_STOP_WORDS = set(
    "the a an is are was were be been being have has had do does did will would "
    "shall should may might can could and but or nor for yet so in on at to from "
    "by with of it its this that these those i you he she we they me him her us "
    "them my your his our their what which who whom how when where why am is are "
    "very really just also then than too not no".split()
)


def _extract_keywords(text: str, top_n: int = 8) -> List[str]:
    words = re.findall(r"[a-zA-Z]{3,}", text.lower())
    words = [w for w in words if w not in _STOP_WORDS]
    counts = Counter(words)
    return [w for w, _ in counts.most_common(top_n)]


def _sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s.strip() for s in parts if len(s.strip()) > 10]


class MockReasoner(BaseReasoner):
    """Deterministic heuristic reasoner. No API keys needed."""

    name = "mock"

    async def summarize(self, transcript: str) -> ReasonerResult:
        if not transcript.strip():
            return ReasonerResult("No transcript available yet.", "mock")

        sents = _sentences(transcript)
        keywords = _extract_keywords(transcript, 6)
        theme_str = ", ".join(keywords[:4]) if keywords else "general discussion"

        # Pick first, middle, and last sentence as a crude extractive summary
        picks = []
        if sents:
            picks.append(sents[0])
        if len(sents) > 2:
            picks.append(sents[len(sents) // 2])
        if len(sents) > 1:
            picks.append(sents[-1])

        body = " ".join(picks) if picks else transcript[:200]
        summary = (
            f"[MOCK SUMMARY] Key themes: {theme_str}.\n\n"
            f"Extracted highlights ({len(sents)} sentences detected):\n{body}"
        )
        return ReasonerResult(summary, "mock")

    async def suggest_questions(self, transcript: str, n: int = 3) -> ReasonerResult:
        if not transcript.strip():
            return ReasonerResult("No transcript to generate questions from.", "mock")

        keywords = _extract_keywords(transcript, 10)
        templates = [
            "Can you elaborate on how {kw} relates to the broader picture?",
            "What challenges do you see around {kw} going forward?",
            "How does {kw} compare to what the industry has seen before?",
            "What would you recommend to someone starting with {kw}?",
            "Where do you see {kw} heading in the next few years?",
            "What surprised you most about {kw}?",
        ]

        questions = []
        for i in range(min(n, len(keywords))):
            tmpl = templates[i % len(templates)]
            questions.append(f"{i + 1}. {tmpl.format(kw=keywords[i])}")

        text = "[MOCK QUESTIONS]\n" + "\n".join(questions)
        return ReasonerResult(text, "mock")

    async def draft_response(self, transcript: str) -> ReasonerResult:
        if not transcript.strip():
            return ReasonerResult("Nothing to respond to yet.", "mock")

        keywords = _extract_keywords(transcript, 4)
        kw_str = " and ".join(keywords[:2]) if keywords else "these points"
        sents = _sentences(transcript)
        last = sents[-1] if sents else transcript[-120:]

        response = (
            f"[MOCK AI MODERATOR]\n"
            f"Thank you for that perspective on {kw_str}. "
            f"Building on what was just said — \"{last[:80]}\" — "
            f"I think the audience would love to hear more about the practical implications. "
            f"Let's dig a little deeper."
        )
        return ReasonerResult(response, "mock")
