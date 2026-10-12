# Local Faster-Whisper Transcription

> Status (2026-10-12): deferred. The current direction is to keep transcription
> on the OpenAI API. This local transcription plan is retained for reference
> and is not part of the active implementation scope.

## Overview
- Add a free local transcription option using `faster-whisper` so Pythia can transcribe Reel audio without OpenAI API credits.
- Keep the existing OpenAI transcription path available as a fallback through configuration.
- Preserve the current pipeline shape: Instagram download -> ffmpeg audio extraction -> transcription -> OpenAI vision/content analysis -> Telegram report.
- Target MVP defaults: `base` model, `cpu`, `int8`, with an option to switch to `tiny` for speed or `small` for better Russian/multilingual quality.

## Context (from discovery)
- Relevant files/components:
  - `pythia/config.py`: runtime settings loaded from `.env`.
  - `pythia/services/openai_analyzer.py`: currently owns both audio transcription and visual/content analysis.
  - `pythia/services/orchestrator.py`: calls `analyzer.transcribe(audio_path)` before visual analysis.
  - `pythia/services/media.py`: already extracts mono 16k audio via ffmpeg, suitable for local ASR.
  - `pyproject.toml` and `uv.lock`: dependency management.
  - `Dockerfile`: runtime image already installs ffmpeg.
- Related patterns found:
  - External-service errors are wrapped in `AnalysisError`.
  - Configuration is environment-driven via Pydantic settings.
  - Tests use small focused unit tests with monkeypatch/fakes.
- Dependencies identified:
  - `faster-whisper` uses CTranslate2 and PyAV; it can run on CPU with `compute_type="int8"`.
  - First model use downloads model weights unless a local model path/cache is already present.
  - Docker image size and first-run startup/download behavior need to be considered.

## Development Approach
- **Testing approach**: Regular, code first with tests in the same task.
- Complete each task fully before moving to the next.
- Make small, focused changes.
- Every code-changing task must add or update tests.
- All targeted tests must pass before starting the next task.
- Update this plan if implementation scope changes.
- Maintain backward compatibility: `TRANSCRIPTION_PROVIDER=openai` should preserve current behavior.

## Testing Strategy
- Unit tests:
  - settings defaults and env overrides;
  - provider selection;
  - OpenAI transcriber success/error wrapping with fakes;
  - local transcriber success/error wrapping with monkeypatched fake `WhisperModel`;
  - analyzer/orchestrator compatibility.
- Integration/manual tests:
  - run local transcription against a generated short mp3/wav fixture;
  - run `/analyze <profile>` with `TRANSCRIPTION_PROVIDER=local`;
  - verify Docker can import `faster_whisper` and instantiate the configured model.
- Full suite:
  - `uv run pytest`
  - note: currently one pre-existing database URL test may fail until the Supabase `sslmode` conversion issue is fixed.

## Progress Tracking
- Mark completed items with `[x]` immediately when done.
- Add newly discovered tasks with ➕ prefix.
- Document blockers with ⚠️ prefix.
- Keep this plan in sync with implementation.

## Solution Overview
- Introduce a small transcription abstraction:
  - `Transcriber` protocol or base interface with `transcribe(audio_path: Path) -> str`.
  - `OpenAITranscriber` for the current cloud path.
  - `FasterWhisperTranscriber` for local ASR.
- Keep `OpenAIAnalyzer` focused on visual/content analysis, while receiving a transcriber dependency or delegating transcription to a selected transcriber.
- Select provider at application startup from settings:
  - `TRANSCRIPTION_PROVIDER=openai` for current behavior.
  - `TRANSCRIPTION_PROVIDER=local` for free local transcription.
- Use lazy local model initialization so the model loads only when transcription is first needed.

## Technical Details
- Proposed env variables:
  ```env
  TRANSCRIPTION_PROVIDER=local
  LOCAL_TRANSCRIPTION_MODEL=base
  LOCAL_TRANSCRIPTION_DEVICE=cpu
  LOCAL_TRANSCRIPTION_COMPUTE_TYPE=int8
  LOCAL_TRANSCRIPTION_LANGUAGE=
  ```
- Suggested defaults:
  - `transcription_provider="openai"` for backward compatibility.
  - `local_transcription_model="base"`.
  - `local_transcription_device="cpu"`.
  - `local_transcription_compute_type="int8"`.
  - `local_transcription_language=None`, allowing language auto-detect.
- Local transcription flow:
  ```text
  audio.mp3
  -> FasterWhisperTranscriber.transcribe()
  -> WhisperModel(...).transcribe(audio_path, vad_filter=True)
  -> concatenate segment.text
  -> transcript string
  ```
- Error behavior:
  - local transcription exceptions should become `AnalysisError("Local transcription failed.")`;
  - empty local transcripts should be allowed, matching current `[no speech recognised]` downstream behavior.
- Docker/runtime considerations:
  - `faster-whisper` may increase image size and install time;
  - first model download may take time and network access;
  - later improvement: mount a model cache volume or pre-bake a small model.

## What Goes Where
- **Implementation Steps**: code, tests, docs, Docker validation.
- **Post-Completion**: manual model download/cache choices, production deployment tuning, OpenAI billing decision for vision analysis.

## Implementation Steps

### Task 1: Add Transcription Configuration

**Files:**
- Modify: `pythia/config.py`
- Modify: `.env.example`
- Modify: `.env.local.example`
- Modify: `README.md`
- Create/Modify tests: `tests/test_config.py` or existing relevant settings tests

