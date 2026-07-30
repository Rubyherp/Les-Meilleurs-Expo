"""Tests for app/services/audio.py — audio extraction and beat detection."""

from unittest.mock import patch

import numpy as np
import pytest

from app.services.audio import _NoAudioStream, extract_beats


class TestExtractBeats:
    def test_no_audio_stream_returns_error(self):
        """Videos without audio return gracefully."""
        with patch("app.services.audio._extract_audio_pipe",
                   side_effect=_NoAudioStream()):
            result = extract_beats("/fake/video.mp4")
        assert result["tempo"] == 0.0
        assert result["beats"] == []
        assert result["error"] == "no_audio_stream"

    def test_ffmpeg_failure_returns_error(self):
        """FFmpeg crashes are caught gracefully."""
        with patch("app.services.audio._extract_audio_pipe",
                   side_effect=RuntimeError("boom")):
            result = extract_beats("/fake/video.mp4")
        assert result["tempo"] == 0.0
        assert result["error"] == "ffmpeg_failed"

    def test_too_short_audio_returns_error(self):
        """Audio shorter than 44 bytes WAV header is rejected."""
        with patch("app.services.audio._extract_audio_pipe",
                   return_value=b"x" * 20):
            result = extract_beats("/fake/video.mp4")
        assert result["error"] == "audio_too_short"

    def test_silent_audio_returns_error(self):
        """Silent audio is detected and skipped."""
        sr = 22050
        silence = np.zeros(sr * 3, dtype=np.int16).tobytes()
        wav = _make_wav_header(sr, len(silence)) + silence
        with patch("app.services.audio._extract_audio_pipe", return_value=wav):
            result = extract_beats("/fake/video.mp4")
        assert result["error"] == "silent"
        assert result["duration"] > 0


def _make_wav_header(sample_rate: int, data_length: int) -> bytes:
    """Build a minimal 44-byte WAV header for PCM 16-bit mono audio."""
    import struct
    byte_rate = sample_rate * 2  # 1 channel × 2 bytes
    return (
        b"RIFF" +
        struct.pack("<I", 36 + data_length) +
        b"WAVEfmt " +
        struct.pack("<I", 16) +          # chunk size
        struct.pack("<H", 1) +           # PCM
        struct.pack("<H", 1) +           # mono
        struct.pack("<I", sample_rate) +
        struct.pack("<I", byte_rate) +
        struct.pack("<H", 2) +           # block align
        struct.pack("<H", 16) +          # bits per sample
        b"data" +
        struct.pack("<I", data_length)
    )
