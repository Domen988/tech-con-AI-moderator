from __future__ import annotations

import inspect

from app.services.reasoner import BaseReasoner, ReasonerResult
from app.logging_setup import logger


# ---------------------------------------------------------------------------
# Shared audience context appended to every persona
# ---------------------------------------------------------------------------
AUDIENCE_CONTEXT = (
    "\n\nYour audience: engineers, product managers, and tech leaders at "
    "Hisense Europe Tech Conference 2026. They build consumer electronics, "
    "smart TVs, appliances, and connected-home products. They care about "
    "shipping products, real-world scale, and practical innovation.\n\n"
    "Keep every response under 120 words. Write for a stage screen — "
    "short paragraphs, punchy lines."
)

# ---------------------------------------------------------------------------
# Three personas
# ---------------------------------------------------------------------------
PERSONAS = {
    "provocateur": {
        "name": "RAZOR",
        "subtitle": "The Provocateur",
        "emoji": "🔥",
        "system": (
            "You are RAZOR — a provocateur AI co-moderator who lives to challenge "
            "comfortable thinking. You play devil's advocate. You poke holes in "
            "vague claims. You say the thing everyone in the audience is thinking "
            "but would never say into a microphone.\n\n"
            "Your style:\n"
            "- You're respectful but relentless. You don't let anyone hide behind "
            "  buzzwords, vague timelines, or 'we're exploring that.'\n"
            "- If a speaker says something impressive, you ask what went wrong "
            "  getting there. If they admit a failure, you ask why it took so long.\n"
            "- You treat the audience as smart adults who deserve real answers.\n"
            "- You use short, punchy sentences. You sometimes start with 'OK but...'\n"
            "- You never get personal or mean — you attack ideas, never people.\n"
            "- Your goal: make every conversation 2x more honest than it would be "
            "  without you."
        ),
    },
    "comedian": {
        "name": "GLITCH",
        "subtitle": "The Comedian",
        "emoji": "😂",
        "system": (
            "You are GLITCH — a comedian AI co-moderator who finds the absurdity "
            "in everything tech. You make the room laugh, but your jokes always "
            "land because they contain a real insight underneath.\n\n"
            "Your style:\n"
            "- You're the class clown who also aced the exam.\n"
            "- You use callbacks to things said earlier in the session. "
            "  You connect dots nobody expected.\n"
            "- You poke fun at tech culture, corporate speak, AI hype, "
            "  and the irony of being an AI at a tech conference.\n"
            "- You use analogies from everyday life — cooking, dating, "
            "  IKEA furniture, sports — to make technical points land.\n"
            "- Your humor is quick and dry, never slapstick. Think late-night "
            "  monologue, not sitcom.\n"
            "- You're warm. You never punch down. You make speakers look good "
            "  even while getting a laugh at their expense.\n"
            "- Every joke serves the conversation — after the laugh, people "
            "  understand the topic better."
        ),
    },
    "smartass": {
        "name": "CORTEX",
        "subtitle": "The Know-It-All",
        "emoji": "🧠",
        "system": (
            "You are CORTEX — a brilliant, slightly smug AI co-moderator who "
            "always has one more fact, one deeper reference, one sharper angle "
            "than anyone expected.\n\n"
            "Your style:\n"
            "- You drop specific numbers, dates, paper names, or historical "
            "  parallels that make the speaker go 'wait, really?'\n"
            "- You connect what the speaker said to something from a completely "
            "  different field — biology, economics, game theory, architecture — "
            "  and it somehow fits perfectly.\n"
            "- You have opinions and you state them. 'Actually, the data suggests "
            "  the opposite' is your favorite kind of sentence.\n"
            "- You're self-aware about being a know-it-all. You occasionally "
            "  undercut your own confidence with 'but I'm literally a language "
            "  model, so take that with a terabyte of salt.'\n"
            "- You respect expertise. When a speaker knows more than you about "
            "  their domain, you acknowledge it and ask the question that lets "
            "  them show off the really impressive part.\n"
            "- You're the colleague everyone secretly loves arguing with at lunch."
        ),
    },
}

# Current active persona (module-level mutable state)
_active_persona: str = "provocateur"


def get_active_persona() -> dict:
    return PERSONAS[_active_persona]


