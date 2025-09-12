"""Database models for users and authentication providers."""

from typing import List
from typing import Optional

from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import UniqueConstraint
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.sql import func
from werkzeug.security import generate_password_hash

from src.modules.database import Base


class UserModel(Base):
    """User model for database storage."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(Text, nullable=True)
    name = Column(String(255), nullable=False)
    active = Column(Boolean, nullable=False, default=True)

    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @staticmethod
    async def get_by_id(session: AsyncSession, user_id: int) -> Optional["UserModel"]:
        """Get user by ID."""
        result = await session.execute(select(UserModel).where(UserModel.id == user_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_email(session: AsyncSession, email: str) -> Optional["UserModel"]:
        """Get user by email."""
        result = await session.execute(
            select(UserModel).where(UserModel.email == email.lower())
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_all(session: AsyncSession) -> List["UserModel"]:
        """Get all users."""
        result = await session.execute(select(UserModel))
        return result.scalars().all()

    @staticmethod
    async def create_user(session: AsyncSession, **kwargs) -> "UserModel":
        """Create a new user."""
        # Hash password if provided
        if "password" in kwargs:
            kwargs["password_hash"] = generate_password_hash(kwargs.pop("password"))

        # Ensure email is lowercase
        if "email" in kwargs:
            kwargs["email"] = kwargs["email"].lower()

        user = UserModel(**kwargs)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user

    async def update(self, session: AsyncSession, **kwargs):
        """Update user fields."""
        # Handle password hashing
        if "password" in kwargs:
            kwargs["password_hash"] = generate_password_hash(kwargs.pop("password"))

        # Handle email normalization
        if "email" in kwargs:
            kwargs["email"] = kwargs["email"].lower()

        # Apply updates
        for key, value in kwargs.items():
            setattr(self, key, value)

        await session.commit()

    async def delete(self, session: AsyncSession):
        """Delete user."""
        await session.delete(self)
        await session.commit()


class UserAuthProviderModel(Base):
    """OAuth provider associations for users."""

    __tablename__ = "user_auth_providers"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider = Column(String(50), nullable=False)  # 'google', 'linkedin', etc.
    provider_user_id = Column(String(255), nullable=False)  # OAuth provider's user ID
    provider_email = Column(
        String(255), nullable=True
    )  # Email associated with this provider

    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )

    # Ensure unique provider per user and unique provider account globally
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_user_provider"),
        UniqueConstraint("provider", "provider_user_id", name="uq_provider_account"),
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @staticmethod
    async def get_by_provider_and_id(
        session: AsyncSession, provider: str, provider_user_id: str
    ) -> Optional["UserAuthProviderModel"]:
        """Get auth provider record by provider name and provider user ID."""
        result = await session.execute(
            select(UserAuthProviderModel).where(
                UserAuthProviderModel.provider == provider,
                UserAuthProviderModel.provider_user_id == provider_user_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_user_id(
        session: AsyncSession, user_id: int
    ) -> List["UserAuthProviderModel"]:
        """Get all auth providers for a user."""
        result = await session.execute(
            select(UserAuthProviderModel).where(
                UserAuthProviderModel.user_id == user_id
            )
        )
        return result.scalars().all()

    @staticmethod
    async def get_by_user_and_provider(
        session: AsyncSession, user_id: int, provider: str
    ) -> Optional["UserAuthProviderModel"]:
        """Get specific provider for a user."""
        result = await session.execute(
            select(UserAuthProviderModel).where(
                UserAuthProviderModel.user_id == user_id,
                UserAuthProviderModel.provider == provider,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_provider(
        session: AsyncSession, **kwargs
    ) -> "UserAuthProviderModel":
        """Create a new auth provider record."""
        provider = UserAuthProviderModel(**kwargs)
        session.add(provider)
        await session.commit()
        await session.refresh(provider)
        return provider

    async def delete(self, session: AsyncSession):
        """Delete this auth provider record."""
        await session.delete(self)
        await session.commit()

    @staticmethod
    async def count_providers_for_user(session: AsyncSession, user_id: int) -> int:
        """Count how many auth providers a user has."""
        result = await session.execute(
            select(func.count(UserAuthProviderModel.id)).where(
                UserAuthProviderModel.user_id == user_id
            )
        )
        return result.scalar() or 0
