import sqlite3
import os

DB_PATH = os.path.abspath("./data/nexus.db")

def get_connection():
    """Létrehozza a data mappát ha nem létezik, és visszaadja az SQLite kapcsolatot."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Inicializálja az adatbázis táblákat."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Alkalmazások nyilvántartása
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS apps (
            name TEXT PRIMARY KEY,
            repo_url TEXT NOT NULL,
            status TEXT NOT NULL,
            port INTEGER,
            container_id TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Deployment napló
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS deployments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            app_name TEXT NOT NULL,
            commit_hash TEXT,
            status TEXT NOT NULL,
            logs TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (app_name) REFERENCES apps (name)
        )
    """)
    
    conn.commit()
    conn.close()
    print("[*] SQLite adatbázis inicializálva: data/nexus.db")

def register_or_update_app(name: str, repo_url: str, status: str, port: int = None, container_id: str = None):
    """Regisztrál egy új alkalmazást vagy frissíti a létező állapotát."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO apps (name, repo_url, status, port, container_id, updated_at)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(name) DO UPDATE SET
            status=excluded.status,
            port=COALESCE(excluded.port, apps.port),
            container_id=COALESCE(excluded.container_id, apps.container_id),
            updated_at=CURRENT_TIMESTAMP
    """, (name, repo_url, status, port, container_id))
    conn.commit()
    conn.close()

def log_deployment(app_name: str, status: str, commit_hash: str = None, logs: str = None):
    """Rögzít egy deployment eseményt a naplóban."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO deployments (app_name, status, commit_hash, logs)
        VALUES (?, ?, ?, ?)
    """, (app_name, status, commit_hash, logs))
    conn.commit()
    conn.close()

def record_webhook_event(
    delivery_id: str,
    event_type: str,
    repository: str,
    ref: str,
    commit_hash: str,
) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS webhook_events (
            delivery_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            repository TEXT NOT NULL,
            ref TEXT,
            commit_hash TEXT,
            received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        INSERT OR IGNORE INTO webhook_events
        (delivery_id, event_type, repository, ref, commit_hash)
        VALUES (?, ?, ?, ?, ?)
    """, (delivery_id, event_type, repository, ref, commit_hash))
    inserted = cursor.rowcount == 1
    conn.commit()
    conn.close()
    return inserted