"""Runtime-store contract unit tests."""

from eurogas_nexus.runtime_store import HeartbeatRecord, RuntimeStore


class _RuntimeStoreDouble(RuntimeStore):
    def __init__(self, record: HeartbeatRecord | None) -> None:
        self._record = record

    def get_heartbeat(self, service_name: str, instance_id: str) -> HeartbeatRecord | None:
        if self._record is None:
            return None
        if self._record.service_name == service_name and self._record.instance_id == instance_id:
            return self._record
        return None


def test_runtime_store_contract_uses_ephemeral_record() -> None:
    record = HeartbeatRecord(
        service_name="api",
        instance_id="i-1",
        observed_at_utc="2026-05-27T00:00:00Z",
    )
    store = _RuntimeStoreDouble(record)

    result = store.get_heartbeat("api", "i-1")

    assert result is not None
    assert result.service_name == "api"
