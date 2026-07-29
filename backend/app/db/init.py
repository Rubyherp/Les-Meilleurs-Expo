import asyncio

from sqlalchemy import text

from app.db.base import Base
from app.db.session import engine
from app.models import (  # noqa: F401
    AnalysisAttempt,
    AnalysisCache,
    AnalysisJob,
    AnalysisResult,
    AnalysisSession,
    StoredMedia,
)


async def initialize_database() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        if connection.dialect.name == "postgresql":
            # Keep earlier databases usable until versioned migrations are added.
            await connection.execute(
                text(
                    "ALTER TABLE analysis_jobs ADD COLUMN IF NOT EXISTS "
                    "media_id UUID REFERENCES stored_media(id) ON DELETE SET NULL"
                )
            )
            await connection.execute(
                text("ALTER TABLE analysis_sessions ADD COLUMN IF NOT EXISTS calibration JSONB")
            )
            await connection.execute(
                text("ALTER TABLE stored_media ADD COLUMN IF NOT EXISTS role VARCHAR(16)")
            )
            await connection.execute(
                text("ALTER TABLE analysis_jobs ADD COLUMN IF NOT EXISTS mode VARCHAR(32) NOT NULL DEFAULT 'single'")
            )
            await connection.execute(
                text("ALTER TABLE analysis_jobs ADD COLUMN IF NOT EXISTS reference_media_id UUID REFERENCES stored_media(id) ON DELETE SET NULL")
            )
            await connection.execute(
                text("ALTER TABLE analysis_jobs ADD COLUMN IF NOT EXISTS attempt_media_id UUID REFERENCES stored_media(id) ON DELETE SET NULL")
            )
            await connection.execute(
                text(
                    "ALTER TABLE analysis_jobs ADD COLUMN IF NOT EXISTS "
                    "expected_dancer_count INTEGER NOT NULL DEFAULT 1"
                )
            )
            await connection.execute(
                text("ALTER TABLE analysis_jobs ADD COLUMN IF NOT EXISTS control_state JSONB")
            )


if __name__ == "__main__":
    asyncio.run(initialize_database())
