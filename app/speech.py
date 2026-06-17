"""
Local speech I/O for the voice receptionist (Phase 5).

  * SpeechToText  - faster-whisper, runs on the GPU if available else CPU.
  * synthesize()  - Piper TTS via its bundled Windows binary, producing a WAV.

Both are fully local and free. No audio ever leaves the machine.
"""

from __future__ import annotations

import os
import subprocess
import sysconfig


def _register_cuda_dlls() -> None:
    """Make pip-installed NVIDIA CUDA libraries discoverable on Windows.

    The nvidia-cublas-cu12 / nvidia-cudnn-cu12 packages drop their DLLs under
    site-packages/nvidia/<lib>/bin, which is not on the DLL search path. We add
    each such directory so faster-whisper (ctranslate2) can run on the GPU. A
    no-op if the packages aren't installed -- STT then falls back to CPU.
    """
    nvidia_root = os.path.join(sysconfig.get_paths()["purelib"], "nvidia")
    if not os.path.isdir(nvidia_root):
        return
    for lib in os.listdir(nvidia_root):
        bin_dir = os.path.join(nvidia_root, lib, "bin")
        if os.path.isdir(bin_dir):
            os.add_dll_directory(bin_dir)
            os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")


# Must run before faster_whisper / ctranslate2 try to load CUDA libraries.
_register_cuda_dlls()

import numpy as np  # noqa: E402
from faster_whisper import WhisperModel  # noqa: E402

from . import config  # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PIPER_EXE = os.path.join(_ROOT, config.PIPER_EXE)
_PIPER_VOICE = os.path.join(_ROOT, config.PIPER_VOICE)


class SpeechToText:
    """Wraps a Whisper model, preferring GPU and falling back to CPU."""

    def __init__(self) -> None:
        self.model, self.device = self._load()
        self._warm_up()

    def _warm_up(self) -> None:
        """Prime the GPU and load the VAD model so the first real call is fast."""
        try:
            silence = np.zeros(16000, dtype=np.float32)
            list(
                self.model.transcribe(
                    silence,
                    language=config.WHISPER_LANGUAGE,
                    beam_size=1,
                    vad_filter=True,
                )[0]
            )
        except Exception:  # noqa: BLE001 - warmup is best-effort
            pass

    def _load(self) -> tuple[WhisperModel, str]:
        # GPU needs separate CUDA libraries (cuBLAS/cuDNN) that may be absent on
        # Windows, and a model can LOAD on cuda yet fail at inference. So we
        # validate each device with a tiny real transcription before accepting it.
        # Order follows config.WHISPER_DEVICE; "auto" tries GPU then CPU.
        all_attempts = {"cuda": ("cuda", "float16"), "cpu": ("cpu", "int8")}
        if config.WHISPER_DEVICE == "auto":
            attempts = [all_attempts["cuda"], all_attempts["cpu"]]
        else:
            attempts = [all_attempts[config.WHISPER_DEVICE]]
        silence = np.zeros(16000, dtype=np.float32)
        last_error: Exception | None = None
        for device, compute_type in attempts:
            try:
                model = WhisperModel(
                    config.WHISPER_MODEL, device=device, compute_type=compute_type
                )
                list(model.transcribe(silence, language="en")[0])  # force a real run
                print(f"Whisper '{config.WHISPER_MODEL}' running on {device}.")
                return model, device
            except Exception as exc:  # noqa: BLE001 - try the next device
                last_error = exc
                print(f"  Whisper on {device} not usable: {str(exc)[:70]}")
        raise RuntimeError(f"Could not load Whisper: {last_error}")

    def transcribe(self, audio_path: str) -> str:
        """Return the recognized text for an audio file (any common format)."""
        # beam_size=1 (greedy) is faster and plenty accurate for clear speech;
        # vad_filter trims silence so we don't decode dead air.
        segments, _ = self.model.transcribe(
            audio_path,
            language=config.WHISPER_LANGUAGE,
            beam_size=1,
            vad_filter=True,
        )
        return " ".join(segment.text for segment in segments).strip()


def synthesize(text: str, out_path: str) -> str:
    """Synthesize `text` to a WAV file at `out_path` using Piper. Returns the path."""
    subprocess.run(
        [_PIPER_EXE, "-m", _PIPER_VOICE, "-f", out_path],
        input=text.encode("utf-8"),
        capture_output=True,
        check=True,
    )
    return out_path
