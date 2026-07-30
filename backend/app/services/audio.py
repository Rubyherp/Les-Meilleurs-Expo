"""
Audio beat detection service for dance practice videos.

Extracts audio from uploaded videos and detects musical beats
using FFmpeg (extraction) and librosa (beat tracking).
"""

from __future__ import annotations

import logging
import subprocess

import numpy as np

logger = logging.getLogger(__name__)


def extract_beats(video_path: str) -> dict:
    """Extract beat timestamps and tempo from a dance practice video.

    Uses FFmpeg to extract audio to a WAV pipe, then librosa for
    tempo estimation and beat tracking. Gracefully handles videos
    without an audio stream or silent audio.

    Args:
        video_path: Filesystem path to the video file.

    Returns:
        dict with keys:
            tempo (float): Detected BPM, 0 if unavailable.
            beats (list[float]): Beat timestamps in seconds.
            duration (float): Audio duration in seconds.
            error (str | None): Error description if extraction failed.
    """
    try:
        pcm = _extract_audio_pipe(video_path)
    except _NoAudioStream:
        logger.info("No audio stream in %s, skipping beat detection.", video_path)
        return {"tempo": 0.0, "beats": [], "duration": 0.0, "error": "no_audio_stream"}
    except Exception:
        logger.exception("FFmpeg audio extraction failed for %s", video_path)
        return {"tempo": 0.0, "beats": [], "duration": 0.0, "error": "ffmpeg_failed"}

    if len(pcm) < 44:
        logger.info("Audio too short in %s (%d bytes).", video_path, len(pcm))
        return {"tempo": 0.0, "beats": [], "duration": 0.0, "error": "audio_too_short"}

    sample_rate = 22050
    y = np.frombuffer(pcm[44:], dtype=np.int16).astype(np.float32) / 32768.0

    # Silence check
    if float(np.sqrt(np.mean(y**2))) < 1e-5:
        logger.info("Audio is silent in %s.", video_path)
        return {"tempo": 0.0, "beats": [], "duration": len(y) / sample_rate, "error": "silent"}

    return _detect_beats(y, sample_rate)


class _NoAudioStream(Exception):
    """Raised when FFmpeg reports no audio stream."""


def _extract_audio_pipe(video_path: str) -> bytes:
    """Pipe PCM audio from video via FFmpeg.

    Raises _NoAudioStream if the video has no audio track.
    """
    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-vn",                    # drop video
        "-acodec", "pcm_s16le",   # 16-bit signed PCM
        "-ar", "22050",           # 22.05 kHz mono (librosa default)
        "-ac", "1",
        "-f", "wav",              # WAV container
        "pipe:1",                 # stdout
        "-loglevel", "error",
        "-nostats",
    ]
    result = subprocess.run(cmd, capture_output=True, check=False)
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").lower()
        if "audio" in stderr or "stream" in stderr:
            raise _NoAudioStream()
        raise subprocess.CalledProcessError(result.returncode, cmd, output=result.stdout, stderr=result.stderr)
    return result.stdout


def _detect_beats(y: np.ndarray, sample_rate: int) -> dict:
    """Run librosa beat detection on a float32 PCM array."""
    # Lazy import so librosa doesn't block module loading
    import librosa

    duration = float(len(y)) / sample_rate

    # Clip too short for reliable beat detection (< 2 sec)
    if len(y) < sample_rate * 2:
        return {"tempo": 0.0, "beats": [], "duration": duration, "error": "clip_too_short"}

    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sample_rate)

    # librosa returns tempo as a scalar or 1-element array
    bpm = float(np.atleast_1d(tempo)[0])

    beat_times: list[float] = []
    if len(beat_frames) > 0:
        beat_times = librosa.frames_to_time(beat_frames, sr=sample_rate).tolist()

    return {
        "tempo": round(bpm, 1),
        "beats": [round(t, 3) for t in beat_times],
        "duration": round(duration, 3),
        "error": None,
    }
