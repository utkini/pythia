import base64
import json
from pathlib import Path

import structlog
from openai import APIConnectionError, APIStatusError, AsyncOpenAI
from pydantic import ValidationError

from pythia.config import settings
from pythia.schemas import ContentAnalysis, ReelMetadata


logger = structlog.get_logger(__name__)


class AnalysisError(Exception):
    pass


ANALYSIS_INSTRUCTIONS = """You analyse a public Instagram Reel for a Russian-speaking creator.
Use the transcript, engagement metadata, and chronological video frames. Return only JSON with:
summary (Russian, max 3 sentences), topics (array), screen_text, hook, cta,
content_format, sentiment, language, key_frame_index (zero-based index in the supplied frames).
screen_text must be a single string: join visible text lines with newline characters;
use an empty string when no text is visible. topics must be an array of strings.
Do not invent information that is absent from the frames or transcript."""


class OpenAIAnalyzer:
    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout=settings.external_timeout_seconds,
            max_retries=2,
        )
        self._transcription_model = settings.openai_transcription_model
        self._vision_model = settings.openai_vision_model

    async def transcribe(self, audio_path: Path) -> str:
        try:
            with audio_path.open("rb") as audio_file:
                response = await self._client.audio.transcriptions.create(
                    model=self._transcription_model,
                    file=audio_file,
                )
            return response.text.strip()
        except Exception as error:
            raise self._failure("transcription", self._transcription_model, error) from error

    @staticmethod
    def _failure(stage: str, model: str, error: Exception) -> AnalysisError:
        details: dict[str, object] = {"stage": stage, "model": model, "error_type": type(error).__name__}
        reason = "unexpected_error"
        if isinstance(error, APIStatusError):
            reason = "api_status_error"
            details.update(status=error.status_code, request_id=error.request_id)
        elif isinstance(error, APIConnectionError):
            reason = "connection_error"
        elif isinstance(error, ValidationError):
            reason = "invalid_response_schema"
            # Never log the model response or validation inputs.
            details["invalid_fields"] = sorted({
                str(item["loc"][0]) for item in error.errors(include_input=False, include_url=False)
                if item["loc"] and item["loc"][0] in ContentAnalysis.model_fields
            })
        logger.warning("openai_analysis_failed", reason=reason, **details)
        return AnalysisError(f"OpenAI {stage} failed: {reason} ({type(error).__name__}).")

    @staticmethod
    def _image_part(path: Path) -> dict:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}", "detail": "low"}}

    async def analyse(self, metadata: ReelMetadata, transcript: str, frames: list[Path]) -> ContentAnalysis:
        metrics = {
            "likes": metadata.likes_count,
            "comments": metadata.comments_count,
            "caption": metadata.caption,
        }
        content: list[dict] = [
            {"type": "text", "text": f"Transcript:\n{transcript or '[no speech recognised]'}\n\nMetadata:\n{json.dumps(metrics, ensure_ascii=False)}"},
        ]
        content.extend(self._image_part(frame) for frame in frames)
        try:
            response = await self._client.chat.completions.create(
                model=self._vision_model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": ANALYSIS_INSTRUCTIONS},
                    {"role": "user", "content": content},
                ],
            )
            if not response.choices:
                raise AnalysisError("OpenAI returned no analysis choices.")
            choice = response.choices[0]
            if choice.message.refusal:
                raise AnalysisError("OpenAI declined the visual analysis.")
            if choice.finish_reason != "stop":
                raise AnalysisError("OpenAI returned an incomplete visual analysis.")
            raw = choice.message.content
            if not raw:
                raise AnalysisError("OpenAI returned an empty analysis.")
            result = ContentAnalysis.model_validate_json(raw)
            result.key_frame_index = min(result.key_frame_index, max(len(frames) - 1, 0))
            return result
        except AnalysisError:
            raise
        except Exception as error:
            raise self._failure("visual_analysis", self._vision_model, error) from error

    async def close(self) -> None:
        await self._client.close()
