"""Grocery shopping prediction service with frequency-based learning."""

import logging
from datetime import date
from statistics import StatisticsError
from statistics import median
from statistics import mode
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from src.models.grocery import GroceryItem
from src.models.grocery import GroceryOrder
from src.models.grocery import OrderItem
from src.models.grocery import ShoppingList

logger = logging.getLogger(__name__)


async def find_or_create_item(
    session: AsyncSession, user_id: int, name: str
) -> GroceryItem:
    """Find existing grocery item by name (case-insensitive) or create new one.

    Args:
        session: Database session
        user_id: User ID
        name: Item name (case-insensitive)

    Returns:
        GroceryItem instance
    """
    # Try to find existing item (case-insensitive)
    item = await GroceryItem.get_by_user_and_name(session, user_id, name)

    if not item:
        # Create new item with normalized name (capitalize each word)
        normalized_name = " ".join(word.capitalize() for word in name.split())
        item = await GroceryItem.create_item(
            session, user_id=user_id, name=normalized_name
        )
        logger.info(f"Created new grocery item: {normalized_name} for user {user_id}")

    return item


async def update_item_frequency(session: AsyncSession, item_id: int) -> None:
    """Recalculate base_frequency_days and typical_quantity from purchase history.

    Args:
        session: Database session
        item_id: Grocery item ID
    """
    item = await GroceryItem.get_by_id(session, item_id)
    if not item:
        logger.warning(f"Item {item_id} not found for frequency update")
        return

    # Get recent purchases (order_items with order dates)
    query = (
        select(OrderItem, GroceryOrder.order_date)
        .join(GroceryOrder)
        .where(OrderItem.item_id == item_id)
        .order_by(GroceryOrder.order_date.desc())
        .limit(10)
    )
    result = await session.execute(query)
    purchases = [(order_item, order_date) for order_item, order_date in result.all()]

    if len(purchases) < 2:
        logger.debug(
            f"Not enough purchases ({len(purchases)}) for frequency calculation for"
            f" item {item_id}"
        )
        return

    # Calculate intervals between consecutive purchases
    intervals = []
    for i in range(len(purchases) - 1):
        _, date1 = purchases[i]
        _, date2 = purchases[i + 1]
        days_diff = (date1 - date2).days
        if days_diff > 0:  # Only include positive intervals
            intervals.append(days_diff)

    if not intervals:
        return

    # Use median for robust frequency (less affected by outliers)
    base_frequency = int(median(intervals))

    # Calculate typical quantity (most common or median)
    quantities = [order_item.quantity for order_item, _ in purchases]
    try:
        # Try mode first (most common)
        typical_qty = mode(quantities)
    except StatisticsError:
        # If no mode, use median
        typical_qty = median(quantities)

    # Update item
    await item.update(
        session,
        base_frequency_days=base_frequency,
        typical_quantity=typical_qty,
    )

    logger.info(
        f"Updated item {item.name}: frequency={base_frequency} days, qty={typical_qty}"
    )


async def record_order(
    session: AsyncSession,
    user_id: int,
    supermarket: str,
    items: List[Dict],
    order_date: Optional[date] = None,
    total_cost: Optional[float] = None,
) -> Tuple[GroceryOrder, int]:
    """Record a grocery order and update item frequencies.

    Args:
        session: Database session
        user_id: User ID
        supermarket: Supermarket name
        items: List of dicts with keys: name, quantity, unit_price (optional), total_price (optional)
        order_date: Order date (defaults to today)
        total_cost: Total order cost (optional)

    Returns:
        Tuple of (GroceryOrder, number of items with updated frequencies)
    """
    if order_date is None:
        order_date = date.today()

    # Create order
    order = await GroceryOrder.create_order(
        session,
        user_id=user_id,
        supermarket=supermarket,
        order_date=order_date,
        total_cost=total_cost,
    )

    updated_frequencies = 0

    # Process each item
    for item_data in items:
        # Find or create grocery item
        grocery_item = await find_or_create_item(session, user_id, item_data["name"])

        # Create order item
        await OrderItem.create_order_item(
            session,
            order_id=order.id,
            item_id=grocery_item.id,
            quantity=item_data["quantity"],
            unit_price=item_data.get("unit_price"),
            total_price=item_data.get("total_price"),
        )

        # Update last purchased date
        await grocery_item.update(session, last_purchased_date=order_date)

        # Update frequency if item has >= 2 purchases
        await update_item_frequency(session, grocery_item.id)

        # Check if frequency was set (meaning >= 2 purchases)
        await session.refresh(grocery_item)
        if grocery_item.base_frequency_days is not None:
            updated_frequencies += 1

        # Remove from shopping list if present
        shopping_entry = await ShoppingList.get_by_user_and_item(
            session, user_id, grocery_item.id
        )
        if shopping_entry:
            await shopping_entry.delete(session)
            logger.debug(f"Removed {grocery_item.name} from shopping list")

    logger.info(
        f"Recorded order from {supermarket} with {len(items)} items, "
        f"updated frequencies for {updated_frequencies} items"
    )

    return order, updated_frequencies


