from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict
from pathlib import Path
import wave

import pytest

from engram.config import EngramConfig
from engram.diarize import WhisperXDiarizer
from engram.models import TranscriptSegment
from engram.transcribe import FasterWhisperTranscriber

AMI_ROOT = Path("AMI")
AMI_MEETINGS = ("ES2002a", "ES2002b", "ES2002c", "ES2002d")


def _available_ami_meetings() -> list[str]:
    return [
        meeting_id
        for meeting_id in AMI_MEETINGS
        if _audio_path(meeting_id).exists()
    ]


def _selected_ami_meetings() -> list[str]:
    requested = os.getenv("ENGRAM_AMI_MEETINGS")
    if requested:
        return [item.strip() for item in requested.split(",") if item.strip()]
    return list(AMI_MEETINGS)


def _audio_path(meeting_id: str) -> Path:
    return AMI_ROOT / "amicorpus" / meeting_id / "audio" / f"{meeting_id}.Mix-Headset.wav"


def _word_paths(meeting_id: str) -> list[Path]:
    return sorted((AMI_ROOT / "annotations" / "words").glob(f"{meeting_id}.*.words.xml"))


def _reference_words(meeting_id: str) -> list[dict]:
    words = []
    for path in _word_paths(meeting_id):
        speaker = path.name.split(".")[1]
        root = ET.parse(path).getroot()
        for elem in root:
            if elem.tag != "w" or elem.attrib.get("punc") == "true" or not elem.text:
                continue
            words.append(
                {
                    "speaker": speaker,
                    "start_seconds": float(elem.attrib["starttime"]),
                    "end_seconds": float(elem.attrib["endtime"]),
                    "text": elem.text,
                }
            )
    return sorted(words, key=lambda item: (item["start_seconds"], item["end_seconds"], item["speaker"]))


def _reference_words_until(meeting_id: str, end_seconds: float) -> list[dict]:
    return [word for word in _reference_words(meeting_id) if word["start_seconds"] < end_seconds]


def _reference_text(meeting_id: str) -> str:
    return " ".join(word["text"] for word in _reference_words(meeting_id))


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _clip_audio(meeting_id: str, seconds: int, output_dir: Path) -> Path:
    source = _audio_path(meeting_id)
    clip_path = output_dir / f"{meeting_id}.first{seconds // 60}min.wav"
    if clip_path.exists():
        return clip_path

    with wave.open(str(source), "rb") as src:
        params = src.getparams()
        frames = min(src.getnframes(), int(src.getframerate() * seconds))
        audio = src.readframes(frames)
    with wave.open(str(clip_path), "wb") as dst:
        dst.setparams(params)
        dst.writeframes(audio)
    return clip_path


def _interval_overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def _speaker_overlap_metrics(predicted: list[TranscriptSegment], reference_words: list[dict]) -> dict:
    overlap_by_pair: dict[tuple[str, str], float] = {}
    reference_duration_by_speaker: dict[str, float] = {}
    predicted_speakers = sorted({segment.speaker for segment in predicted if segment.speaker})
    reference_speakers = sorted({word["speaker"] for word in reference_words})

    for word in reference_words:
        ref_duration = max(0.0, word["end_seconds"] - word["start_seconds"])
        reference_duration_by_speaker[word["speaker"]] = reference_duration_by_speaker.get(word["speaker"], 0.0) + ref_duration
        for segment in predicted:
            if not segment.speaker:
                continue
            overlap = _interval_overlap(
                word["start_seconds"],
                word["end_seconds"],
                segment.start_seconds,
                segment.end_seconds,
            )
            if overlap > 0:
                key = (segment.speaker, word["speaker"])
                overlap_by_pair[key] = overlap_by_pair.get(key, 0.0) + overlap

    mapping: dict[str, str] = {}
    remaining_refs = set(reference_speakers)
    for pred_speaker in predicted_speakers:
        best_ref = None
        best_overlap = 0.0
        for ref_speaker in remaining_refs:
            overlap = overlap_by_pair.get((pred_speaker, ref_speaker), 0.0)
            if overlap > best_overlap:
                best_ref = ref_speaker
                best_overlap = overlap
        if best_ref is not None:
            mapping[pred_speaker] = best_ref
            remaining_refs.remove(best_ref)

    matched_overlap = sum(overlap_by_pair.get((pred, ref), 0.0) for pred, ref in mapping.items())
    total_reference_duration = sum(reference_duration_by_speaker.values())
    total_predicted_reference_overlap = sum(overlap_by_pair.values())

    return {
        "predicted_speakers": predicted_speakers,
        "reference_speakers": reference_speakers,
        "speaker_mapping": mapping,
        "matched_overlap_seconds": matched_overlap,
        "total_reference_speech_seconds": total_reference_duration,
        "total_predicted_reference_overlap_seconds": total_predicted_reference_overlap,
        "mapped_reference_coverage": matched_overlap / total_reference_duration if total_reference_duration else 0.0,
        "overlap_by_pair_seconds": {
            f"{pred}->{ref}": seconds
            for (pred, ref), seconds in sorted(overlap_by_pair.items())
        },
        "reference_duration_by_speaker_seconds": reference_duration_by_speaker,
    }


