"""Unit tests for grocery tools and service functions."""

import os
import tempfile
from datetime import date
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine

from src.models.grocery import GroceryItem
from src.models.grocery import ShoppingList
from src.modules import grocery_service
from src.modules.database import Base


@pytest_asyncio.fixture
async def test_db():
    """Create a temporary SQLite database for testing."""
    # Create temporary database file
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)

    try:
        # Create async engine for SQLite
        database_url = f"sqlite+aiosqlite:///{db_path}"
        engine = create_async_engine(database_url, echo=False)

        # Create all tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Create session factory
        from sqlalchemy.ext.asyncio import async_sessionmaker

        session_factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        yield session_factory

        # Cleanup
        await engine.dispose()
        os.unlink(db_path)

    except Exception as e:
        # Cleanup on error
        try:
            os.unlink(db_path)
        except Exception:
            pass
        raise e


@pytest.mark.asyncio
async def test_find_or_create_item(test_db):
    """Test finding or creating grocery items."""
    async with test_db() as session:
        # Create new item
        item1 = await grocery_service.find_or_create_item(
            session, user_id=1, name="anchor milk 2l"
        )
        assert item1.name == "Anchor Milk 2l"  # Should be capitalized
        assert item1.user_id == 1

        # Find existing item (case-insensitive)
        item2 = await grocery_service.find_or_create_item(
            session, user_id=1, name="ANCHOR MILK 2L"
        )
        assert item1.id == item2.id  # Should be same item


@pytest.mark.asyncio
async def test_record_order_basic(test_db):
    """Test recording a basic grocery order."""
    async with test_db() as session:
        items = [
            {"name": "Milk", "quantity": 2.0},
            {"name": "Eggs", "quantity": 12.0},
            {"name": "Bread", "quantity": 1.0},
        ]

        order, updated_count = await grocery_service.record_order(
            session,
            user_id=1,
            supermarket="Tesco",
            items=items,
            order_date=date.today(),
        )

        assert order.supermarket == "Tesco"
        assert order.user_id == 1
        assert updated_count == 0  # No frequencies updated (first purchase)

        # Verify items were created
        all_items = await GroceryItem.get_all_by_user(session, 1)
        assert len(all_items) == 3


@pytest.mark.asyncio
async def test_frequency_calculation(test_db):
    """Test frequency calculation after multiple purchases."""
    async with test_db() as session:
        user_id = 1
        item_name = "Milk"

        # First purchase
        await grocery_service.record_order(
            session,
            user_id=user_id,
            supermarket="Tesco",
            items=[{"name": item_name, "quantity": 2.0}],
            order_date=date.today() - timedelta(days=14),
        )

        # Second purchase (7 days later)
        await grocery_service.record_order(
            session,
            user_id=user_id,
            supermarket="Tesco",
            items=[{"name": item_name, "quantity": 2.0}],
            order_date=date.today() - timedelta(days=7),
        )

        # Third purchase (7 days later)
        order, updated_count = await grocery_service.record_order(
            session,
            user_id=user_id,
            supermarket="Tesco",
            items=[{"name": item_name, "quantity": 2.0}],
            order_date=date.today(),
        )

        assert updated_count == 1  # Frequency should be calculated

        # Check item frequency
        item = await GroceryItem.get_by_user_and_name(session, user_id, item_name)
        assert item.base_frequency_days == 7  # Median of [7, 7] = 7
        assert item.typical_quantity == 2.0


@pytest.mark.asyncio
async def test_calculate_predictions(test_db):
    """Test prediction calculation."""
    async with test_db() as session:
        user_id = 1

        # Create item with known frequency
        await GroceryItem.create_item(
            session,
            user_id=user_id,
            name="Milk",
            base_frequency_days=7,
            typical_quantity=2.0,
            unit_type="liters",
            last_purchased_date=date.today()
            - timedelta(days=8),  # 8 days ago (overdue)
        )

        # Calculate predictions
        predictions = await grocery_service.calculate_predictions(
            session, user_id=user_id, min_priority=0.8
        )

        assert len(predictions) == 1
        assert predictions[0]["item_name"] == "Milk"
        assert predictions[0]["priority_score"] > 1.0  # Overdue


