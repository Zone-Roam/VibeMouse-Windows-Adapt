from __future__ import annotations

import importlib
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast
from uuid import uuid4

import numpy as np
from numpy.typing import NDArray


AudioFrame = NDArray[np.float32]


@dataclass
class AudioRecording:
    path: Path
    duration_s: float


class _AudioStream(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...

    def close(self) -> None: ...


class _SoundDeviceModule(Protocol):
    def InputStream(
        self,
        *,
        samplerate: int,
        channels: int,
        dtype: str,
        callback: Callable[[AudioFrame, int, object, object], None],
    ) -> _AudioStream: ...


class _SoundFileModule(Protocol):
    def write(self, file: str | Path, data: AudioFrame, samplerate: int) -> None: ...


class AudioRecorder:
    def __init__(
        self, sample_rate: int, channels: int, dtype: str, temp_dir: Path
    ) -> None:
        self._sample_rate: int = sample_rate
        self._channels: int = channels
        self._dtype: str = dtype
        self._temp_dir: Path = temp_dir
        self._sd: _SoundDeviceModule | None = None
        self._sf: _SoundFileModule | None = None
        self._lock: threading.Lock = threading.Lock()
        self._frames: list[AudioFrame] = []
        self._stream: _AudioStream | None = None
        self._recording: bool = False
        self._input_level: float = 0.0

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._recording

    @property
    def input_level(self) -> float:
        with self._lock:
            return self._input_level

    def start(self) -> None:
        self._ensure_audio_modules()
        with self._lock:
            if self._recording:
                return
            try:
                self._temp_dir.mkdir(parents=True, exist_ok=True)
            except OSError as error:
                raise RuntimeError(
                    f"Failed to create temp audio directory {self._temp_dir}: {error}"
                ) from error
            self._frames = []
            self._input_level = 0.0
            if self._sd is None:
                raise RuntimeError("Audio input module not initialized")
            stream = self._sd.InputStream(
                samplerate=self._sample_rate,
                channels=self._channels,
                dtype=self._dtype,
                callback=self._callback,
            )
            stream.start()
            self._stream = stream
            self._recording = True

    def stop_and_save(self) -> AudioRecording | None:
        with self._lock:
            if not self._recording:
                return None
            stream = self._stream
            self._stream = None
            self._recording = False
            self._input_level = 0.0

        if stream is not None:
            stream.stop()
            stream.close()

        with self._lock:
            if not self._frames:
                return None
            audio = np.concatenate(self._frames, axis=0)
            self._frames = []

        out_path = self._temp_dir / f"recording_{uuid4().hex}.wav"
        if self._sf is None:
            raise RuntimeError("Audio write module not initialized")
        try:
            self._sf.write(out_path, audio, self._sample_rate)
        except Exception as error:
            raise RuntimeError(
                f"Failed to write recording to {out_path}: {error}"
            ) from error
        duration = float(len(audio) / self._sample_rate)
        return AudioRecording(path=out_path, duration_s=duration)

    def cancel(self) -> None:
        with self._lock:
            if not self._recording:
                self._frames = []
                self._input_level = 0.0
                return
            stream = self._stream
            self._stream = None
            self._recording = False
            self._frames = []
            self._input_level = 0.0

        if stream is not None:
            stream.stop()
            stream.close()

    def _callback(
        self, indata: AudioFrame, frames: int, time_data: object, status: object
    ) -> None:
        del frames
        del time_data
        del status
        audio = indata.astype(np.float32, copy=False)
        if audio.size <= 0:
            level = 0.0
        else:
            level = float(np.sqrt(np.mean(np.square(audio))))
        level = min(1.0, max(0.0, level))
        with self._lock:
            if self._recording:
                self._frames.append(indata.copy())
                self._input_level = max(level, self._input_level * 0.82)

    def _ensure_audio_modules(self) -> None:
        if self._sd is not None and self._sf is not None:
            return
        try:
            sounddevice_module = importlib.import_module("sounddevice")
            soundfile_module = importlib.import_module("soundfile")
        except Exception as error:
            raise RuntimeError(
                "Audio dependencies missing. Install sounddevice and soundfile."
            ) from error

        self._sd = cast(_SoundDeviceModule, cast(object, sounddevice_module))
        self._sf = cast(_SoundFileModule, cast(object, soundfile_module))
