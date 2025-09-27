"""Database connection and session management."""

import logging
from typing import AsyncGenerator

from sqlalchemy import MetaData
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class Database:
    def __init__(self, app=None):
        self.engine = None
        self.session_factory = None
        self.sync_engine = None  # Sync engine for APScheduler
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialize database with Quart app."""
        database_url = app.config.get("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL must be configured")

        # Only echo if SQLAlchemy logging is explicitly set to DEBUG/INFO
        sqlalchemy_logger = logging.getLogger("sqlalchemy.engine")
        should_echo = sqlalchemy_logger.isEnabledFor(logging.INFO)

        # In debug mode, respect the logger level instead of always echoing
        if app.config.get("DEBUG", False):
            app.logger.debug(
                f"Debug mode: SQLAlchemy echo={should_echo} (based on logger level)"
            )

        # Create async engine for SQLite
        self.engine = create_async_engine(
            database_url,
            echo=should_echo,  # Respect the logger configuration
        )

        # Create sync engine for APScheduler (use sqlite driver)
        sync_database_url = database_url.replace("+aiosqlite", "")
        self.sync_engine = create_engine(
            sync_database_url,
            echo=should_echo,
        )

        # Create session factory
        self.session_factory = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

        app.extensions["database"] = self

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get database session."""
        if not self.session_factory:
            raise RuntimeError("Database not initialized")

        async with self.session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    async def create_tables(self):
        """Create all tables."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self):
        """Close database connection."""
        if self.engine:
            await self.engine.dispose()
        if self.sync_engine:
            self.sync_engine.dispose()
