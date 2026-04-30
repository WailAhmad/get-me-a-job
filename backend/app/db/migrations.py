from sqlalchemy import inspect, text


def ensure_sqlite_schema(engine):
    if not engine.url.get_backend_name().startswith("sqlite"):
        return
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        if "candidate_profile" in tables:
            cols = {c["name"] for c in inspector.get_columns("candidate_profile")}
            additions = {
                "current_company": "VARCHAR(200) DEFAULT ''",
                "nationality": "VARCHAR(120) DEFAULT ''",
                "summary": "TEXT DEFAULT ''",
                "core_skills_json": "TEXT DEFAULT '[]'",
                "ai_experience_json": "TEXT DEFAULT '[]'",
                "data_experience_json": "TEXT DEFAULT '[]'",
                "cloud_platforms_json": "TEXT DEFAULT '[]'",
                "governance_tools_json": "TEXT DEFAULT '[]'",
                "industries_json": "TEXT DEFAULT '[]'",
                "employers_json": "TEXT DEFAULT '[]'",
                "education_json": "TEXT DEFAULT '[]'",
                "certifications_json": "TEXT DEFAULT '[]'",
                "major_achievements_json": "TEXT DEFAULT '[]'",
            }
            for name, ddl in additions.items():
                if name not in cols:
                    conn.execute(text(f"ALTER TABLE candidate_profile ADD COLUMN {name} {ddl}"))
        if "source_accounts" in tables:
            cols = {c["name"] for c in inspector.get_columns("source_accounts")}
            additions = {
                "token_path": "VARCHAR(500) DEFAULT ''",
                "sync_status": "VARCHAR(80) DEFAULT 'idle'",
                "last_error": "TEXT DEFAULT ''",
            }
            for name, ddl in additions.items():
                if name not in cols:
                    conn.execute(text(f"ALTER TABLE source_accounts ADD COLUMN {name} {ddl}"))
        if "jobs" in tables:
            cols = {c["name"] for c in inspector.get_columns("jobs")}
            additions = {
                "source_email_id": "VARCHAR(250) DEFAULT ''",
                "source_email_subject": "VARCHAR(500) DEFAULT ''",
                "source_email_from": "VARCHAR(250) DEFAULT ''",
            }
            for name, ddl in additions.items():
                if name not in cols:
                    conn.execute(text(f"ALTER TABLE jobs ADD COLUMN {name} {ddl}"))