@pytest.mark.asyncio
async def test_shopping_list_integration(test_db):
    """Test shopping list integration with predictions."""
    async with test_db() as session:
        user_id = 1

        # Create item with low priority (not quite due)
        await GroceryItem.create_item(
            session,
            user_id=user_id,
            name="Chocolate",
            base_frequency_days=14,
            typical_quantity=1.0,
            last_purchased_date=date.today() - timedelta(days=10),  # Priority ~0.71
        )

        # Should not appear in predictions (below 0.8 threshold)
        predictions1 = await grocery_service.calculate_predictions(
            session, user_id=user_id, min_priority=0.8
        )
        assert len(predictions1) == 0

        # Add to shopping list
        await grocery_service.add_to_shopping_list(
            session, user_id=user_id, item_name="Chocolate", urgency="high"
        )

        # Should now appear with boosted priority
        predictions2 = await grocery_service.calculate_predictions(
            session, user_id=user_id, min_priority=0.8
        )
        assert len(predictions2) == 1
        assert predictions2[0]["is_urgent"] is True
        assert predictions2[0]["urgency_level"] == "high"


@pytest.mark.asyncio
async def test_adjust_item_frequency(test_db):
    """Test frequency adjustment."""
    async with test_db() as session:
        user_id = 1

        # Create item
        item = await GroceryItem.create_item(
            session,
            user_id=user_id,
            name="Bananas",
            base_frequency_days=7,
            frequency_adjustment_days=0,
        )

        # Adjust frequency (buy less often)
        adjusted = await grocery_service.adjust_item_frequency(
            session, user_id=user_id, item_name="Bananas", adjustment_weeks=2
        )

        assert adjusted.frequency_adjustment_days == 14  # 2 weeks * 7 days
        assert adjusted.id == item.id

        # Adjust again (buy more often)
        adjusted2 = await grocery_service.adjust_item_frequency(
            session, user_id=user_id, item_name="Bananas", adjustment_weeks=-1
        )

        assert adjusted2.frequency_adjustment_days == 7  # 14 - 7 = 7


@pytest.mark.asyncio
async def test_remove_from_shopping_list_with_frequency_adjustment(test_db):
    """Test removing from shopping list with frequency adjustment."""
    async with test_db() as session:
        user_id = 1

        # Create item and add to shopping list
        item = await GroceryItem.create_item(
            session,
            user_id=user_id,
            name="Coconut",
            base_frequency_days=14,
            frequency_adjustment_days=0,
        )

        await grocery_service.add_to_shopping_list(
            session, user_id=user_id, item_name="Coconut"
        )

        # Verify it's in shopping list
        shopping_entry = await ShoppingList.get_by_user_and_item(
            session, user_id, item.id
        )
        assert shopping_entry is not None

        # Remove with frequency adjustment
        await grocery_service.remove_from_shopping_list(
            session,
            user_id=user_id,
            item_name="Coconut",
            adjust_frequency=True,
            frequency_adjustment_weeks=8,
        )

        # Verify removed from shopping list
        shopping_entry2 = await ShoppingList.get_by_user_and_item(
            session, user_id, item.id
        )
        assert shopping_entry2 is None

        # Verify frequency adjusted
        await session.refresh(item)
        assert item.frequency_adjustment_days == 56  # 8 weeks * 7 days


@pytest.mark.asyncio
async def test_get_shopping_list_service(test_db):
    """Test getting shopping list entries."""
    async with test_db() as session:
        user_id = 1

        # Create items and add to shopping list
        await grocery_service.add_to_shopping_list(
            session,
            user_id=user_id,
            item_name="Milk",
            urgency="high",
            notes="For breakfast",
        )
        await grocery_service.add_to_shopping_list(
            session, user_id=user_id, item_name="Bread", urgency="normal"
        )

        # Get all entries
        entries = await ShoppingList.get_all_by_user(session, user_id)
        assert len(entries) == 2

        # Check urgency levels
        urgencies = {e.urgency for e in entries}
        assert "high" in urgencies
        assert "normal" in urgencies


@pytest.mark.asyncio
async def test_get_item_history(test_db):
    """Test getting item purchase history."""
    async with test_db() as session:
        user_id = 1
        item_name = "Eggs"

        # Record multiple purchases
        for i in range(3):
            await grocery_service.record_order(
                session,
                user_id=user_id,
                supermarket="Countdown",
                items=[{"name": item_name, "quantity": 12.0, "unit_price": 5.50}],
                order_date=date.today() - timedelta(days=i * 7),
            )

        # Get history
        history = await grocery_service.get_item_history(
            session, user_id=user_id, item_name=item_name, limit=5
        )

        assert history is not None
        assert history["item_name"] == "Eggs"
        assert len(history["recent_purchases"]) == 3
        assert history["statistics"]["total_purchases"] == 3
        assert history["base_frequency"] == 7  # Median of [7, 7]
