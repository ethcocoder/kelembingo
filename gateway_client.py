"""
Synchronous HTTP client that mirrors MockFirestoreClient interface via Gateway REST API.

Bot services use this instead of a local SQLite — all CRUD goes through
the Gateway, so only one process ever touches the DB file.

Usage (drop-in for db.collection(...)):

    from gateway_client import GatewayClient
    db = GatewayClient()
    user_doc = db.collection('users').document('123').get()  # sync, same as MockFirestoreClient
    if user_doc.exists:
        data = user_doc.to_dict()

During Phase 0 (same-container), GATEWAY_URL defaults to localhost.
After the split, set GATEWAY_URL to the gateway's Render URL.
"""

import os
import json
import logging
from datetime import datetime, date
import httpx
from firestore_db import Increment, ArrayUnion, ArrayRemove, FieldFilter

logger = logging.getLogger(__name__)

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")


def _scrub(data):
    """Convert non-JSON-safe objects (Increment, datetime, etc) to JSON-safe types."""
    if isinstance(data, dict):
        if hasattr(data, '_is_increment'):
            return {"__type": "increment", "value": data.value}
        if hasattr(data, '_is_array_union'):
            return {"__type": "array_union", "value": data.value}
        if hasattr(data, '_is_array_remove'):
            return {"__type": "array_remove", "value": data.value}
        return {k: _scrub(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_scrub(v) for v in data]
    if isinstance(data, datetime):
        return data.isoformat()
    if isinstance(data, date):
        return data.isoformat()
    return data


class GatewayDocSnapshot:
    """Mimics firestore_db.DocumentSnapshot."""
    __slots__ = ("_id", "_data", "exists")

    def __init__(self, doc_id, data_dict):
        self._id = doc_id
        self._data = data_dict
        self.exists = data_dict is not None

    @property
    def id(self):
        return self._id

    def to_dict(self):
        return self._data


class GatewayDocRef:
    """Mimics firestore_db.DocumentRef via synchronous HTTP calls."""

    def __init__(self, client, collection, doc_id):
        self._client = client
        self._collection = collection
        self._id = doc_id

    def get(self):
        data = self._client._request("GET", f"/api/db/{self._collection}/{self._id}")
        if data is None:
            return GatewayDocSnapshot(self._id, None)
        return GatewayDocSnapshot(data.get("id"), data.get("data"))

    def set(self, data, merge=False):
        self._client._request("POST", f"/api/db/{self._collection}/{self._id}",
                              json={"data": _scrub(data), "merge": merge})

    def update(self, data):
        self._client._request("PATCH", f"/api/db/{self._collection}/{self._id}",
                              json={"data": _scrub(data)})

    def delete(self):
        self._client._request("DELETE", f"/api/db/{self._collection}/{self._id}")


class GatewayCollectionRef:
    """Mimics firestore_db.CollectionRef via synchronous HTTP calls."""

    def __init__(self, client, name):
        self._client = client
        self._name = name
        self._filters = []
        self._order_by = None
        self._order_dir = "ASCENDING"
        self._limit_n = None

    def document(self, doc_id=None):
        return GatewayDocRef(self._client, self._name, doc_id or "")

    def where(self, field, op, value):
        self._filters.append([field, op, value])
        return self

    def order_by(self, field, direction="ASCENDING"):
        self._order_by = field
        self._order_dir = direction
        return self

    def limit(self, n):
        self._limit_n = n
        return self

    def get(self):
        params = {}
        if self._filters:
            params["filters"] = json.dumps(self._filters)
        if self._order_by:
            params["order_by"] = self._order_by
            params["order_dir"] = self._order_dir
        if self._limit_n is not None:
            params["limit_n"] = self._limit_n
        data = self._client._request("GET", f"/api/db/{self._name}", params=params)
        return [GatewayDocSnapshot(d["id"], d["data"]) for d in (data or [])]

    def stream(self):
        return iter(self.get())

    def add(self, data):
        result = self._client._request("POST", f"/api/db/{self._name}",
                                       json={"data": _scrub(data)})
        doc_id = result.get("id", "")
        return GatewayDocRef(self._client, self._name, doc_id)


class GatewayTransaction:
    """Minimal transaction — individual ops go over HTTP (no multi-op atomicity).

    Each read/write inside a @transactional block fires a separate HTTP request.
    There is no server-side rollback. For true atomic operations the Gateway
    should expose a dedicated endpoint (e.g. POST /api/transfer-funds).
    """

    def __init__(self, client):
        self._client = client
        self._ops = []

    def get(self, ref):
        raise NotImplementedError(
            "GatewayTransaction.get not supported over HTTP. "
            "Use dedicated atomic endpoints on the Gateway."
        )

    def update(self, ref, data):
        self._ops.append((ref, data))

    def commit(self):
        for ref, data in self._ops:
            ref.update(data)


def transactional(func):
    """Compatibility shim for the @transactional decorator.

    Real atomicity is handled server-side by the Gateway.
    """
    def wrapper(transaction, *args, **kwargs):
        return func(transaction, *args, **kwargs)
    return wrapper


class MockIncrement(Increment):
    """Identity-preserving Increment subclass for cross-module compatibility."""
    pass


class GatewayClient:
    """Synchronous drop-in replacement for MockFirestoreClient backed by Gateway HTTP API.

    Usage:
        db = GatewayClient()
        user_doc = db.collection('users').document('123').get()
    """

    def __init__(self, base_url=None, api_key=None):
        self.base_url = base_url or GATEWAY_URL
        self.api_key = api_key or INTERNAL_API_KEY
        self._http = httpx.Client(
            base_url=self.base_url,
            headers={"X-Internal-Key": self.api_key} if self.api_key else {},
            timeout=15.0,
        )

    def collection(self, name):
        return GatewayCollectionRef(self, name)

    def transaction(self):
        return GatewayTransaction(self)

    def _request(self, method, path, **kwargs):
        try:
            r = self._http.request(method, path, **kwargs)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            logger.error(f"Gateway {method} {path}: {e}")
            raise
        except Exception as e:
            logger.error(f"Gateway {method} {path}: {e}")
            raise

    def close(self):
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# ── Convenience singleton ──
_default_client = None


def get_client():
    global _default_client
    if _default_client is None:
        _default_client = GatewayClient()
    return _default_client


__all__ = [
    "GatewayClient", "GatewayCollectionRef", "GatewayDocRef",
    "GatewayDocSnapshot", "GatewayTransaction", "transactional",
    "get_client", "Increment", "ArrayUnion", "ArrayRemove", "FieldFilter",
    "MockIncrement",
]
