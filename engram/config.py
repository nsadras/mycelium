from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomllib


@dataclass
class EngramConfig:
    store_path: Path = Path("./mycelium_store/engram")
    audio_dir: Path = Path("./mycelium_store/engram/audio")
    whisper_model: str = "large-v3"
    whisper_device: str = "auto"
    whisper_compute_type: str = "auto"
    whisper_batch_size: int = 8
    pyannote_model: str = "pyannote/speaker-diarization-community-1"
    hf_token: str | None = None
    ollama_model: str = "gemma4:12b"
    ollama_url: str = "http://localhost:11434"
    summary_temperature: float = 0.1
    summary_context_window_tokens: int = 32768

    @property
    def db_path(self) -> Path:
        return self.store_path / "engram.sqlite"

    def resolved_whisper_device(self) -> str:
        if self.whisper_device != "auto":
            return self.whisper_device
        try:
            import torch

            if torch.cuda.is_available():
                return "cuda"
        except Exception:
            pass
        return "cpu"

    def resolved_whisper_compute_type(self, device: str | None = None) -> str:
        if self.whisper_compute_type != "auto":
            return self.whisper_compute_type
        resolved_device = device or self.resolved_whisper_device()
        return "float16" if resolved_device == "cuda" else "int8"

    @classmethod
    def from_toml(cls, path: str | Path = "mycelium.toml") -> "EngramConfig":
        config_path = Path(path)
        data: dict = {}
        if config_path.exists():
            with open(config_path, "rb") as f:
                data = tomllib.load(f)

        engram_data = data.get("engram", {})
        whisper_data = engram_data.get("whisper", {})
        diarization_data = engram_data.get("diarization", {})
        summary_data = engram_data.get("summary", {})
        llm_data = data.get("llm", {})

        store_path = Path(engram_data.get("store_path", "./mycelium_store/engram"))
        return cls(
            store_path=store_path,
            audio_dir=Path(engram_data.get("audio_dir", store_path / "audio")),
            whisper_model=whisper_data.get("model", "large-v3"),
            whisper_device=whisper_data.get("device", "auto"),
            whisper_compute_type=whisper_data.get("compute_type", "auto"),
            whisper_batch_size=int(whisper_data.get("batch_size", 8)),
            pyannote_model=diarization_data.get("model", "pyannote/speaker-diarization-community-1"),
            hf_token=os.getenv("HF_TOKEN") or diarization_data.get("hf_token"),
            ollama_model=summary_data.get("model", llm_data.get("model", "gemma4:12b")),
            ollama_url=summary_data.get("url", llm_data.get("url", "http://localhost:11434")),
            summary_temperature=float(summary_data.get("temperature", 0.1)),
            summary_context_window_tokens=int(
                summary_data.get(
                    "context_window_tokens",
                    llm_data.get("context_window_tokens", 32768),
                )
            ),
        )

    def ensure_dirs(self) -> None:
        self.store_path.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
