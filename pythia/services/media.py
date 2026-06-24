import asyncio
import json
import subprocess
from pathlib import Path


class MediaError(Exception):
    pass


def frame_timestamps(duration: float, count: int) -> list[float]:
    if duration <= 0 or count <= 0:
        raise ValueError("duration and count must be positive")
    return [round(duration * index / (count + 1), 3) for index in range(1, count + 1)]


def audio_command(video_path: Path, audio_path: Path) -> list[str]:
    return [
        "ffmpeg", "-y", "-i", str(video_path), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", str(audio_path),
    ]


def frame_command(video_path: Path, timestamp: float, output_path: Path) -> list[str]:
    return [
        "ffmpeg", "-y", "-ss", str(timestamp), "-i", str(video_path), "-frames:v", "1",
        "-vf", "scale='min(1024,iw)':-2", str(output_path),
    ]


class MediaProcessor:
    def __init__(self, frame_count: int) -> None:
        self._frame_count = frame_count

    @staticmethod
    def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(command, check=True, capture_output=True, text=True)
        except FileNotFoundError as error:
            raise MediaError("ffmpeg/ffprobe is not installed in the runtime image.") from error
        except subprocess.CalledProcessError as error:
            raise MediaError(error.stderr[-1000:]) from error

    async def duration(self, video_path: Path) -> float:
        command = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(video_path)]
        result = await asyncio.to_thread(self._run, command)
        try:
            return float(json.loads(result.stdout)["format"]["duration"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise MediaError("ffprobe did not return a video duration.") from error

    async def extract_audio(self, video_path: Path, destination: Path) -> Path:
        audio_path = destination / "audio.mp3"
        await asyncio.to_thread(self._run, audio_command(video_path, audio_path))
        return audio_path

    async def extract_frames(self, video_path: Path, duration: float, destination: Path) -> list[Path]:
        frames_dir = destination / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        for number, timestamp in enumerate(frame_timestamps(duration, self._frame_count), start=1):
            frame_path = frames_dir / f"frame-{number:02d}.jpg"
            await asyncio.to_thread(self._run, frame_command(video_path, timestamp, frame_path))
            paths.append(frame_path)
        return paths
