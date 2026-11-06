"""Task lifecycle client; numerical and access decisions stay on the server."""

from eurogas_nexus_sdk import _http
from eurogas_nexus_sdk._transport import api_url

OPERATIONS = {
    "list": ("get", "functional-runs"),
    "submit": ("post", "functional-runs"),
    "status": ("get", "functional-runs/{id}"),
    "replay": ("post", "functional-runs/{id}/replay"),
    "compare": ("post", "functional-runs/{id}/compare"),
    "reconcile": ("post", "functional-runs/reconcile"),
    "freeze-model": ("post", "functional-models"),
    "model": ("get", "functional-models/{id}"),
    "review-model": ("patch", "functional-models/{id}"),
    "predict": ("post", "functional-models/{id}/predict"),
    "evaluate": ("post", "functional-models/{id}/evaluate"),
    "cancel": ("post", "jobs/{id}/cancel"),
}


def operate(base_url, operation, *, identifier=None, body=None):
    from urllib.parse import quote

    if operation not in OPERATIONS:
        raise ValueError("unknown functional operation")
    method, path = OPERATIONS[operation]
    if "{id}" in path:
        if not identifier:
            raise ValueError("this operation requires an identifier")
        path = path.replace("{id}", quote(identifier, safe=""))
    kwargs = {"timeout": 30}
    if method != "get":
        kwargs["json"] = body or {}
    response = getattr(_http, method)(api_url(base_url, path), **kwargs)
    response.raise_for_status()
    return response.json()


def submit_run(base_url, kind, inputs, idempotency_key, *, version_refs=None, deadline_seconds=60):
    response = _http.post(
        api_url(base_url, "functional-runs"),
        json={
            "kind": kind,
            "inputs": inputs,
            "idempotency_key": idempotency_key,
            "version_refs": version_refs or {},
            "deadline_seconds": deadline_seconds,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def get_run(base_url, run_id):
    from urllib.parse import quote

    response = _http.get(api_url(base_url, f"functional-runs/{quote(run_id, safe='')}"), timeout=15)
    response.raise_for_status()
    return response.json()


def replay_run(base_url, run_id, idempotency_key):
    from urllib.parse import quote

    response = _http.post(
        api_url(base_url, f"functional-runs/{quote(run_id, safe='')}/replay"),
        json={"idempotency_key": idempotency_key},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()
