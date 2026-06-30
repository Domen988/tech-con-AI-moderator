from __future__ import annotations

import os
import tempfile
from typing import Optional

from app.config import settings
from app.logging_setup import logger

try:
    import azure.cognitiveservices.speech as speechsdk
    HAS_SPEECH_SDK = True
except ImportError:  # pragma: no cover
    HAS_SPEECH_SDK = False
    logger.warning("Azure Speech SDK not installed. Text-to-speech disabled.")


class TTSService:
    def _build_config(self) -> object:
        if not HAS_SPEECH_SDK:
            raise RuntimeError("Azure Speech SDK not installed")
        if not settings.has_azure_speech:
            raise RuntimeError("AZURE_SPEECH_KEY and AZURE_SPEECH_REGION must be set")

        speech_config = speechsdk.SpeechConfig(
            subscription=settings.azure_speech_key,
            region=settings.azure_speech_region_name,
        )
        speech_config.speech_synthesis_voice_name = "en-US-AriaNeural"
        speech_config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Audio16Khz32KBitRateMonoMp3
        )
        return speech_config

    def synthesize_text(self, text: str) -> bytes:
        if not text or not text.strip():
            raise ValueError("Text must be provided for speech synthesis")
        speech_config = self._build_config()
        synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=speech_config,
            audio_config=None,
        )

        result = synthesizer.speak_text_async(text).get()
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            # Newer SDKs expose raw bytes on the result
            if getattr(result, "audio_data", None):
                return result.audio_data

            # Otherwise use AudioDataStream and save to a temporary file
            audio_stream = speechsdk.AudioDataStream(result)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                tmp_path = tmp.name
            try:
                audio_stream.save_to_wav_file(tmp_path)
                with open(tmp_path, "rb") as fp:
                    return fp.read()
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        if result.reason == speechsdk.ResultReason.Canceled:
            cancellation = speechsdk.CancellationDetails(result)
            raise RuntimeError(
                f"TTS canceled: {cancellation.reason} - {cancellation.error_details}"
            )

        raise RuntimeError(f"TTS synthesis failed: {result.reason}")


tts = TTSService()
