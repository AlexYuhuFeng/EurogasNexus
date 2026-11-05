"""DB-independent submission contract for functional tasks."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SubmitRun(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    kind: str
    inputs: dict
    idempotency_key: str = Field(min_length=1, max_length=80)
    version_refs: dict[str, str] = Field(default_factory=dict, max_length=32)
    deadline_seconds: int = Field(default=60, ge=1, le=120)

    @field_validator("version_refs")
    @classmethod
    def bounded_versions(cls, value):
        if any(not 1 <= len(k) <= 160 or not 1 <= len(v) <= 128 for k, v in value.items()):
            raise ValueError("version references require bounded non-empty identifiers")
        return value