async def calculate_predictions(
    session: AsyncSession,
    user_id: int,
    min_priority: float = 0.5,
    include_shopping_list: bool = True,
) -> List[Dict]:
    """Generate shopping predictions based on purchase frequency.

    Args:
        session: Database session
        user_id: User ID
        min_priority: Minimum priority score threshold (0-1 scale, default 0.5)
        include_shopping_list: Include urgent shopping list items (default True)

    Returns:
        List of prediction dicts with keys:
            - item_name
            - quantity
            - unit_type
            - priority_score: 0-1 (0=just purchased, 1=entirely used up)
            - days_since_last_purchase
            - expected_frequency_days
            - is_urgent
            - urgency_level
            - reason
    """
    today = date.today()
    predictions = []

    # Get all grocery items for user
    items = await GroceryItem.get_all_by_user(session, user_id)

    # Get shopping list items for fast lookup
    shopping_list_items = {}
    if include_shopping_list:
        shopping_entries = await ShoppingList.get_all_by_user(session, user_id)
        shopping_list_items = {
            entry.item_id: entry.urgency for entry in shopping_entries
        }

    for item in items:
        # Calculate effective frequency
        effective_frequency = (item.base_frequency_days or 0) + (
            item.frequency_adjustment_days or 0
        )

        # Skip items with no frequency data yet (need >= 2 purchases)
        if not item.base_frequency_days or effective_frequency <= 0:
            continue

        # Skip items never purchased
        if not item.last_purchased_date:
            continue

        # Calculate days since last purchase
        days_since = (today - item.last_purchased_date).days

        # Calculate priority score (0-1 scale: 0=just purchased, 1=entirely used up)
        priority_score = min(days_since / effective_frequency, 1.0)

        # Check if on shopping list
        is_urgent = item.id in shopping_list_items
        urgency_level = shopping_list_items.get(item.id, "normal")

        # Set to maximum confidence if on shopping list (user already decided to purchase)
        if is_urgent:
            priority_score = 1.0

        # Apply confidence threshold (default 0.5)
        if priority_score >= min_priority:
            predictions.append({
                "item_name": item.name,
                "quantity": item.typical_quantity,
                "unit_type": item.unit_type,
                "priority_score": round(priority_score, 2),
                "days_since_last_purchase": days_since,
                "expected_frequency_days": effective_frequency,
                "is_urgent": is_urgent,
                "urgency_level": urgency_level,
                "reason": (
                    f"Usually purchased every {effective_frequency} days, last bought"
                    f" {days_since} days ago"
                ),
            })

    # Sort by priority descending
    predictions.sort(key=lambda x: x["priority_score"], reverse=True)

    logger.info(f"Generated {len(predictions)} predictions for user {user_id}")
    return predictions


async def adjust_item_frequency(
    session: AsyncSession, user_id: int, item_name: str, adjustment_weeks: int
) -> Optional[GroceryItem]:
    """Adjust item frequency by user feedback.

    Args:
        session: Database session
        user_id: User ID
        item_name: Item name (case-insensitive)
        adjustment_weeks: Weeks to adjust (positive = less often, negative = more often)

    Returns:
        Updated GroceryItem or None if not found
    """
    item = await GroceryItem.get_by_user_and_name(session, user_id, item_name)
    if not item:
        logger.warning(f"Item '{item_name}' not found for user {user_id}")
        return None

    adjustment_days = adjustment_weeks * 7
    new_adjustment = (item.frequency_adjustment_days or 0) + adjustment_days

    await item.update(session, frequency_adjustment_days=new_adjustment)

    logger.info(
        f"Adjusted frequency for {item.name}: {adjustment_weeks} weeks "
        f"(total adjustment: {new_adjustment} days)"
    )

    return item


