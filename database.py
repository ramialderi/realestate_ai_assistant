import sqlite3
from contextlib import closing

DB_PATH = "realestate.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with closing(get_conn()) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS properties (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id INTEGER NOT NULL,
                deal_type TEXT NOT NULL,      -- بيع / إيجار
                category TEXT NOT NULL,       -- شقة / فيلا / أرض / محل
                city TEXT NOT NULL,
                price REAL NOT NULL,
                area REAL,
                rooms INTEGER,
                description TEXT,
                photo_file_id TEXT,
                phone TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agents (
                telegram_id INTEGER PRIMARY KEY,
                name TEXT,
                phone TEXT,
                joined_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def upsert_agent(telegram_id: int, name: str):
    with closing(get_conn()) as conn:
        conn.execute(
            "INSERT INTO agents (telegram_id, name) VALUES (?, ?) "
            "ON CONFLICT(telegram_id) DO UPDATE SET name=excluded.name",
            (telegram_id, name),
        )
        conn.commit()


def add_property(agent_id, deal_type, category, city, price, area, rooms, description, photo_file_id, phone):
    with closing(get_conn()) as conn:
        cur = conn.execute(
            """INSERT INTO properties
               (agent_id, deal_type, category, city, price, area, rooms, description, photo_file_id, phone)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (agent_id, deal_type, category, city, price, area, rooms, description, photo_file_id, phone),
        )
        conn.commit()
        return cur.lastrowid


def search_properties(deal_type=None, category=None, city=None, min_price=None, max_price=None, limit=10, offset=0):
    query = "SELECT * FROM properties WHERE 1=1"
    params = []
    if deal_type:
        query += " AND deal_type = ?"
        params.append(deal_type)
    if category:
        query += " AND category = ?"
        params.append(category)
    if city:
        query += " AND city LIKE ?"
        params.append(f"%{city}%")
    if min_price is not None:
        query += " AND price >= ?"
        params.append(min_price)
    if max_price is not None:
        query += " AND price <= ?"
        params.append(max_price)
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    with closing(get_conn()) as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def get_property(prop_id):
    with closing(get_conn()) as conn:
        row = conn.execute("SELECT * FROM properties WHERE id = ?", (prop_id,)).fetchone()
        return dict(row) if row else None


def list_agent_properties(agent_id):
    with closing(get_conn()) as conn:
        rows = conn.execute(
            "SELECT * FROM properties WHERE agent_id = ? ORDER BY created_at DESC", (agent_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def delete_property(prop_id, agent_id):
    with closing(get_conn()) as conn:
        cur = conn.execute(
            "DELETE FROM properties WHERE id = ? AND agent_id = ?", (prop_id, agent_id)
        )
        conn.commit()
        return cur.rowcount > 0
