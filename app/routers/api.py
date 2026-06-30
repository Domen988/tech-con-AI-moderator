from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile, File, Response
from pydantic import BaseModel

from app.services.session import session
from app.services.tts import tts
from app.services.avatar import avatar
from app.services.reasoner import MockReasoner, BaseReasoner
from app.services.llm_reasoner import (
    build_llm_reasoner_or_none, list_personas, set_active_persona,
    get_active_persona, LLMReasoner,
)
from app.services.briefing import extract_text, generate_synopsis
from app.logging_setup import logger

router = APIRouter(prefix="/api")

# Pick the best available reasoner at startup
_llm = build_llm_reasoner_or_none()
reasoner: BaseReasoner = _llm if _llm else MockReasoner()
logger.info("Active reasoner: %s", reasoner.name)


class ReasonerResponse(BaseModel):
    content: str
    source: str


class SpeakRequest(BaseModel):
    text: str


# -- Persona endpoints --

@router.get("/personas")
async def get_personas():
    return list_personas()


@router.post("/personas/{key}")
async def switch_persona(key: str):
    try:
        persona = set_active_persona(key)
        return {"status": "ok", "key": key, "name": persona["name"],
                "subtitle": persona["subtitle"], "emoji": persona["emoji"]}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


# -- Briefing / file upload --

@router.post("/upload")
async def upload_materials(file: UploadFile = File(...)):
    """Upload a .pptx, .docx, or .txt file. Extracts text and generates a synopsis."""
    if not file.filename:
        raise HTTPException(400, "No file provided")

    allowed = (".pptx", ".docx", ".txt", ".md")
    ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in allowed:
        raise HTTPException(400, f"Unsupported file type: {ext}. Use {', '.join(allowed)}")

    file_bytes = await file.read()
    try:
        raw_text = extract_text(file.filename, file_bytes)
    except Exception as exc:
        raise HTTPException(400, f"Failed to extract text: {exc}")

    if not raw_text.strip():
        raise HTTPException(400, "No text content found in the file")

    # Generate synopsis using LLM if available
    synopsis = ""
    if isinstance(reasoner, LLMReasoner):
        synopsis = await generate_synopsis(raw_text, reasoner.client, reasoner.model_name)
    else:
        # Mock fallback: use first 500 chars as synopsis
        synopsis = f"[MOCK SYNOPSIS — no LLM available]\n\n{raw_text[:500]}"

    session.set_briefing(file.filename, raw_text, synopsis)
    logger.info("Briefing loaded: %s (%d chars extracted, synopsis generated)", file.filename, len(raw_text))

    return {
        "status": "ok",
        "filename": file.filename,
        "extracted_chars": len(raw_text),
        "synopsis": synopsis,
    }


@router.get("/briefing")
async def get_briefing():
    if not session.briefing:
        return {"loaded": False}
    return {
        "loaded": True,
        "filename": session.briefing.filename,
        "synopsis": session.briefing.synopsis,
        "raw_length": len(session.briefing.raw_text),
    }


@router.delete("/briefing")
async def clear_briefing():
    session.clear_briefing()
    return {"status": "cleared"}


# -- Rolling summary --

@router.post("/compress")
async def compress_transcript():
    """Compress older transcript into rolling summary. Call periodically during long talks."""
    if not isinstance(reasoner, LLMReasoner):
        raise HTTPException(400, "Rolling summary requires an LLM reasoner")

    text_to_compress, new_index = session.get_utterances_to_summarize(keep_recent=15)
    if not text_to_compress:
        return {"status": "nothing_to_compress", "utterances": len(session.utterances)}

    new_summary = await reasoner.compress_transcript(session.rolling_summary, text_to_compress)
    session.update_rolling_summary(new_summary, new_index)
    session.add_activity("compress", f"Compressed transcript (keeping last 15 utterances fresh)")
    logger.info("Rolling summary updated, summarized up to utterance %d", new_index)

    return {"status": "ok", "summarized_up_to": new_index, "total": len(session.utterances)}


# -- Session & core actions --

@router.get("/session")
async def get_session():
    return session.snapshot()