async def add_to_shopping_list(
    session: AsyncSession,
    user_id: int,
    item_name: str,
    quantity: Optional[float] = None,
    urgency: str = "normal",
    notes: Optional[str] = None,
) -> ShoppingList:
    """Add or update item in shopping list.

    Args:
        session: Database session
        user_id: User ID
        item_name: Item name (will find or create)
        quantity: Quantity needed (optional)
        urgency: Urgency level ('low', 'normal', 'high')
        notes: User notes (optional)

    Returns:
        ShoppingList entry
    """
    # Find or create grocery item
    item = await find_or_create_item(session, user_id, item_name)

    # Check if already in shopping list
    existing = await ShoppingList.get_by_user_and_item(session, user_id, item.id)

    if existing:
        # Update existing entry
        await existing.update(
            session, quantity_needed=quantity, urgency=urgency, notes=notes
        )
        logger.info(f"Updated {item.name} in shopping list (urgency: {urgency})")
        return existing
    else:
        # Create new entry
        entry = await ShoppingList.create_entry(
            session,
            user_id=user_id,
            item_id=item.id,
            quantity_needed=quantity,
            urgency=urgency,
            notes=notes,
        )
        logger.info(f"Added {item.name} to shopping list (urgency: {urgency})")
        return entry


async def remove_from_shopping_list(
    session: AsyncSession,
    user_id: int,
    item_name: str,
    adjust_frequency: bool = False,
    frequency_adjustment_weeks: int = 2,
) -> Optional[str]:
    """Remove item from shopping list, optionally adjust frequency.

    Args:
        session: Database session
        user_id: User ID
        item_name: Item name (case-insensitive)
        adjust_frequency: Whether to adjust frequency (default False)
        frequency_adjustment_weeks: Weeks to push out (default 2)

    Returns:
        Success message or None if not found
    """
    item = await GroceryItem.get_by_user_and_name(session, user_id, item_name)
    if not item:
        logger.warning(f"Item '{item_name}' not found for user {user_id}")
        return None

    # Remove from shopping list
    shopping_entry = await ShoppingList.get_by_user_and_item(session, user_id, item.id)
    if shopping_entry:
        await shopping_entry.delete(session)

    message = f"Removed {item.name} from shopping list"

    # Optionally adjust frequency
    if adjust_frequency:
        adjustment_days = frequency_adjustment_weeks * 7
        new_adjustment = (item.frequency_adjustment_days or 0) + adjustment_days
        await item.update(session, frequency_adjustment_days=new_adjustment)
        message += f" and adjusted frequency by +{frequency_adjustment_weeks} weeks"

    logger.info(message)
    return message


async def get_item_history(
    session: AsyncSession, user_id: int, item_name: str, limit: int = 10
) -> Optional[Dict]:
    """Get purchase history and statistics for an item.

    Args:
        session: Database session
        user_id: User ID
        item_name: Item name (case-insensitive)
        limit: Max number of recent purchases to return (default 10)

    Returns:
        Dict with history data or None if not found
    """
    item = await GroceryItem.get_by_user_and_name(session, user_id, item_name)
    if not item:
        return None

    # Get recent order items with order details
    query = (
        select(OrderItem, GroceryOrder)
        .join(GroceryOrder)
        .where(OrderItem.item_id == item.id)
        .order_by(GroceryOrder.order_date.desc())
        .limit(limit)
    )
    result = await session.execute(query)
    purchases = [(order_item, order) for order_item, order in result.all()]

    # Calculate statistics
    if purchases:
        quantities = [oi.quantity for oi, _ in purchases]
        intervals = []
        for i in range(len(purchases) - 1):
            _, order1 = purchases[i]
            _, order2 = purchases[i + 1]
            days_diff = (order1.order_date - order2.order_date).days
            if days_diff > 0:
                intervals.append(days_diff)

        avg_interval = median(intervals) if intervals else None
        avg_quantity = median(quantities) if quantities else None
        try:
            common_quantity = mode(quantities)
        except StatisticsError:
            common_quantity = avg_quantity
    else:
        avg_interval = None
        avg_quantity = None
        common_quantity = None

    return {
        "item_name": item.name,
        "base_frequency": item.base_frequency_days,
        "user_adjustment": item.frequency_adjustment_days or 0,
        "effective_frequency": (
            (item.base_frequency_days or 0) + (item.frequency_adjustment_days or 0)
        ),
        "recent_purchases": [
            {
                "date": order.order_date,
                "quantity": order_item.quantity,
                "unit_price": order_item.unit_price,
                "supermarket": order.supermarket,
            }
            for order_item, order in purchases
        ],
        "statistics": {
            "avg_interval_days": avg_interval,
            "avg_quantity": avg_quantity,
            "common_quantity": common_quantity,
            "total_purchases": len(purchases),
        },
    }
