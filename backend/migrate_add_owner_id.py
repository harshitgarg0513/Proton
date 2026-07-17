#!/usr/bin/env python3
"""
Migration script to add owner_id columns to files and jobs tables.
Run this after updating the models to add owner_id fields.
"""

from sqlalchemy import text
from app.core.database import engine


def migrate():
    """Add owner_id columns to files and jobs tables."""
    with engine.connect() as conn:
        # Add owner_id to files table
        try:
            conn.execute(text("ALTER TABLE files ADD COLUMN IF NOT EXISTS owner_id VARCHAR(64) NOT NULL DEFAULT 'demo-api-key-12345678'"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_files_owner_id ON files(owner_id)"))
            print("✓ Added owner_id column to files table")
        except Exception as e:
            print(f"✗ Error adding owner_id to files: {e}")

        # Add owner_id to jobs table
        try:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS owner_id VARCHAR(64) NOT NULL DEFAULT 'demo-api-key-12345678'"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_jobs_owner_id ON jobs(owner_id)"))
            print("✓ Added owner_id column to jobs table")
        except Exception as e:
            print(f"✗ Error adding owner_id to jobs: {e}")

        conn.commit()
        print("Migration completed successfully!")


if __name__ == "__main__":
    migrate()