- [ ] add `transcription_provider` setting with default `openai`
- [ ] add local transcription settings for model, device, compute type, and optional language
- [ ] document `TRANSCRIPTION_PROVIDER=local` in `.env.example` and `.env.local.example`
- [ ] update README with a short local transcription configuration section
- [ ] write tests for default settings and env overrides
- [ ] run targeted config tests before Task 2

### Task 2: Introduce Transcriber Abstraction

**Files:**
- Create: `pythia/services/transcription.py`
- Modify: `pythia/services/openai_analyzer.py`
- Create/Modify tests: `tests/test_transcription.py`, `tests/test_openai_analyzer.py` if needed

- [ ] define a minimal `Transcriber` protocol/interface
- [ ] move current OpenAI audio transcription logic into `OpenAITranscriber`
- [ ] keep `AnalysisError` wrapping behavior compatible with the current user-facing flow
- [ ] update `OpenAIAnalyzer` so visual analysis remains separate from transcription implementation
- [ ] write tests for OpenAI transcription success and failure using a fake OpenAI client or monkeypatch
- [ ] run targeted transcription/analyzer tests before Task 3

### Task 3: Add Faster-Whisper Local Transcriber

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `pythia/services/transcription.py`
- Create/Modify tests: `tests/test_transcription.py`

- [ ] add `faster-whisper` dependency
- [ ] implement `FasterWhisperTranscriber` with lazy `WhisperModel` initialization
- [ ] use configured model/device/compute type/language
- [ ] enable `vad_filter=True` for noisy or silent Reels
- [ ] concatenate generated segments into a normalized transcript string
- [ ] wrap local model/load/transcription failures in `AnalysisError`
- [ ] write tests with a monkeypatched fake `WhisperModel` covering success, empty transcript, and failure
- [ ] run targeted transcription tests before Task 4

### Task 4: Wire Provider Selection Into the Bot

**Files:**
- Modify: `pythia/bot.py`
- Modify: `pythia/services/orchestrator.py` only if needed
- Create/Modify tests: `tests/test_bot.py` or `tests/test_transcription.py`

- [ ] create a small factory such as `build_transcriber(settings)`
- [ ] inject the selected transcriber into the analyzer/service at startup
- [ ] preserve current behavior when `TRANSCRIPTION_PROVIDER=openai`
- [ ] use local transcription when `TRANSCRIPTION_PROVIDER=local`
- [ ] return a clear configuration error for unsupported provider values
- [ ] write tests for provider selection and injection
- [ ] run targeted bot/transcription tests before Task 5

### Task 5: Validate Docker Runtime

**Files:**
- Modify: `Dockerfile` only if extra system packages are required
- Modify: `docker-compose.local.yml` only if cache volumes/env are needed
- Create/Modify tests: none unless runtime checks are codified

- [ ] rebuild the local image with `faster-whisper`
- [ ] verify `uv run python -c "import faster_whisper"` works inside the container
- [ ] generate a 1-second test audio file with ffmpeg inside the container
- [ ] run local transcriber manually against the generated audio
- [ ] decide whether to mount a model cache volume for local development
- [ ] document any Docker image size/startup tradeoffs discovered

### Task 6: End-to-End Local Transcription Smoke Test

**Files:**
- Modify: `README.md` if manual steps change
- Modify: this plan if new blockers are discovered

- [ ] set `.env.local` to `TRANSCRIPTION_PROVIDER=local`
- [ ] run migrations if needed: `uv run alembic upgrade head` or Docker migrate service
- [ ] start local stack: `docker compose -f docker-compose.local.yml up --build`
- [ ] run `/analyze https://www.instagram.com/<public_profile>/` from Telegram
- [ ] verify transcript appears in the Telegram report or empty speech is handled gracefully
- [ ] verify OpenAI vision/content analysis is still the only remaining OpenAI API dependency
- [ ] capture performance notes for `tiny`, `base`, and optionally `small`

### Task 7: Verify Acceptance Criteria

- [ ] `TRANSCRIPTION_PROVIDER=openai` keeps the existing OpenAI transcription behavior
- [ ] `TRANSCRIPTION_PROVIDER=local` avoids OpenAI audio transcription API calls
- [ ] local transcription errors produce the existing user-facing AI failure behavior
- [ ] Telegram report generation still includes transcript text when available
- [ ] all targeted tests pass
- [ ] run full test suite: `uv run pytest`
- [ ] note or fix any pre-existing unrelated failures, especially the Supabase `sslmode` test

### Task 8: Final Documentation and Cleanup

**Files:**
- Modify: `README.md`
- Modify: `.env.example`
- Modify: `.env.local.example`
- Optionally modify: `docs/plans/20260809-local-faster-whisper-transcription.md`

- [ ] document model quality/speed tradeoffs: `tiny`, `base`, `small`
- [ ] document first-run model download behavior
- [ ] document that OpenAI API may still be required for visual/content analysis unless a future local vision path is added
- [ ] remove or ignore local Instaloader scratch folders from previous manual tests if appropriate
- [ ] move this plan to `docs/plans/completed/` after implementation is complete

## Post-Completion

**Manual verification**
- Try at least one Russian-speaking Reel and one English-speaking Reel.
- Compare `tiny`, `base`, and `small` on the same Reel for quality and runtime.
- Confirm acceptable runtime on the actual target machine, especially if deploying to Raspberry Pi.

**External system updates**
- If deploying with Docker, decide where model cache should live.
- If keeping OpenAI only for vision/content analysis, ensure API credits are enough for that reduced usage.
- If later removing OpenAI entirely, create a separate plan for local vision/OCR/script analysis.
