"""Database models for grocery shopping prediction feature."""

from typing import List
from typing import Optional

from sqlalchemy import Column
from sqlalchemy import Date
from sqlalchemy import DateTime
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.modules.database import Base


class GroceryItem(Base):
    """Grocery item model with learned frequency patterns."""

    __tablename__ = "grocery_items"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    unit_type = Column(String(50), nullable=True)
    typical_quantity = Column(Float, nullable=True)
    base_frequency_days = Column(Integer, nullable=True)
    frequency_adjustment_days = Column(Integer, nullable=False, default=0)
    last_purchased_date = Column(Date, nullable=True, index=True)

    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    order_items = relationship("OrderItem", back_populates="item")
    shopping_list_entries = relationship("ShoppingList", back_populates="item")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def __repr__(self):
        return f"<GroceryItem(id={self.id}, name={self.name}, user_id={self.user_id})>"

    @staticmethod
    async def get_by_id(session: AsyncSession, item_id: int) -> Optional["GroceryItem"]:
        """Get grocery item by ID."""
        result = await session.execute(
            select(GroceryItem).where(GroceryItem.id == item_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_user_and_name(
        session: AsyncSession, user_id: int, name: str
    ) -> Optional["GroceryItem"]:
        """Get grocery item by user and name (case-insensitive)."""
        result = await session.execute(
            select(GroceryItem).where(
                GroceryItem.user_id == user_id,
                func.lower(GroceryItem.name) == func.lower(name),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_all_by_user(
        session: AsyncSession, user_id: int
    ) -> List["GroceryItem"]:
        """Get all grocery items for a user."""
        result = await session.execute(
            select(GroceryItem).where(GroceryItem.user_id == user_id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def create_item(session: AsyncSession, **kwargs) -> "GroceryItem":
        """Create a new grocery item."""
        item = GroceryItem(**kwargs)
        session.add(item)
        await session.commit()
        await session.refresh(item)
        return item

    async def update(self, session: AsyncSession, **kwargs):
        """Update grocery item fields."""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        await session.commit()

    async def delete(self, session: AsyncSession):
        """Delete grocery item."""
        await session.delete(self)
        await session.commit()


class GroceryOrder(Base):
    """Grocery order model for purchase history."""

    __tablename__ = "grocery_orders"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    supermarket = Column(String(100), nullable=False)
    order_date = Column(Date, nullable=False, index=True)
    total_cost = Column(Float, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    order_items = relationship(
        "OrderItem", back_populates="order", cascade="all, delete-orphan"
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def __repr__(self):
        return (
            f"<GroceryOrder(id={self.id}, supermarket={self.supermarket},"
            f" date={self.order_date})>"
        )

    @staticmethod
    async def get_by_id(
        session: AsyncSession, order_id: int
    ) -> Optional["GroceryOrder"]:
        """Get grocery order by ID."""
        result = await session.execute(
            select(GroceryOrder).where(GroceryOrder.id == order_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_all_by_user(
        session: AsyncSession, user_id: int, limit: int = None
    ) -> List["GroceryOrder"]:
        """Get all grocery orders for a user, optionally limited."""
        query = (
            select(GroceryOrder)
            .where(GroceryOrder.user_id == user_id)
            .order_by(GroceryOrder.order_date.desc())
        )
        if limit:
            query = query.limit(limit)

        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def create_order(session: AsyncSession, **kwargs) -> "GroceryOrder":
        """Create a new grocery order."""
        order = GroceryOrder(**kwargs)
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return order

    async def delete(self, session: AsyncSession):
        """Delete grocery order."""
        await session.delete(self)
        await session.commit()


class OrderItem(Base):
    """Order item model linking orders to grocery items."""

    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True)
    order_id = Column(
        Integer, ForeignKey("grocery_orders.id", ondelete="CASCADE"), nullable=False
    )
    item_id = Column(Integer, ForeignKey("grocery_items.id"), nullable=False)
    quantity = Column(Float, nullable=False)
    unit_price = Column(Float, nullable=True)
    total_price = Column(Float, nullable=True)

    # Relationships
    order = relationship("GroceryOrder", back_populates="order_items")
    item = relationship("GroceryItem", back_populates="order_items")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def __repr__(self):
        return (
            f"<OrderItem(id={self.id}, order_id={self.order_id},"
            f" item_id={self.item_id})>"
        )

    @staticmethod
    async def get_by_id(session: AsyncSession, item_id: int) -> Optional["OrderItem"]:
        """Get order item by ID."""
        result = await session.execute(select(OrderItem).where(OrderItem.id == item_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_order(session: AsyncSession, order_id: int) -> List["OrderItem"]:
        """Get all items for an order."""
        result = await session.execute(
            select(OrderItem).where(OrderItem.order_id == order_id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_by_item(
        session: AsyncSession, item_id: int, limit: int = None
    ) -> List["OrderItem"]:
        """Get all order items for a grocery item, optionally limited."""
        query = (
            select(OrderItem)
            .where(OrderItem.item_id == item_id)
            .join(GroceryOrder)
            .order_by(GroceryOrder.order_date.desc())
        )
        if limit:
            query = query.limit(limit)

        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def create_order_item(session: AsyncSession, **kwargs) -> "OrderItem":
        """Create a new order item."""
        order_item = OrderItem(**kwargs)
        session.add(order_item)
        await session.commit()
        await session.refresh(order_item)
        return order_item

    async def delete(self, session: AsyncSession):
        """Delete order item."""
        await session.delete(self)
        await session.commit()


class ShoppingList(Base):
    """Shopping list model for urgent items and planning."""

    __tablename__ = "shopping_list"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("grocery_items.id"), nullable=False)
    quantity_needed = Column(Float, nullable=True)
    urgency = Column(String(20), nullable=False, default="normal")
    added_at = Column(DateTime, default=func.now(), nullable=False)
    notes = Column(Text, nullable=True)

    # Relationships
    item = relationship("GroceryItem", back_populates="shopping_list_entries")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def __repr__(self):
        return (
            f"<ShoppingList(id={self.id}, user_id={self.user_id},"
            f" item_id={self.item_id})>"
        )

    @staticmethod
    async def get_by_id(
        session: AsyncSession, list_id: int
    ) -> Optional["ShoppingList"]:
        """Get shopping list entry by ID."""
        result = await session.execute(
            select(ShoppingList).where(ShoppingList.id == list_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_user_and_item(
        session: AsyncSession, user_id: int, item_id: int
    ) -> Optional["ShoppingList"]:
        """Get shopping list entry by user and item."""
        result = await session.execute(
            select(ShoppingList).where(
                ShoppingList.user_id == user_id, ShoppingList.item_id == item_id
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_all_by_user(
        session: AsyncSession, user_id: int
    ) -> List["ShoppingList"]:
        """Get all shopping list items for a user."""
        result = await session.execute(
            select(ShoppingList).where(ShoppingList.user_id == user_id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def create_entry(session: AsyncSession, **kwargs) -> "ShoppingList":
        """Create a new shopping list entry."""
        entry = ShoppingList(**kwargs)
        session.add(entry)
        await session.commit()
        await session.refresh(entry)
        return entry

    async def update(self, session: AsyncSession, **kwargs):
        """Update shopping list entry fields."""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        await session.commit()

    async def delete(self, session: AsyncSession):
        """Delete shopping list entry."""
        await session.delete(self)
        await session.commit()
