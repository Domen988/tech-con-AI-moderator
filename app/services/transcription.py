from __future__ import annotations

import asyncio
import threading
from datetime import timedelta
from typing import Callable, Optional

from app.config import settings
from app.logging_setup import logger

try:
    import azure.cognitiveservices.speech as speechsdk
    HAS_SPEECH_SDK = True
except ImportError:
    HAS_SPEECH_SDK = False
    logger.warning("azure-cognitiveservices-speech not installed. Transcription disabled.")


class TranscriptionService:
    """Wraps Azure Speech SDK continuous recognition.

    Callbacks run on SDK threads, so we push events into an asyncio queue
    that the WebSocket handler can await.
    """

    def __init__(self):
        self._recognizer: Optional[object] = None
        self._running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._queue: Optional[asyncio.Queue] = None
        self._consumed_audio_seconds = 0.0

    @property
    def is_running(self) -> bool:
        return self._running

    def _build_config(self):
        if not HAS_SPEECH_SDK:
            raise RuntimeError("Azure Speech SDK not installed")
        if not settings.has_azure_speech:
            raise RuntimeError(
                "AZURE_SPEECH_KEY and AZURE_SPEECH_REGION must be set in .env"
            )

        speech_config = speechsdk.SpeechConfig(
            subscription=settings.azure_speech_key,
            region=settings.azure_speech_region_name,
        )
        speech_config.speech_recognition_language = "en-US"

        # Lower latency
        speech_config.set_property(
            speechsdk.PropertyId.Speech_SegmentationSilenceTimeoutMs, "800"
        )
        speech_config.set_profanity(speechsdk.ProfanityOption.Raw)
        speech_config.output_format = speechsdk.OutputFormat.Detailed

        # Enable SDK-level logging for diagnostics
        speech_config.set_property(
            speechsdk.PropertyId.Speech_LogFilename, ""
        )

        return speech_config

    def _build_recognizer(self):
        speech_config = self._build_config()
        audio_config = speechsdk.audio.AudioConfig(use_default_microphone=True)
        return speechsdk.SpeechRecognizer(
            speech_config=speech_config, audio_config=audio_config
        )

    def _enqueue(self, event_type: str, payload):
        """Thread-safe push into the async queue."""
        if self._loop and self._queue:
            self._loop.call_soon_threadsafe(
                self._queue.put_nowait, {"type": event_type, "payload": payload}
            )

    def _duration_seconds(self, duration) -> float:
        if duration is None:
            return 0.0
        if isinstance(duration, timedelta):
            return duration.total_seconds()
        if hasattr(duration, "total_seconds"):
            try:
                return float(duration.total_seconds())
            except Exception:
                pass
        try:
            return float(duration)
        except Exception:
            return 0.0

    def _update_usage(self, duration):
        seconds = self._duration_seconds(duration)
        if seconds > 0:
            self._consumed_audio_seconds += seconds
        return seconds

    def get_usage(self) -> dict:
        free_seconds = settings.azure_speech_free_seconds
        remaining = None
        if free_seconds > 0:
            remaining = max(0.0, free_seconds - self._consumed_audio_seconds)
        return {
            "consumed_seconds": round(self._consumed_audio_seconds, 2),
            "free_seconds": free_seconds,
            "remaining_seconds": None if remaining is None else round(remaining, 2),
        }

    async def test_connection(self) -> dict:
        """Run a one-shot recognition to test Azure connectivity.
        Returns a dict with status and diagnostics."""
        if not HAS_SPEECH_SDK:
            return {"ok": False, "error": "Azure Speech SDK not installed"}
        if not settings.has_azure_speech:
            return {"ok": False, "error": "AZURE_SPEECH_KEY/AZURE_SPEECH_REGION not set"}

        result = {"ok": False, "error": "Unknown error"}

        try:
            speech_config = self._build_config()
            # Use null audio — we just want to test the network connection
            audio_config = speechsdk.audio.AudioConfig(use_default_microphone=True)
            recognizer = speechsdk.SpeechRecognizer(
                speech_config=speech_config, audio_config=audio_config
            )

            logger.info("Testing Azure Speech connection to %s.api.cognitive.microsoft.com ...",
                        settings.azure_speech_region_name)

            # Single-shot recognition with a short timeout
            done = threading.Event()

            def on_recognized(evt):
                result["ok"] = True
                result["error"] = None
                result["detail"] = "Connection OK — speech recognized"
                done.set()

            def on_canceled(evt):
                cd = evt.cancellation_details
                reason = str(cd.reason)
                error = cd.error_details or ""

                if "401" in error or "Unauthorized" in error:
                    result["error"] = (
                        f"AUTHENTICATION FAILED (401). Your Azure Speech key may be "
                        f"invalid or expired. Region: {settings.azure_speech_region_name}"
                    )
                elif "403" in error or "Forbidden" in error:
                    result["error"] = (
                        f"ACCESS FORBIDDEN (403). Your network or firewall may be blocking "
                        f"access to {settings.azure_speech_region}.api.cognitive.microsoft.com"
                    )
                elif "connection" in error.lower() or "resolve" in error.lower():
                    result["error"] = (
                        f"CONNECTION FAILED. Cannot reach Azure Speech service.\n"
                        f"  Target: wss://{settings.azure_speech_region_name}.stt.speech.microsoft.com\n"
                        f"  Detail: {error}\n"
                        f"  This is likely a firewall/proxy blocking WebSocket connections."
                    )
                elif "timeout" in error.lower():
                    result["error"] = (
                        f"CONNECTION TIMED OUT. The network can't reach Azure.\n"
                        f"  Target: {settings.azure_speech_region_name}.stt.speech.microsoft.com\n"
                        f"  Your company firewall may be blocking this."
                    )
                elif cd.reason == speechsdk.CancellationReason.EndOfStream:
                    result["ok"] = True
                    result["error"] = None
                    result["detail"] = "Connection OK (end of stream — no speech detected, but connection works)"
                else:
                    result["error"] = (
                        f"Cancellation reason: {reason}\n"
                        f"Error details: {error}\n"
                        f"If this persists, your network may be blocking Azure Speech."
                    )
                done.set()

            def on_session_started(evt):
                # If session starts, the connection works
                result["ok"] = True
                result["error"] = None
                result["detail"] = "Connection OK — session established with Azure"
                logger.info("Azure Speech session started successfully")

            recognizer.recognized.connect(on_recognized)
            recognizer.canceled.connect(on_canceled)
            recognizer.session_started.connect(on_session_started)

            recognizer.start_continuous_recognition()

            # Wait up to 8 seconds for a response
            got_event = done.wait(timeout=8)
            recognizer.stop_continuous_recognition()

            if not got_event and result["ok"]:
                # session_started fired but no canceled/recognized — that's fine
                result["detail"] = "Connection OK — listening works"
            elif not got_event:
                result["error"] = (
                    f"NO RESPONSE from Azure after 8 seconds.\n"
                    f"  Target: wss://{settings.azure_speech_region}.stt.speech.microsoft.com\n"
                    f"  Most likely cause: firewall blocking WebSocket (wss://) connections.\n"
                    f"  Ask IT to allow: *.stt.speech.microsoft.com on port 443"
                )

        except Exception as exc:
            result["error"] = f"Exception during connection test: {exc}"

        # Log prominently
        if result["ok"]:
            logger.info("✓ Azure Speech connection test PASSED: %s", result.get("detail", ""))
        else:
            logger.error("✗ Azure Speech connection test FAILED:\n  %s", result["error"])

        return result

    async def start(self, loop: asyncio.AbstractEventLoop) -> asyncio.Queue:
        """Start continuous recognition. Returns an async queue of events."""
        if self._running:
            logger.warning("Transcription already running")
            return self._queue

        self._loop = loop
        self._queue = asyncio.Queue()

        recognizer = self._build_recognizer()

        # Wire callbacks
        def on_recognizing(evt):
            self._enqueue("partial", evt.result.text)

        def on_recognized(evt):
            if evt.result.text:
                self._update_usage(getattr(evt.result, "duration", None))
                self._enqueue("final", evt.result.text)
                self._enqueue("usage", self.get_usage())

        def on_canceled(evt):
            cd = evt.cancellation_details
            error = cd.error_details or ""
            reason = str(cd.reason)

            # Detailed diagnostics in the terminal
            if "401" in error or "Unauthorized" in error:
                logger.error(
                    "╔════════════════════════════════════════════════╗\n"
                    "║  AZURE SPEECH: AUTHENTICATION FAILED (401)    ║\n"
                    "║  Check your AZURE_SPEECH_KEY in .env           ║\n"
                    "╚════════════════════════════════════════════════╝"
                )
                self._enqueue("error", "Authentication failed (401) — check your Azure Speech key")
            elif "403" in error or "Forbidden" in error:
                logger.error(
                    "╔════════════════════════════════════════════════╗\n"
                    "║  AZURE SPEECH: ACCESS FORBIDDEN (403)          ║\n"
                    "║  Network/firewall may be blocking access       ║\n"
                    "╚════════════════════════════════════════════════╝"
                )
                self._enqueue("error", "Access forbidden (403) — firewall may be blocking Azure")
            elif "connection" in error.lower() or "resolve" in error.lower() or "timeout" in error.lower():
                target = f"{settings.azure_speech_region_name}.stt.speech.microsoft.com"
                logger.error(
                    "╔════════════════════════════════════════════════╗\n"
                    "║  AZURE SPEECH: CONNECTION FAILED               ║\n"
                    "║  Cannot reach: %-33s║\n"
                    "║  Likely blocked by company firewall/proxy      ║\n"
                    "║  Ask IT to allow *.stt.speech.microsoft.com    ║\n"
                    "╚════════════════════════════════════════════════╝",
                    target
                )
                self._enqueue("error", f"Connection failed — cannot reach {target}. Firewall?")
            else:
                logger.warning("Speech canceled: %s — %s", reason, error)
                self._enqueue("error", error or f"Speech canceled: {reason}")

        def on_stopped(evt):
            logger.info("Speech session stopped")
            self._enqueue("stopped", "")

        def on_session_started(evt):
            logger.info("Azure Speech session connected successfully")
            self._enqueue("status", "Azure connection established — listening")

        recognizer.recognizing.connect(on_recognizing)
        recognizer.recognized.connect(on_recognized)
        recognizer.canceled.connect(on_canceled)
        recognizer.session_stopped.connect(on_stopped)
        recognizer.session_started.connect(on_session_started)

        recognizer.start_continuous_recognition()
        self._recognizer = recognizer
        self._running = True
        logger.info("Azure STT started — listening on default microphone")
        logger.info("  Target: wss://%s.stt.speech.microsoft.com",
                     settings.azure_speech_region_name)
        return self._queue

    async def stop(self):
        if not self._running or not self._recognizer:
            return
        self._recognizer.stop_continuous_recognition()
        self._running = False
        self._recognizer = None
        logger.info("Azure STT stopped")


# singleton
transcription = TranscriptionService()
