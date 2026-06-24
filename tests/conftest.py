import os


_TEST_ENVIRONMENT = {
    "TELEGRAM_BOT_TOKEN": "test-token",
    "OWNER_TELEGRAM_ID": "1",
    "DATABASE_URL": "postgresql://test:test@localhost:5432/test",
    "OPENAI_API_KEY": "test-key",
    "OPENAI_TRANSCRIPTION_MODEL": "test-transcription-model",
    "OPENAI_VISION_MODEL": "test-vision-model",
}

for key, value in _TEST_ENVIRONMENT.items():
    os.environ.setdefault(key, value)
