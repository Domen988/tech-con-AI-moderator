from app.config import Settings


def test_speech_settings_accept_endpoint_and_infer_region():
    settings = Settings(
        _env_file=None,
        azure_speech_key="test-key",
        azure_speech_endpoint="https://westeurope.api.cognitive.microsoft.com/",
        azure_speech_region="",
    )

    assert settings.azure_speech_region == "westeurope"
    assert settings.azure_speech_endpoint == "https://westeurope.api.cognitive.microsoft.com/"
    assert settings.has_azure_speech is True
