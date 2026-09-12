import sqlite3

from src.config import settings


DB_PATH = settings.database_path


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
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
        CREATE TABLE IF NOT EXISTS security_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            outcome TEXT NOT NULL,
            actor TEXT NOT NULL,
            detail TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

    columns = {row["name"] for row in cursor.execute("PRAGMA table_info(deployment_jobs)")}
    if "environment" not in columns:
        cursor.execute("ALTER TABLE deployment_jobs ADD COLUMN environment TEXT NOT NULL DEFAULT 'dev'")

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


def enqueue_deployment(delivery_id, app_name, repository, commit_hash, environment="dev"):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR IGNORE INTO deployment_jobs
        (delivery_id, app_name, repository, commit_hash, environment)
        VALUES (?, ?, ?, ?, ?)
    """, (delivery_id, app_name, repository, commit_hash, environment))

    job_id = cursor.lastrowid if cursor.rowcount == 1 else None
    conn.commit()
    conn.close()
    return job_id


def enqueue_webhook_deployment(delivery_id, event_type, app_name, repository, ref, commit_hash, environment="dev"):
    """Atomically deduplicate a webhook and create its deployment job."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute("""
            INSERT OR IGNORE INTO webhook_events
            (delivery_id, event_type, repository, ref, commit_hash)
            VALUES (?, ?, ?, ?, ?)
        """, (delivery_id, event_type, repository, ref, commit_hash))

        if cursor.rowcount != 1:
            conn.commit()
            return None

        cursor.execute("""
            INSERT INTO deployment_jobs
            (delivery_id, app_name, repository, commit_hash, environment)
            VALUES (?, ?, ?, ?, ?)
        """, (delivery_id, app_name, repository, commit_hash, environment))
        job_id = cursor.lastrowid
        conn.commit()
        return job_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def claim_next_deployment():
    conn = get_connection()
    cursor = conn.cursor()

    try:
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
            return None

        cursor.execute("""
            UPDATE deployment_jobs
            SET status = 'running', started_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (job["id"],))

        conn.commit()
        return dict(job)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def recover_interrupted_deployments():
    """Retry jobs left in running state when the worker process was interrupted."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE deployment_jobs
        SET status = 'queued',
            logs = COALESCE(logs, '') || '\nWorker restarted; deployment queued again.',
            started_at = NULL
        WHERE status = 'running'
    """)
    recovered = cursor.rowcount
    conn.commit()
    conn.close()
    return recovered


def list_deployment_jobs(limit: int = 20):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM deployment_jobs
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))
    jobs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jobs


def get_deployment_job(job_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM deployment_jobs WHERE id = ?", (job_id,))
    job = cursor.fetchone()
    conn.close()
    return dict(job) if job else None


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


def log_security_event(event_type, outcome, actor, detail=None):
    conn = get_connection()
    conn.execute(
        "INSERT INTO security_events (event_type, outcome, actor, detail) VALUES (?, ?, ?, ?)",
        (event_type, outcome, actor, detail),
    )
    conn.commit()
    conn.close()


def list_security_events(limit: int = 50):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM security_events ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def latest_successful_deployment(environment: str):
    conn = get_connection()
    row = conn.execute(
        """SELECT * FROM deployment_jobs
        WHERE environment = ? AND status = 'success'
        ORDER BY id DESC LIMIT 1""",
        (environment,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None
