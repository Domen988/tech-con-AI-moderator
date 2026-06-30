from __future__ import annotations

import json
import urllib.request
import urllib.error

from app.config import settings
from app.logging_setup import logger


class AvatarService:
    def __init__(self):
        self.api_url = settings.avatar_api_url
        self.api_key = settings.avatar_api_key
        self.model = settings.avatar_model
        self.character = settings.avatar_character
        self.style = settings.avatar_style

    @property
    def is_configured(self) -> bool:
        return bool(self.api_url and self.api_key)

    def get_config(self) -> dict:
        return {
            "model": self.model,
            "character": self.character,
            "style": self.style,
        }

    def supports_azure_avatar(self) -> bool:
        return settings.has_azure_speech

    def fetch_azure_relay_token(self) -> dict:
        if not self.supports_azure_avatar():
            raise RuntimeError("Azure Speech key and region must be configured for avatar relay token generation.")

        token_url = (
            f"https://{settings.azure_speech_region_name}.tts.speech.microsoft.com"
            "/cognitiveservices/avatar/relay/token/v1"
        )
        headers = {
            "Ocp-Apim-Subscription-Key": settings.azure_speech_key,
            "Accept": "application/json",
        }

        def parse_body(body: str) -> dict:
            payload = body.strip()
            if not payload:
                raise RuntimeError("Empty response from avatar relay token endpoint")

            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                data = {"authorizationToken": payload}

            if isinstance(data, str):
                data = {"authorizationToken": data}
            if "token" in data and "authorizationToken" not in data:
                data["authorizationToken"] = data["token"]

            if "iceServers" not in data:
                if all(key in data for key in ("Urls", "Username", "Password")):
                    data["iceServers"] = [{
                        "urls": data["Urls"],
                        "username": data["Username"],
                        "credential": data["Password"],
                    }]

            if "authorizationToken" not in data and not data.get("iceServers"):
                raise RuntimeError(
                    "Relay token response did not include an authorization token or ICE server credentials"
                )

            data.setdefault("iceServers", [])
            data["region"] = settings.azure_speech_region_name
            return data

        def request_token(method: str):
            request = urllib.request.Request(token_url, headers=headers, method=method)
            with urllib.request.urlopen(request, timeout=15) as response:
                return response.read().decode("utf-8")

        try:
            try:
                body = request_token("GET")
            except urllib.error.HTTPError as exc:
                if exc.code in {404, 405}:
                    body = request_token("POST")
                else:
                    body = exc.read().decode("utf-8", errors="ignore")
                    raise RuntimeError(
                        f"Azure avatar relay token request failed ({exc.code}): {body or exc.reason}"
                    )

            data = parse_body(body)

            # If the relay endpoint returned ICE server credentials but no authorization token,
            # try obtaining a short-lived STS token as a fallback so the browser can authenticate
            # with Azure Speech services for avatar signaling.
            if not data.get("authorizationToken"):
                try:
                    sts_url = f"https://{settings.azure_speech_region_name}.api.cognitive.microsoft.com/sts/v1.0/issueToken"
                    sts_req = urllib.request.Request(sts_url, headers={
                        "Ocp-Apim-Subscription-Key": settings.azure_speech_key,
                        "Accept": "text/plain",
                    }, method="POST")
                    with urllib.request.urlopen(sts_req, timeout=10) as sts_resp:
                        token = sts_resp.read().decode("utf-8").strip()
                        if token:
                            data["authorizationToken"] = token
                except Exception:
                    # Non-fatal: leave data as-is (we'll surface ICE servers if present)
                    pass

            return data
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(
                f"Azure avatar relay token request failed ({exc.code}): {body or exc.reason}"
            )
        except Exception as exc:
            raise RuntimeError(f"Azure avatar relay token request failed: {exc}")

    def generate_video(self, text: str) -> bytes:
        if not self.is_configured:
            raise RuntimeError("Avatar service is not configured. Set AVATAR_API_URL and AVATAR_API_KEY.")
        logger.info(
            "AvatarService.generate_video() using character=%s style=%s model=%s",
            self.character,
            self.style,
            self.model,
        )
        logger.warning(
            "AvatarService.generate_video() called, but no concrete avatar provider is implemented yet."
        )
        raise NotImplementedError(
            "Configure an external avatar generation service and implement the provider integration."
        )


avatar = AvatarService()
