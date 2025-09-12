from typing import Optional

from quart import current_app
from quart_auth import AuthUser
from werkzeug.security import check_password_hash
from werkzeug.security import generate_password_hash

from src.models.user_db import UserModel


class User(AuthUser):
    """User model for authentication."""

    def __init__(
        self,
        auth_id,
        email: Optional[str] = None,
        password_hash: Optional[str] = None,
        name: Optional[str] = None,
        active: bool = True,
        **kwargs,
    ):
        super().__init__(auth_id)
        self.id: int = auth_id
        self.email: Optional[str] = email
        self.password_hash: Optional[str] = password_hash
        self.name: Optional[str] = name
        self.active: bool = active
        self._resolved: bool = False

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email})>"

    @classmethod
    def from_db_model(cls, db_user: UserModel) -> "User":
        """Create User instance from database model."""
        return cls(
            auth_id=db_user.id,
            email=db_user.email,
            password_hash=db_user.password_hash,
            name=db_user.name,
            active=db_user.active,
        )

    async def load_user_data(self) -> "User":
        """Load user data from database."""
        if not self._resolved:
            user_manager = current_app.extensions["user_manager"]
            db_user = await user_manager.get_user(self.id)
            if db_user:
                self.email = db_user.email
                self.password_hash = db_user.password_hash
                self.name = db_user.name
                self.active = db_user.active
                self._resolved = True
        return self

    def is_active(self) -> bool:
        return self.active

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    async def save(self):
        """Save user changes to database."""
        user_manager = current_app.extensions["user_manager"]
        await user_manager.update_user(self)
        self._resolved = False


class UserManager:
    """Manager class for user operations as a Quart extension."""

    def __init__(self, app=None):
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialise with Quart app."""
        self.db = app.extensions["database"]
        app.extensions["user_manager"] = self

    def get_session(self):
        """Get database session context manager."""
        return self.db.session_factory()

    async def get_user(self, user_id: int) -> Optional[User]:
        """Get user by ID."""
        async with self.db.session_factory() as session:
            db_user = await UserModel.get_by_id(session, user_id)
            if db_user:
                return User.from_db_model(db_user)
            return None

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email address."""
        async with self.db.session_factory() as session:
            db_user = await UserModel.get_by_email(session, email)
            if db_user:
                return User.from_db_model(db_user)
            return None

    async def create_user(self, **kwargs) -> Optional[User]:
        """Create a new user."""
        async with self.db.session_factory() as session:
            db_user = await UserModel.create_user(session, **kwargs)
            user = User.from_db_model(db_user)
            return user

    async def update_user(self, user: User):
        """Update user in database."""
        async with self.db.session_factory() as session:
            db_user = await UserModel.get_by_id(session, user.id)
            if db_user:
                await db_user.update(
                    session,
                    email=user.email,
                    password_hash=user.password_hash,
                    name=user.name,
                    active=user.active,
                )

    async def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """Authenticate user with email and password."""
        user = await self.get_user_by_email(email)
        if user and user.is_active() and user.check_password(password):
            return user
        return None
