from pathlib import Path

from dotenv import load_dotenv
import psycopg

from app.infrastructure.config import get_database_url


def apply_migrations() -> None:
    """Apply pending SQL migrations using DATABASE_URL."""
    migrations_dir = Path(__file__).resolve().parent.parent / "supabase" / "migrations"
    sql_files = sorted(migrations_dir.glob("*.sql"))

    if not sql_files:
        raise SystemExit(
            "Copia los archivos SQL entregados por separado en backend/supabase/migrations/."
        )

    load_dotenv()
    database_url = get_database_url()

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(481927)")
            cur.execute("CREATE SCHEMA IF NOT EXISTS planner_internal")
            cur.execute(
                "CREATE TABLE IF NOT EXISTS planner_internal.migrations "
                "(name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
            )
            cur.execute("SELECT name FROM planner_internal.migrations")
            applied = {row[0] for row in cur.fetchall()}
            for sql_file in sql_files:
                if sql_file.name in applied:
                    continue
                cur.execute(sql_file.read_text(encoding="utf-8"))
                cur.execute(
                    "INSERT INTO planner_internal.migrations (name) VALUES (%s)",
                    (sql_file.name,),
                )
        conn.commit()


if __name__ == "__main__":
    apply_migrations()
