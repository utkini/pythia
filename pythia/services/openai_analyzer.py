import base64
import json
from pathlib import Path

from openai import AsyncOpenAI

from pythia.config import settings
from pythia.schemas import ContentAnalysis, ReelMetadata


class AnalysisError(Exception):
    pass


ANALYSIS_INSTRUCTIONS = """You analyse a public Instagram Reel for a Russian-speaking creator.
Use the transcript, engagement metadata, and chronological video frames. Return only JSON with:
summary (Russian, max 3 sentences), topics (array), screen_text, hook, cta,
content_format, sentiment, language, key_frame_index (zero-based index in the supplied frames).
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
            raise AnalysisError("OpenAI transcription request failed.") from error

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
            raw = response.choices[0].message.content
            if not raw:
                raise AnalysisError("OpenAI returned an empty analysis.")
            result = ContentAnalysis.model_validate_json(raw)
            result.key_frame_index = min(result.key_frame_index, max(len(frames) - 1, 0))
            return result
        except AnalysisError:
            raise
        except Exception as error:
            raise AnalysisError("OpenAI visual analysis request failed.") from error

    async def close(self) -> None:
        await self._client.close()
