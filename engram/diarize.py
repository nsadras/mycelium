from __future__ import annotations

from engram.config import EngramConfig
from engram.models import TranscriptSegment


class WhisperXDiarizer:
    def __init__(self, config: EngramConfig) -> None:
        self.config = config

    def diarize(self, audio_path: str, fallback_segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
        try:
            import whisperx
            from whisperx.diarize import DiarizationPipeline
        except ImportError as exc:
            raise RuntimeError("WhisperX is not installed. Install Engram diarization dependencies.") from exc

        device = self.config.resolved_whisper_device()
        audio = whisperx.load_audio(audio_path)
        # Reuse canonical ASR segments. Speaker assignment uses their audio-time
        # intervals; it does not need another transcription or text alignment.
        aligned = {"segments": [
            {"start": s.start_seconds, "end": s.end_seconds, "text": s.text}
            for s in fallback_segments
        ]}
        diarize_model = DiarizationPipeline(
            model_name=self.config.pyannote_model,
            token=self.config.hf_token,
            device=device,
        )
        diarize_segments = diarize_model(audio)
        assigned = whisperx.assign_word_speakers(diarize_segments, aligned)

        output: list[TranscriptSegment] = []
        for idx, segment in enumerate(assigned.get("segments", [])):
            text = str(segment.get("text", "")).strip()
            if not text:
                continue
            output.append(
                TranscriptSegment(
                    id=None,
                    meeting_id=fallback_segments[0].meeting_id if fallback_segments else "",
                    segment_index=idx,
                    start_seconds=float(segment.get("start", 0.0)),
                    end_seconds=float(segment.get("end", 0.0)),
                    text=text,
                    speaker=segment.get("speaker") or "Speaker ?",
                    status="diarized",
                )
            )
        return output or fallback_segments
