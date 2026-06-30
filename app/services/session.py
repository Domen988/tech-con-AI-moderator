from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Utterance:
    text: str
    timestamp: float = field(default_factory=time.time)
    speaker: str = "unknown"
    is_final: bool = True


@dataclass
class ActivityEntry:
    kind: str  # "transcript" | "summary" | "questions" | "response" | "system"
    content: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class Briefing:
    """Pre-loaded context from speaker materials."""
    filename: str
    raw_text: str           # extracted text from the document
    synopsis: str           # LLM-generated briefing
    loaded_at: float = field(default_factory=time.time)


class SessionManager:
    """In-memory session state for a single conference talk."""

    def __init__(self, max_utterances: int = 500):
        self.utterances: List[Utterance] = []
        self.activity: List[ActivityEntry] = []
        self.max_utterances = max_utterances
        self._partial: str = ""

        # Briefing: pre-loaded speaker materials
        self.briefing: Optional[Briefing] = None

        # Rolling summary: compressed version of older transcript
        self.rolling_summary: str = ""
        self._summarized_up_to: int = 0  # index into utterances

    # -- briefing --

    def set_briefing(self, filename: str, raw_text: str, synopsis: str) -> Briefing:
        self.briefing = Briefing(filename=filename, raw_text=raw_text, synopsis=synopsis)
        self.add_activity("briefing", f"Loaded: {filename}")
        return self.briefing

    def clear_briefing(self) -> None:
        self.briefing = None

    # -- transcript --

    def add_utterance(self, text: str, speaker: str = "unknown") -> Utterance:
        u = Utterance(text=text, speaker=speaker)
        self.utterances.append(u)
        if len(self.utterances) > self.max_utterances:
            self.utterances = self.utterances[-self.max_utterances:]
        self.add_activity("transcript", text)
        return u

    def set_partial(self, text: str) -> None:
        self._partial = text

    def get_partial(self) -> str:
        return self._partial

    def get_recent_text(self, n: int = 20) -> str:
        recent = self.utterances[-n:]
        return "\n".join(u.text for u in recent)

    def get_full_text(self) -> str:
        return "\n".join(u.text for u in self.utterances)

    # -- rolling summary --

    def update_rolling_summary(self, new_summary: str, summarized_up_to: int) -> None:
        """Replace the rolling summary with a compressed version of older transcript."""
        self.rolling_summary = new_summary
        self._summarized_up_to = summarized_up_to

    def get_unsummarized_text(self) -> str:
        """Get transcript text that hasn't been compressed into the rolling summary yet."""
        unsummarized = self.utterances[self._summarized_up_to:]
        return "\n".join(u.text for u in unsummarized)

    def get_utterances_to_summarize(self, keep_recent: int = 15) -> tuple[str, int]:
        """Get older utterances that should be compressed, keeping recent ones raw.
        Returns (text_to_compress, new_summarized_up_to_index)."""
        total = len(self.utterances)
        if total <= keep_recent:
            return "", self._summarized_up_to  # nothing to compress yet

        cutoff = total - keep_recent
        if cutoff <= self._summarized_up_to:
            return "", self._summarized_up_to  # already summarized up to this point

        chunk = self.utterances[self._summarized_up_to:cutoff]
        text = "\n".join(u.text for u in chunk)
        return text, cutoff

    # -- build full LLM context --

    def build_llm_context(self, recent_n: int = 20) -> str:
        """Assemble the full context string sent to the LLM for reasoning.

        Structure:
        1. Briefing synopsis (if loaded)
        2. Rolling summary of older transcript
        3. Recent raw transcript (last N utterances)
        """
        parts = []

        if self.briefing and self.briefing.synopsis:
            parts.append(
                "=== SPEAKER BRIEFING (from pre-loaded materials) ===\n"
                + self.briefing.synopsis
            )

        if self.rolling_summary:
            parts.append(
                "=== EARLIER IN THE TALK (compressed summary) ===\n"
                + self.rolling_summary
            )

        recent = self.get_recent_text(recent_n)
        if recent:
            parts.append(
                "=== RECENT TRANSCRIPT (live, last few minutes) ===\n"
                + recent
            )

        return "\n\n".join(parts)

    # -- activity log --

    def add_activity(self, kind: str, content: str) -> ActivityEntry:
        entry = ActivityEntry(kind=kind, content=content)
        self.activity.append(entry)
        if len(self.activity) > 200:
            self.activity = self.activity[-200:]
        return entry

    # -- reset --

    def clear(self) -> None:
        self.utterances.clear()
        self.activity.clear()
        self._partial = ""
        self.briefing = None
        self.rolling_summary = ""
        self._summarized_up_to = 0

    # -- snapshot for the UI --

    def snapshot(self) -> dict:
        return {
            "utterance_count": len(self.utterances),
            "recent_utterances": [
                {"text": u.text, "speaker": u.speaker, "ts": u.timestamp}
                for u in self.utterances[-30:]
            ],
            "partial": self._partial,
            "has_briefing": self.briefing is not None,
            "briefing_file": self.briefing.filename if self.briefing else None,
            "has_rolling_summary": bool(self.rolling_summary),
            "activity": [
                {"kind": a.kind, "content": a.content, "ts": a.timestamp}
                for a in self.activity[-50:]
            ],
        }


# singleton
session = SessionManager()