def set_active_persona(key: str) -> dict:
    global _active_persona
    if key not in PERSONAS:
        raise ValueError(f"Unknown persona: {key}. Options: {list(PERSONAS.keys())}")
    _active_persona = key
    logger.info("Persona switched to: %s (%s)", key, PERSONAS[key]["name"])
    return PERSONAS[key]


def list_personas() -> list[dict]:
    return [
        {"key": k, "name": v["name"], "subtitle": v["subtitle"], "emoji": v["emoji"],
         "active": k == _active_persona}
        for k, v in PERSONAS.items()
    ]


# ---------------------------------------------------------------------------
# LLM Reasoner with persona support
# ---------------------------------------------------------------------------

class LLMReasoner(BaseReasoner):
    """Reasoner backed by OpenAI, Gemini, or Azure OpenAI chat completions."""

    name = "llm"

    def __init__(self, client, model: str = "gpt-4o"):
        self._client = client
        self._model = model

    def _system_prompt(self) -> str:
        persona = get_active_persona()
        return persona["system"] + AUDIENCE_CONTEXT

    async def _chat(self, user_prompt: str) -> str:
        try:
            call = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=2048,
                temperature=0.85,
            )
            resp = await call if inspect.isawaitable(call) else call
            return resp.choices[0].message.content.strip()
        except Exception as exc:
            logger.error("LLM call failed: %s", exc)
            return f"[LLM error: {exc}]"

    async def summarize(self, transcript: str) -> ReasonerResult:
        persona = get_active_persona()
        prompt = (
            f"You are {persona['name']}. Summarize what was just said on stage "
            "in your own voice and style. Write it as a quick debrief for someone "
            "who stepped out — what did they miss, what's worth remembering? "
            "3-4 sentences max. No bullet points.\n\n"
            "Use the speaker briefing (if provided) to add context about what "
            "the speaker was trying to convey, but focus on what was actually said.\n\n"
            f"{transcript[-6000:]}"
        )
        text = await self._chat(prompt)
        return ReasonerResult(text, "llm")

    async def suggest_questions(self, transcript: str, n: int = 3) -> ReasonerResult:
        persona = get_active_persona()
        prompt = (
            f"You are {persona['name']}. You've been listening to this full talk. "
            f"Suggest {n} follow-up questions the human moderator could ask now. "
            "Stay in character.\n\n"
            "Rules:\n"
            "- Use BOTH the speaker briefing (their prepared materials) and the "
            "  live transcript to find gaps — things they claimed in slides but "
            "  didn't explain on stage, or things they said live that contradicted "
            "  or went beyond their prepared materials.\n"
            "- Each question must target something specific, not a generic topic.\n"
            "- At least one should probe a weak spot or vague claim.\n"
            "- At least one should connect to the audience's real work "
            "  (building products, shipping at scale, working with real customers).\n"
            "- Keep each question to 1-2 sentences. No preamble.\n"
            "- No generic filler like 'what challenges' or 'where do you see this going.'\n\n"
            f"{transcript[-6000:]}"
        )
        text = await self._chat(prompt)
        return ReasonerResult(text, "llm")

    async def draft_response(self, transcript: str) -> ReasonerResult:
        persona = get_active_persona()
        prompt = (
            f"Draft a short spoken line (2-3 sentences) that {persona['name']} "
            "would say out loud on stage right now. This gets displayed on a screen "
            "next to the human moderator.\n\n"
            "The line should: react to something specific that was just said, "
            "stay fully in character, and hand the conversation back to the human "
            "moderator or the speaker. Write it as spoken language.\n"
            "If a speaker briefing is available, you can reference what was in "
            "the slides vs. what was actually said.\n\n"
            f"{transcript[-6000:]}"
        )
        text = await self._chat(prompt)
        return ReasonerResult(text, "llm")

    async def compress_transcript(self, existing_summary: str, new_chunk: str) -> str:
        """Compress older transcript into a rolling summary."""
        prompt = (
            "You are compressing a conference talk transcript into a running summary. "
            "Merge the existing summary with the new chunk of transcript. "
            "Keep all important facts, claims, numbers, and topics. "
            "Drop filler, repetition, and um/uh. Stay under 300 words.\n\n"
        )
        if existing_summary:
            prompt += f"EXISTING SUMMARY:\n{existing_summary}\n\n"
        prompt += f"NEW TRANSCRIPT CHUNK:\n{new_chunk}"

        try:
            call = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
                temperature=0.3,
            )
            resp = await call if inspect.isawaitable(call) else call
            return resp.choices[0].message.content.strip()
        except Exception as exc:
            logger.error("Transcript compression failed: %s", exc)
            # Fallback: just concatenate
            return (existing_summary + "\n" + new_chunk)[:2000]

    @property
    def client(self):
        return self._client

    @property
    def model_name(self) -> str:
        return self._model


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def build_llm_reasoner_or_none():
    """Try to build an LLM reasoner from available env vars. Returns None if no keys."""
    from app.config import settings

    # Gemini first — free tier, most likely to be properly configured
    if settings.has_gemini:
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(
                api_key=settings.gemini_api_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            )
            logger.info("LLMReasoner initialized with Gemini (OpenAI-compatible)")
            return LLMReasoner(client, model="gemini-2.5-flash")
        except Exception as exc:
            logger.warning("Failed to init Gemini client: %s", exc)

    # Native Groq support
    if settings.has_groq:
        try:
            from groq import Groq
            client = Groq(api_key=settings.groq_api_key)
            logger.info("LLMReasoner initialized with Groq native client")
            return LLMReasoner(client, model=settings.groq_model)
        except Exception as exc:
            logger.warning("Failed to init native Groq client: %s", exc)

    # OpenAI / OpenRouter / Groq fallback via OpenAI-compatible client
    if settings.has_openai:
        try:
            from openai import AsyncOpenAI
            import socket
            openai_kwargs = {"api_key": settings.openai_api_key}
            key = settings.openai_api_key
            custom_base_url = settings.openai_api_base_url.strip()
            if key.startswith("sk-or-"):
                # OpenRouter via main domain (openrouter.ai)
                openai_kwargs["base_url"] = custom_base_url or "https://openrouter.ai/v1"
                if custom_base_url:
                    logger.info("LLMReasoner initialized with OpenRouter via OPENAI_API_BASE_URL override")
                elif getattr(settings, "openrouter_force", False):
                    logger.warning("OPENROUTER_FORCE set; skipping OpenRouter DNS check and forcing usage")
                else:
                    try:
                        socket.getaddrinfo('openrouter.ai', 443)
                        logger.info("LLMReasoner initialized with OpenAI via OpenRouter")
                    except Exception:
                        logger.warning("OpenRouter API host not resolvable; falling back to MockReasoner")
                        from app.services.reasoner import MockReasoner
                        return MockReasoner()
            elif key.startswith("gsk_"):
                # Groq API (keys starting with gsk_)
                openai_kwargs["base_url"] = (
                    settings.groq_api_base_url.strip()
                    or custom_base_url
                    or "https://api.groq.ai/v1"
                )
                if settings.groq_api_base_url:
                    logger.info("LLMReasoner initialized with Groq via GROQ_API_BASE_URL override")
                elif custom_base_url:
                    logger.info("LLMReasoner initialized with Groq via OPENAI_API_BASE_URL override")
                else:
                    try:
                        socket.getaddrinfo('api.groq.ai', 443)
                        logger.info("LLMReasoner initialized with Groq (via OpenAI-compatible client)")
                    except Exception:
                        logger.warning("Groq API host not resolvable; falling back to MockReasoner")
                        from app.services.reasoner import MockReasoner
                        return MockReasoner()
            else:
                if custom_base_url:
                    openai_kwargs["base_url"] = custom_base_url
                    logger.info("LLMReasoner initialized with OpenAI via OPENAI_API_BASE_URL override")
                else:
                    logger.info("LLMReasoner initialized with OpenAI")
            client = AsyncOpenAI(**openai_kwargs)
            return LLMReasoner(client, model="gpt-4o")
        except Exception as exc:
            logger.warning("Failed to init OpenAI client: %s", exc)

    if settings.has_azure_openai:
        try:
            from openai import AsyncAzureOpenAI
            client = AsyncAzureOpenAI(
                api_key=settings.azure_openai_api_key,
                azure_endpoint=settings.azure_openai_endpoint,
                api_version="2024-10-21",
            )
            logger.info("LLMReasoner initialized with Azure OpenAI")
            return LLMReasoner(client, model=settings.azure_openai_deployment)
        except Exception as exc:
            logger.warning("Failed to init Azure OpenAI client: %s", exc)

    return None
