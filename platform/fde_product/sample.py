"""Generic fictional read-only sample, unrelated to Qinghe customer data."""

from contextlib import closing
from pathlib import Path
import sqlite3

from .runtime import Tool, ToolRegistry


def initialize_database(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS sample_coverage(store_id TEXT, day TEXT, PRIMARY KEY(store_id,day));
        CREATE TABLE IF NOT EXISTS sample_orders(id TEXT PRIMARY KEY, store_id TEXT, day TEXT);
        INSERT OR IGNORE INTO sample_coverage VALUES ('SAMPLE-01','2026-01-01'),('SAMPLE-01','2026-01-02');
        INSERT OR IGNORE INTO sample_orders VALUES
          ('D-001','SAMPLE-01','2026-01-01'),('D-002','SAMPLE-01','2026-01-01'),('D-003','SAMPLE-01','2026-01-01');
        """)


def sample_registry(path):
    path = Path(path).resolve()

    def count_orders(store_id, day):
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
            covered = db.execute("SELECT 1 FROM sample_coverage WHERE store_id=? AND day=?", (store_id, day)).fetchone()
            source = f"DATA-DEMO-ORDERS-v1/{store_id}/{day}"
            if not covered:
                return {"status": "missing", "code": "DATA_NOT_PROVIDED", "source_id": source}
            count = db.execute("SELECT count(*) FROM sample_orders WHERE store_id=? AND day=?", (store_id, day)).fetchone()[0]
            return {"status": "ok", "order_count": count, "source_id": source}

    registry = ToolRegistry()
    registry.register(Tool("count_sample_orders", "查询虚构样例门店某日订单数；必须提供门店和日期。数据缺失不等于零。",
                          {"type": "object", "required": ["store_id", "day"], "additionalProperties": False,
                           "properties": {"store_id": {"type": "string", "pattern": "^SAMPLE-[0-9]{2}$"},
                                          "day": {"type": "string", "format": "date"}}},
                          count_orders, "sample:read"))
    return registry
