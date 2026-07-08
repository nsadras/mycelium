from __future__ import annotations

import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

from engram.config import EngramConfig


@dataclass
class TranscribedSegment:
    start_seconds: float
    end_seconds: float
    text: str


class FasterWhisperTranscriber:
    def __init__(self, config: EngramConfig) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError("faster-whisper is not installed. Install Engram speech dependencies.") from exc

        device = config.resolved_whisper_device()
        compute_type = config.resolved_whisper_compute_type(device)
        kwargs = {"compute_type": compute_type}
        kwargs["device"] = device
        self.model = WhisperModel(config.whisper_model, **kwargs)
        self.sample_rate = 16000

    def transcribe_pcm(self, pcm16: bytes, *, offset_seconds: float) -> list[TranscribedSegment]:
        if not pcm16:
            return []
        wav_path = self._write_temp_wav(pcm16)
        try:
            return self.transcribe_audio(str(wav_path), offset_seconds=offset_seconds)
        finally:
            wav_path.unlink(missing_ok=True)

    def transcribe_audio(self, audio_path: str, *, offset_seconds: float = 0.0) -> list[TranscribedSegment]:
        segments, _info = self.model.transcribe(
            audio_path,
            vad_filter=True,
            word_timestamps=True,
            beam_size=1,
        )
        output = []
        for segment in segments:
            text = segment.text.strip()
            if text:
                output.append(
                    TranscribedSegment(
                        start_seconds=offset_seconds + float(segment.start),
                        end_seconds=offset_seconds + float(segment.end),
                        text=text,
                    )
                )
        return output

    def _write_temp_wav(self, pcm16: bytes) -> Path:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        path = Path(tmp.name)
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(self.sample_rate)
            wav.writeframes(pcm16)
        return path
