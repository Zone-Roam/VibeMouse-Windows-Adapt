from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, cast


_ACTIVE_JOB_STAGES = {"queued", "transcribing", "translating", "delivering"}


@dataclass(frozen=True)
class OverlayState:
    """Normalized overlay state compatible with status schema v1 and v2."""

    schema_version: int = 1
    revision: int = 0
    service_state: str = "ready"
    capture_state: str = "idle"
    audio_level: float = 0.0
    job_id: str | None = None
    job_stage: str | None = None
    output_target: str | None = None
    partial_text: str = ""
    last_outcome: str | None = None
    error_code: str | None = None

    @property
    def recording(self) -> bool:
        return self.capture_state == "recording"

    @property
    def has_active_job(self) -> bool:
        return self.job_stage in _ACTIVE_JOB_STAGES

    @property
    def visible(self) -> bool:
        return self.recording or self.has_active_job

    @classmethod
    def from_payload(cls, payload_obj: object) -> "OverlayState":
        if not isinstance(payload_obj, dict):
            return cls()
        payload = cast(Mapping[str, object], payload_obj)

        schema_version = _read_int(payload.get("schema_version"), 1)
        revision = _read_int(payload.get("revision"), 0)
        audio_level = _clamp_level(payload.get("audio_level"))

        # Schema v1 uses top-level recording/state fields.
        recording = bool(payload.get("recording", False))
        capture_state = "recording" if recording else _read_text(payload.get("state"), "idle")
        service_state = "ready"
        job_id: str | None = None
        job_stage: str | None = None
        output_target: str | None = None
        partial_text = _read_text(payload.get("partial_text"), "")
        last_outcome: str | None = None
        error_code: str | None = None

        service_obj = payload.get("service")
        if isinstance(service_obj, dict):
            service = cast(Mapping[str, object], service_obj)
            service_state = _read_text(service.get("state"), service_state)

        capture_obj = payload.get("capture")
        if isinstance(capture_obj, dict):
            capture = cast(Mapping[str, object], capture_obj)
            capture_state = _read_text(capture.get("state"), capture_state)
            audio_level = _clamp_level(capture.get("audio_level", audio_level))

        job_obj = payload.get("job")
        if isinstance(job_obj, dict):
            job = cast(Mapping[str, object], job_obj)
            job_id = _read_optional_text(job.get("id"))
            job_stage = _read_optional_text(job.get("stage"))
            output_target = _read_optional_text(job.get("target"))
            partial_text = _read_text(job.get("partial_text"), partial_text)

        result_obj = payload.get("last_result")
        if isinstance(result_obj, dict):
            result = cast(Mapping[str, object], result_obj)
            last_outcome = _read_optional_text(result.get("outcome"))
            error_code = _read_optional_text(result.get("error_code"))

        return cls(
            schema_version=max(1, schema_version),
            revision=max(0, revision),
            service_state=service_state,
            capture_state=capture_state,
            audio_level=audio_level,
            job_id=job_id,
            job_stage=job_stage,
            output_target=output_target,
            partial_text=partial_text,
            last_outcome=last_outcome,
            error_code=error_code,
        )


def _read_text(value: object, default: str) -> str:
    if not isinstance(value, str):
        return default
    normalized = value.strip()
    return normalized or default


def _read_optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _read_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    return default


def _clamp_level(value: object) -> float:
    try:
        level = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, level))