@router.post("/summarize", response_model=ReasonerResponse)
async def summarize():
    context = session.build_llm_context(recent_n=30)
    if not context.strip():
        raise HTTPException(400, "No transcript or briefing available yet")
    result = await reasoner.summarize(context)
    session.add_activity("summary", result.content)
    return ReasonerResponse(content=result.content, source=result.source)


@router.post("/questions", response_model=ReasonerResponse)
async def suggest_questions():
    context = session.build_llm_context(recent_n=30)
    if not context.strip():
        raise HTTPException(400, "No transcript or briefing available yet")
    result = await reasoner.suggest_questions(context, n=3)
    session.add_activity("questions", result.content)
    return ReasonerResponse(content=result.content, source=result.source)


@router.post("/response", response_model=ReasonerResponse)
async def draft_response():
    context = session.build_llm_context(recent_n=30)
    if not context.strip():
        raise HTTPException(400, "No transcript or briefing available yet")
    result = await reasoner.draft_response(context)
    session.add_activity("response", result.content)
    return ReasonerResponse(content=result.content, source=result.source)


@router.post("/clear")
async def clear_session():
    session.clear()
    return {"status": "cleared"}


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "reasoner": reasoner.name,
        "has_briefing": session.briefing is not None,
    }


@router.post("/speak")
async def speak(request: SpeakRequest):
    """Synthesize text to speech audio for avatar playback."""
    try:
        audio_bytes = tts.synthesize_text(request.text)
    except Exception as exc:
        raise HTTPException(500, f"Text-to-speech failed: {exc}")
    return Response(content=audio_bytes, media_type="audio/mpeg")


@router.get("/avatar-token")
async def avatar_token():
    """Return a short-lived Azure avatar relay token and ICE servers for browser WebRTC."""
    try:
        token_data = avatar.fetch_azure_relay_token()
    except Exception as exc:
        raise HTTPException(502, f"Could not fetch avatar relay token: {exc}")
    # Log a minimal, non-secret summary to help debugging without printing credentials
    try:
        summary = {
            "hasAuthorization": bool(token_data.get("authorizationToken")),
            "iceServers": len(token_data.get("iceServers") or []),
            "region": token_data.get("region"),
        }
        logger.info("Avatar relay token fetched: %s", summary)
    except Exception:
        logger.info("Avatar relay token fetched")

    # Include avatar config (character/style/model) so the client can construct AvatarConfig
    try:
        cfg = avatar.get_config()
        if isinstance(cfg, dict):
            token_data.update({
                "avatar_character": cfg.get("character"),
                "avatar_style": cfg.get("style"),
                "avatar_model": cfg.get("model"),
            })
    except Exception:
        # non-fatal
        pass

    return token_data


@router.post("/avatar")
async def generate_avatar(request: SpeakRequest):
    """Generate a talking-head avatar video for the provided text."""
    if not avatar.is_configured:
        raise HTTPException(501, "Avatar service not configured. Set AVATAR_API_URL and AVATAR_API_KEY.")
    try:
        video_bytes = avatar.generate_video(request.text)
    except NotImplementedError as exc:
        raise HTTPException(501, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"Avatar generation failed: {exc}")
    return Response(content=video_bytes, media_type="video/mp4")


@router.get("/avatar-diagnostics")
async def avatar_diagnostics():
    """Run quick server-side checks for avatar token + TTS synthesis (non-sensitive summary).
    Returns presence of authorization token / ICE servers and a small TTS audio-length check.
    """
    result = {}
    # Avatar token check
    try:
        token_data = avatar.fetch_azure_relay_token()
        result["token"] = {
            "hasAuthorization": bool(token_data.get("authorizationToken")),
            "iceServers": len(token_data.get("iceServers") or []),
            "region": token_data.get("region"),
        }
    except Exception as exc:
        result["token_error"] = str(exc)

    # TTS check
    try:
        sample = tts.synthesize_text("Diagnostics test")
        result["tts"] = {"ok": True, "audio_length": len(sample)}
    except Exception as exc:
        result["tts"] = {"ok": False, "error": str(exc)}

    return result


@router.post("/test-speech")
async def test_speech_connection():
    """Test Azure Speech connectivity. Reports firewall/auth issues clearly."""
    from app.services.transcription import transcription
    result = await transcription.test_connection()
    return result
