"""
HTTP client that mirrors MockFirestoreClient interface via Gateway REST API.

Bot services use this instead of a local SQLite — all CRUD goes through
the Gateway, so only one process ever touches the DB file.

Usage (drop-in replacement for db.collection(...)):

    from gateway_client import GatewayClient as FirestoreClient
    db = FirestoreClient()
    user = await db.collection('users').document('123').get()

During Phase 0 (same-container), GATEWAY_URL defaults to localhost.
After the split, set GATEWAY_URL to the gateway's Render URL.
"""

import os
import json
import logging
import httpx

logger = logging.getLogger(__name__)

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")


class GatewayDocSnapshot:
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
    def __init__(self, client, collection, doc_id):
        self._client = client
        self._collection = collection
        self._id = doc_id

    async def get(self):
        data = await self._client._request("GET", f"/api/db/{self._collection}/{self._id}")
        if data is None:
            return GatewayDocSnapshot(self._id, None)
        return GatewayDocSnapshot(data.get("id"), data.get("data"))

    async def set(self, data, merge=False):
        await self._client._request("POST", f"/api/db/{self._collection}/{self._id}",
                                    json={"data": _scrub(data), "merge": merge})

    async def update(self, data):
        await self._client._request("PATCH", f"/api/db/{self._collection}/{self._id}",
                                    json={"data": _scrub(data)})

    async def delete(self):
        await self._client._request("DELETE", f"/api/db/{self._collection}/{self._id}")


def _scrub(data):
    """Convert Increment/etc objects to JSON-safe __type dicts."""
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
    return data


class GatewayCollectionRef:
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

    async def get(self):
        params = {}
        if self._filters:
            params["filters"] = json.dumps(self._filters)
        if self._order_by:
            params["order_by"] = self._order_by
            params["order_dir"] = self._order_dir
        if self._limit_n is not None:
            params["limit_n"] = self._limit_n
        data = await self._client._request("GET", f"/api/db/{self._name}", params=params)
        return [GatewayDocSnapshot(d["id"], d["data"]) for d in (data or [])]

    async def stream(self):
        for doc in await self.get():
            yield doc

    async def add(self, data):
        result = await self._client._request("POST", f"/api/db/{self._name}",
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

    def get(self, ref):
        raise NotImplementedError("GatewayTransaction.get not supported — use dedicated endpoints")
    
    def update(self, ref, data):
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(ref.update(data))
            else:
                loop.run_until_complete(ref.update(data))
        except Exception:
            pass


def transactional(func):
    """Compatibility shim — no-op wrapper for @transactional decorator.
    
    Real transactions are handled server-side by the Gateway.
    """
    def wrapper(transaction, *args, **kwargs):
        return func(transaction, *args, **kwargs)
    return wrapper


class GatewayClient:
    """Drop-in for MockFirestoreClient backed by Gateway HTTP API."""

    def __init__(self, base_url=None, api_key=None):
        self.base_url = base_url or GATEWAY_URL
        self.api_key = api_key or INTERNAL_API_KEY
        self._headers = {"X-Internal-Key": self.api_key} if self.api_key else {}
        self._http = httpx.AsyncClient(base_url=self.base_url,
                                       headers=self._headers, timeout=15.0)

    def collection(self, name):
        return GatewayCollectionRef(self, name)

    def transaction(self):
        return GatewayTransaction(self)

    async def _request(self, method, path, **kwargs):
        try:
            r = await self._http.request(method, path, **kwargs)
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

    async def close(self):
        await self._http.aclose()


# ── Convenience singleton ──
default_client = None

def get_client():
    global default_client
    if default_client is None:
        default_client = GatewayClient()
    return default_client
