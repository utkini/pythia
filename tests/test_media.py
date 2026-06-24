from pathlib import Path

import pytest

from pythia.services.media import audio_command, frame_command, frame_timestamps


def test_frame_timestamps_are_evenly_distributed() -> None:
    assert frame_timestamps(90, 8) == [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0]


@pytest.mark.parametrize("duration,count", [(0, 8), (10, 0)])
def test_frame_timestamps_require_positive_values(duration: float, count: int) -> None:
    with pytest.raises(ValueError):
        frame_timestamps(duration, count)


def test_ffmpeg_commands_keep_input_and_output_paths() -> None:
    video = Path("/tmp/video.mp4")
    audio = Path("/tmp/audio.mp3")
    frame = Path("/tmp/frame.jpg")
    assert audio_command(video, audio)[0] == "ffmpeg"
    assert str(video) in audio_command(video, audio)
    assert str(audio) == audio_command(video, audio)[-1]
    assert "-ss" in frame_command(video, 12.5, frame)
    assert str(frame) == frame_command(video, 12.5, frame)[-1]
