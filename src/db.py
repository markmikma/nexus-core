import os
import sqlite3

DB_PATH = os.path.abspath("./data/nexus.db")


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS deployments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            app_name TEXT NOT NULL,
            commit_hash TEXT,
            status TEXT NOT NULL,
            logs TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

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
        CREATE TABLE IF NOT EXISTS deployment_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            delivery_id TEXT UNIQUE NOT NULL,
            app_name TEXT NOT NULL,
            repository TEXT NOT NULL,
            commit_hash TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            logs TEXT,
            container_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            finished_at TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def register_or_update_app(name, repo_url, status, port=None, container_id=None):
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


def log_deployment(app_name, status, commit_hash=None, logs=None):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO deployments (app_name, status, commit_hash, logs)
        VALUES (?, ?, ?, ?)
    """, (app_name, status, commit_hash, logs))

    conn.commit()
    conn.close()


def record_webhook_event(delivery_id, event_type, repository, ref, commit_hash):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR IGNORE INTO webhook_events
        (delivery_id, event_type, repository, ref, commit_hash)
        VALUES (?, ?, ?, ?, ?)
    """, (delivery_id, event_type, repository, ref, commit_hash))

    inserted = cursor.rowcount == 1
    conn.commit()
    conn.close()
    return inserted


def enqueue_deployment(delivery_id, app_name, repository, commit_hash):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR IGNORE INTO deployment_jobs
        (delivery_id, app_name, repository, commit_hash)
        VALUES (?, ?, ?, ?)
    """, (delivery_id, app_name, repository, commit_hash))

    job_id = cursor.lastrowid if cursor.rowcount == 1 else None
    conn.commit()
    conn.close()
    return job_id


def claim_next_deployment():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("BEGIN IMMEDIATE")
    cursor.execute("""
        SELECT * FROM deployment_jobs
        WHERE status = 'queued'
        ORDER BY id
        LIMIT 1
    """)

    job = cursor.fetchone()
    if job is None:
        conn.commit()
        conn.close()
        return None

    cursor.execute("""
        UPDATE deployment_jobs
        SET status = 'running', started_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (job["id"],))

    conn.commit()
    conn.close()
    return dict(job)


def finish_deployment(job_id, status, logs=None, container_id=None):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE deployment_jobs
        SET status = ?,
            logs = ?,
            container_id = ?,
            finished_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (status, logs, container_id, job_id))

    conn.commit()
    conn.close()