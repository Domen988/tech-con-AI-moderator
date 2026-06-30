from __future__ import annotations

import re
from pydantic_settings import BaseSettings
from pydantic import Field, model_validator


class Settings(BaseSettings):
    # Required
    azure_speech_key: str = Field(default="")
    azure_speech_region: str = Field(default="")
    azure_speech_endpoint: str = Field(default="")

    # Optional LLM backends
    openai_api_key: str = Field(default="")
    openai_api_base_url: str = Field(default="")
    groq_api_key: str = Field(default="")
    groq_api_base_url: str = Field(default="")
    groq_model: str = Field(default="llama-3.3-70b-versatile")
    gemini_api_key: str = Field(default="")
    azure_openai_api_key: str = Field(default="")
    azure_openai_endpoint: str = Field(default="")
    azure_openai_deployment: str = Field(default="")
    azure_speech_free_minutes: int = Field(default=0)

    # Optional avatar service (full video talking head)
    avatar_api_key: str = Field(default="")
    avatar_api_url: str = Field(default="")
    avatar_model: str = Field(default="default-avatar")
    avatar_character: str = Field(default="lisa")
    avatar_style: str = Field(default="casual-sitting")

    # App
    log_level: str = Field(default="INFO")
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    # Force using OpenRouter even if DNS checks fail (use with caution)
    openrouter_force: bool = Field(default=False)

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @model_validator(mode="after")
    def _normalize_azure_speech_settings(self) -> "Settings":
        if not self.azure_speech_region.strip():
            endpoint = (self.azure_speech_endpoint or "").strip().lower()
            if endpoint.startswith("https://"):
                endpoint = endpoint[8:]
            if endpoint.startswith("http://"):
                endpoint = endpoint[7:]
            if endpoint.endswith("/"):
                endpoint = endpoint[:-1]
            if ".api.cognitive.microsoft.com" in endpoint:
                self.azure_speech_region = endpoint.split(".")[0]
        self.azure_speech_region = self.azure_speech_region.strip().lower()
        self.azure_speech_endpoint = self.azure_speech_endpoint.strip()
        return self

    @staticmethod
    def _is_api_key_placeholder(value: str) -> bool:
        if not value:
            return False
        norm = value.strip().lower()
        if norm in {
            "your-api-key",
            "your-api-key-here",
            "your-openai-key",
            "your_openai_key",
            "your_openai_api_key",
            "your-azure-speech-key",
            "your-key",
            "your_key",
            "your_key_here",
            "replace_me",
            "changeme",
            "none",
        }:
            return True
        return bool("your" in norm and ("api" in norm or "key" in norm or "openai" in norm))

    @property
    def azure_speech_region_name(self) -> str:
        region = (self.azure_speech_region or "").strip().lower()
        if region:
            return region
        endpoint = (self.azure_speech_endpoint or "").strip().lower()
        if endpoint.startswith("https://"):
            endpoint = endpoint[8:]
        if endpoint.startswith("http://"):
            endpoint = endpoint[7:]
        if endpoint.endswith("/"):
            endpoint = endpoint[:-1]
        if ".api.cognitive.microsoft.com" in endpoint:
            region = endpoint.split(".")[0]
            return region
        return region

    @property
    def has_azure_speech(self) -> bool:
        return bool(
            self.azure_speech_key
            and self.azure_speech_region_name
            and not self._is_api_key_placeholder(self.azure_speech_key)
        )

    @property
    def azure_speech_free_seconds(self) -> int:
        return max(0, self.azure_speech_free_minutes * 60)

    @property
    def has_openai(self) -> bool:
        return bool(
            self.openai_api_key
            and not self._is_api_key_placeholder(self.openai_api_key)
        )

    @property
    def has_groq(self) -> bool:
        return bool(
            self.groq_api_key
            and not self._is_api_key_placeholder(self.groq_api_key)
        )

    @property
    def has_gemini(self) -> bool:
        return bool(
            self.gemini_api_key
            and not self._is_api_key_placeholder(self.gemini_api_key)
        )

    @property
    def has_azure_openai(self) -> bool:
        return bool(
            self.azure_openai_api_key
            and not self._is_api_key_placeholder(self.azure_openai_api_key)
            and self.azure_openai_endpoint
            and self.azure_openai_deployment
        )

    @property
    def has_avatar_service(self) -> bool:
        return bool(
            self.avatar_api_key
            and self.avatar_api_url
            and not self._is_api_key_placeholder(self.avatar_api_key)
        )

    def print_status(self) -> None:
        print("\n╔══════════════════════════════════════════╗")
        print("║   AI Conference Moderator - PoC          ║")
        print("╠══════════════════════════════════════════╣")
        ok = "✓"
        no = "✗"
        print(f"║ Azure Speech-to-Text:  {ok if self.has_azure_speech else no}               ║")
        print(f"║ OpenAI LLM:            {ok if self.has_openai else no} {'(available)' if self.has_openai else '(mock mode)'}    ║")
        print(f"║ Groq LLM:              {ok if self.has_groq else no} {'(available)' if self.has_groq else '(mock mode)'}    ║")
        print(f"║ Gemini LLM:            {ok if self.has_gemini else no} {'(available)' if self.has_gemini else '(mock mode)'}    ║")
        print(f"║ Azure OpenAI LLM:      {ok if self.has_azure_openai else no} {'(available)' if self.has_azure_openai else '(mock mode)'}    ║")
        print("╚══════════════════════════════════════════╝")

        if not self.has_azure_speech:
            print("\n⚠  AZURE_SPEECH_KEY / AZURE_SPEECH_REGION not set or appears to be a placeholder.")
            print("   Transcription will not work. Set them in .env")
            print("   The UI will still load, but listening will fail.\n")

        if self.openai_api_key and not self.has_openai:
            print("⚠  OPENAI_API_KEY looks like a placeholder value and will be ignored.")
            print("   Replace it with a real key in .env or your environment.")

        if not self.has_openai and not self.has_gemini and not self.has_azure_openai:
            print("ℹ  No valid LLM key found. Running with MockReasoner.")
            print("   Add GEMINI_API_KEY or OPENAI_API_KEY to .env for real AI generation.")
            if self.openrouter_force:
                print("   Note: OPENROUTER_FORCE is set; attempting to use OpenRouter despite DNS checks.")
            print()


settings = Settings()
