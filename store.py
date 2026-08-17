"""Session storage: a single, simple disk-backed store.

One format, one path. Sessions are plain dicts owned by game.py's logic;
this module only persists them with a sliding TTL.
"""
import copy
import logging
import os

import diskcache

logger = logging.getLogger(__name__)


class SessionStore:
    def __init__(self, directory: str = None, ttl: int = 21600):
        self.directory = directory or os.environ.get('SESSION_STORAGE_DIR', 'session_storage')
        self.ttl = ttl
        os.makedirs(self.directory, exist_ok=True)
        self._cache = diskcache.Cache(
            self.directory,
            size_limit=1_000_000_000,
            eviction_policy='least-recently-used',
            disk_min_file_size=1024,
            statistics=0,
        )

    def get(self, session_id: str):
        """Return a deep copy of the session (callers may mutate freely),
        or None. Reading renews the TTL so active games never expire."""
        state = self._cache.get(session_id)
        if state is None:
            return None
        try:
            self._cache.touch(session_id, expire=self.ttl)
        except Exception as e:  # TTL renewal is best-effort
            logger.debug("TTL renew failed for %s: %s", session_id, e)
        return copy.deepcopy(state)

    def put(self, session_id: str, state: dict) -> None:
        self._cache.set(session_id, state, expire=self.ttl)

    def delete(self, session_id: str) -> None:
        try:
            self._cache.delete(session_id)
        except KeyError:
            pass

    def close(self) -> None:
        self._cache.close()
