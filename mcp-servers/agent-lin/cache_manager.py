import asyncio
import sqlite3
import time
import os

MAX_SIZE_MB = 100


class CacheManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                namespace TEXT NOT NULL,
                key      TEXT NOT NULL,
                value    TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                PRIMARY KEY (namespace, key)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_expires ON cache(expires_at)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_created ON cache(created_at)
        """)
        conn.commit()
        conn.close()

    def _run_sync(self, func):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            result = func(conn)
            conn.commit()
            return result
        finally:
            conn.close()

    async def _run(self, func):
        return await asyncio.to_thread(self._run_sync, func)

    async def get(self, namespace: str, key: str) -> str | None:
        now = time.time()

        def _get(conn):
            row = conn.execute(
                "SELECT value FROM cache WHERE namespace=? AND key=? AND expires_at > ?",
                (namespace, key, now),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE cache SET created_at=? WHERE namespace=? AND key=?",
                    (now, namespace, key),
                )
            return row[0] if row else None

        return await self._run(_get)

    async def set(self, namespace: str, key: str, value: str, ttl: int):
        now = time.time()

        def _set(conn):
            self._evict_if_needed_sync(conn, len(value.encode("utf-8")))
            conn.execute(
                "REPLACE INTO cache VALUES (?, ?, ?, ?, ?)",
                (namespace, key, value, now, now + ttl),
            )

        await self._run(_set)

    async def clear(self, namespace: str | None = None):
        def _clear(conn):
            if namespace:
                conn.execute("DELETE FROM cache WHERE namespace=?", (namespace,))
            else:
                conn.execute("DELETE FROM cache")

        await self._run(_clear)

    async def stats(self) -> dict:
        def _stats(conn):
            total = conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
            size_row = conn.execute(
                "SELECT COALESCE(SUM(LENGTH(value)), 0) FROM cache"
            ).fetchone()
            size_bytes = size_row[0]
            ns_stats = conn.execute(
                "SELECT namespace, COUNT(*), COALESCE(SUM(LENGTH(value)), 0) FROM cache GROUP BY namespace"
            ).fetchall()

            now = time.time()
            expired = conn.execute(
                "SELECT COUNT(*) FROM cache WHERE expires_at <= ?", (now,)
            ).fetchone()[0]

            return {
                "total_entries": total,
                "size_bytes": size_bytes,
                "size_mb": round(size_bytes / (1024 * 1024), 2),
                "expired_entries": expired,
                "by_namespace": [
                    {"namespace": ns, "count": cnt, "size_kb": round(sz / 1024, 1)}
                    for ns, cnt, sz in ns_stats
                ],
            }

        return await self._run(_stats)

    def _evict_if_needed_sync(self, conn, new_bytes: int):
        limit = MAX_SIZE_MB * 1024 * 1024
        while True:
            current = conn.execute(
                "SELECT COALESCE(SUM(LENGTH(value)), 0) FROM cache"
            ).fetchone()[0]
            if current + new_bytes <= limit:
                break
            oldest = conn.execute(
                "SELECT namespace, key FROM cache ORDER BY created_at ASC LIMIT 1"
            ).fetchone()
            if not oldest:
                break
            conn.execute(
                "DELETE FROM cache WHERE namespace=? AND key=?", oldest
            )


_cache: CacheManager | None = None


def get_cache() -> CacheManager:
    global _cache
    if _cache is None:
        db_dir = os.path.dirname(os.path.abspath(__file__))
        _cache = CacheManager(os.path.join(db_dir, "cache.db"))
    return _cache