@pytest.mark.skipif(not AMI_ROOT.exists(), reason="AMI dataset is not available locally")
def test_ami_subset_has_expected_audio_and_word_annotations():
    assert _available_ami_meetings() == list(AMI_MEETINGS)

    for meeting_id in AMI_MEETINGS:
        audio = _audio_path(meeting_id)
        word_paths = _word_paths(meeting_id)
        words = _reference_words(meeting_id)

        assert audio.exists(), f"Missing audio for {meeting_id}: {audio}"
        assert len(word_paths) == 4, f"Expected A-D word annotations for {meeting_id}"
        assert len(words) > 100, f"Expected usable word annotations for {meeting_id}"


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("ENGRAM_RUN_AMI_TRANSCRIPTION") != "1",
    reason="Set ENGRAM_RUN_AMI_TRANSCRIPTION=1 to run slow AMI Whisper transcription",
)
def test_transcribe_ami_meetings_with_whisper_for_manual_comparison():
    missing = [meeting_id for meeting_id in _selected_ami_meetings() if not _audio_path(meeting_id).exists()]
    assert not missing, f"Missing AMI audio for: {', '.join(missing)}"

    config = EngramConfig.from_toml("mycelium.toml")
    config.whisper_model = os.getenv("ENGRAM_AMI_WHISPER_MODEL", config.whisper_model)
    config.whisper_device = os.getenv("ENGRAM_AMI_WHISPER_DEVICE", config.whisper_device)
    config.whisper_compute_type = os.getenv("ENGRAM_AMI_WHISPER_COMPUTE_TYPE", config.whisper_compute_type)
    transcriber = FasterWhisperTranscriber(config)

    output_dir = Path(os.getenv("ENGRAM_AMI_OUTPUT_DIR", "test_outputs/ami_transcripts"))
    output_dir.mkdir(parents=True, exist_ok=True)

    for meeting_id in _selected_ami_meetings():
        audio_path = _audio_path(meeting_id)
        segments = transcriber.transcribe_audio(str(audio_path))
        assert segments, f"Whisper produced no segments for {meeting_id}"

        transcript_text = "\n".join(segment.text for segment in segments)
        reference_text = _reference_text(meeting_id)
        assert _normalized(transcript_text), f"Whisper transcript is empty for {meeting_id}"
        assert _normalized(reference_text), f"AMI reference transcript is empty for {meeting_id}"

        (output_dir / f"{meeting_id}.whisper.txt").write_text(transcript_text + "\n", encoding="utf-8")
        (output_dir / f"{meeting_id}.reference.txt").write_text(reference_text + "\n", encoding="utf-8")
        (output_dir / f"{meeting_id}.segments.json").write_text(
            json.dumps([asdict(segment) for segment in segments], indent=2),
            encoding="utf-8",
        )


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("ENGRAM_RUN_AMI_DIARIZATION") != "1",
    reason="Set ENGRAM_RUN_AMI_DIARIZATION=1 to run slow AMI WhisperX/pyannote diarization",
)
def test_diarize_ami_first_five_minutes_with_whisperx_for_manual_comparison():
    meeting_id = os.getenv("ENGRAM_AMI_DIARIZATION_MEETING", "ES2002a")
    assert _audio_path(meeting_id).exists(), f"Missing AMI audio for {meeting_id}"

    output_dir = Path(os.getenv("ENGRAM_AMI_OUTPUT_DIR", "test_outputs/ami_transcripts"))
    output_dir.mkdir(parents=True, exist_ok=True)
    clip_path = _clip_audio(meeting_id, 300, output_dir)

    config = EngramConfig.from_toml("mycelium.toml")
    config.whisper_model = os.getenv("ENGRAM_AMI_WHISPER_MODEL", "base.en")
    config.whisper_device = os.getenv("ENGRAM_AMI_WHISPER_DEVICE", "cpu")
    config.whisper_compute_type = os.getenv("ENGRAM_AMI_WHISPER_COMPUTE_TYPE", "int8")
    config.whisper_batch_size = int(os.getenv("ENGRAM_AMI_WHISPER_BATCH_SIZE", "8"))
    config.pyannote_model = os.getenv("ENGRAM_AMI_PYANNOTE_MODEL", config.pyannote_model)
    config.hf_token = os.getenv("HF_TOKEN") or config.hf_token
    if not config.hf_token:
        pytest.skip(
            "pyannote/speaker-diarization-community-1 is gated; set HF_TOKEN after accepting the model terms "
            "to run AMI diarization comparison"
        )

    diarizer = WhisperXDiarizer(config)
    fallback = [
        TranscriptSegment(
            id=None,
            meeting_id=meeting_id,
            segment_index=0,
            start_seconds=0.0,
            end_seconds=300.0,
            text="",
        )
    ]
    diarized = diarizer.diarize(str(clip_path), fallback)
    reference_words = _reference_words_until(meeting_id, 300.0)
    metrics = _speaker_overlap_metrics(diarized, reference_words)

    assert diarized, f"WhisperX/pyannote produced no diarized segments for {meeting_id}"
    assert len(metrics["predicted_speakers"]) >= 2, "Expected at least two predicted speakers in the AMI clip"
    assert metrics["total_reference_speech_seconds"] > 30.0
    assert metrics["total_predicted_reference_overlap_seconds"] > 10.0

    (output_dir / f"{meeting_id}.first5min.diarized.txt").write_text(
        "\n".join(
            f"[{segment.start_seconds:7.2f}-{segment.end_seconds:7.2f}] {segment.speaker}: {segment.text}"
            for segment in diarized
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / f"{meeting_id}.first5min.diarized_segments.json").write_text(
        json.dumps([asdict(segment) for segment in diarized], indent=2, default=str),
        encoding="utf-8",
    )
    (output_dir / f"{meeting_id}.first5min.reference_words.json").write_text(
        json.dumps(reference_words, indent=2),
        encoding="utf-8",
    )
    (output_dir / f"{meeting_id}.first5min.diarization_metrics.json").write_text(
        json.dumps(metrics, indent=2),
        encoding="utf-8",
    )
