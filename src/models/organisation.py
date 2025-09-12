"""Database models for organisations."""

from typing import Optional

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.sql import func

from src.modules.database import Base


class OrganisationModel(Base):
    """Organisation model for database storage."""

    __tablename__ = "organisations"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    short_name = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    timezone = Column(String(50), nullable=False, default="Pacific/Auckland")

    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )

    @staticmethod
    async def get_by_id(
        session: AsyncSession, org_id: int
    ) -> Optional["OrganisationModel"]:
        """Get organisation by ID."""
        result = await session.execute(
            select(OrganisationModel).where(OrganisationModel.id == org_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_short_name(
        session: AsyncSession, short_name: str
    ) -> Optional["OrganisationModel"]:
        """Get organisation by short name."""
        result = await session.execute(
            select(OrganisationModel).where(OrganisationModel.short_name == short_name)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_organisation(
        session: AsyncSession, **kwargs
    ) -> "OrganisationModel":
        """Create a new organisation."""
        # Ensure short_name is lowercase
        if "short_name" in kwargs:
            kwargs["short_name"] = kwargs["short_name"].lower()

        org = OrganisationModel(**kwargs)
        session.add(org)
        await session.commit()
        await session.refresh(org)
        return org
