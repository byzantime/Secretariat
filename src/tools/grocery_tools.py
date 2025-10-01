"""Grocery shopping prediction tools for AI agent."""

from datetime import datetime
from typing import List

from pydantic import BaseModel
from pydantic import Field
from pydantic_ai import RunContext
from pydantic_ai.toolsets import FunctionToolset
from quart import current_app

from src.modules import grocery_service

# Create toolset for grocery tools
grocery_toolset = FunctionToolset()


class OrderItemInput(BaseModel):
    """Single item in a grocery order."""

    name: str = Field(
        description=(
            "Specific item name including brand, e.g., 'Anchor Milk 2L', 'Whittaker's"
            " Hazelnut Chocolate'"
        )
    )
    quantity: float = Field(description="Amount purchased")
    unit_price: float | None = Field(None, description="Optional price per unit")
    total_price: float | None = Field(None, description="Optional total for this item")


class GroceryOrderInput(BaseModel):
    """Input for recording a grocery order."""

    supermarket: str = Field(
        description="Store name, e.g., 'Tesco', 'New World', 'Countdown'"
    )
    items: List[OrderItemInput] = Field(description="List of items purchased")
    order_date: str | None = Field(
        None, description="Order date (YYYY-MM-DD), defaults to today"
    )
    total_cost: float | None = Field(None, description="Optional total order cost")


class PredictionFilters(BaseModel):
    """Filters for shopping predictions."""

    min_priority: float = Field(
        0.8, description="Minimum priority score (0-2+), default 0.8"
    )
    include_shopping_list: bool = Field(
        True, description="Include urgent shopping list items"
    )


class ShoppingListInput(BaseModel):
    """Input for adding item to shopping list."""

    item_name: str = Field(description="Item name (will find/create in grocery_items)")
    quantity: float | None = Field(
        None, description="Optional specific quantity needed"
    )
    urgency: str = Field(
        "normal", description="Urgency level: 'low', 'normal', or 'high'"
    )
    notes: str | None = Field(None, description="Optional user notes")


@grocery_toolset.tool
async def record_grocery_order(
    ctx: RunContext[dict], order_data: GroceryOrderInput
) -> str:
    """Record a grocery order to learn shopping patterns.

    Use this tool when:
    - User reports completing a grocery shop
    - Agent completes online shopping on behalf of user
    - User provides receipt/order details

    Examples:
    - "I bought groceries from Tesco: 12 eggs, 2L milk, 500g butter"
    - "Add my New World order: Whittaker's chocolate, bananas, bread"
    - "Just shopped at Countdown - got the usual plus some extras"

    The tool will:
    1. Create order record in database
    2. Find or create grocery items (with brand-specific names)
    3. Update purchase frequencies for items (after 2+ purchases)
    4. Remove purchased items from shopping list
    5. Track last purchase date for predictions

    Returns a summary of the recorded order and updated frequencies.
    """
    current_app.logger.info(
        f"🔧 TOOL CALLED: record_grocery_order for {order_data.supermarket}"
    )

    conversation = ctx.deps.get("conversation")
    if not conversation:
        return "Error: No conversation context available."

    user_id = conversation.user_id

    # Parse order date if provided
    order_date = None
    if order_data.order_date:
        try:
            order_date = datetime.strptime(order_data.order_date, "%Y-%m-%d").date()
        except ValueError:
            return (
                f"Error: Invalid date format '{order_data.order_date}'. Use YYYY-MM-DD."
            )

    # Convert Pydantic items to dicts
    items = [
        {
            "name": item.name,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "total_price": item.total_price,
        }
        for item in order_data.items
    ]

    # Get database session
    db = current_app.extensions["database"]
    async with db.session_factory() as session:
        try:
            order, updated_count = await grocery_service.record_order(
                session,
                user_id=user_id,
                supermarket=order_data.supermarket,
                items=items,
                order_date=order_date,
                total_cost=order_data.total_cost,
            )

            # Build response
            response = (
                f"✅ Recorded order from {order_data.supermarket} with"
                f" {len(items)} items."
            )

            if updated_count > 0:
                response += (
                    f" Updated frequencies for {updated_count} items (had 2+"
                    " purchases)."
                )
            elif len(items) > 0:
                response += (
                    " First purchase for these items - I'll start learning patterns"
                    " after the next purchase."
                )

            return response

        except Exception as e:
            current_app.logger.error(f"Error recording order: {e}")
            return f"Error recording order: {str(e)}"


@grocery_toolset.tool
async def get_shopping_predictions(
    ctx: RunContext[dict], filters: PredictionFilters = PredictionFilters()
) -> str:
    """Generate shopping predictions based on purchase patterns.

    Use this tool when:
    - User asks "what should I buy?", "what do I need?", "shopping list?"
    - User wants to know what groceries to order
    - User is planning a shopping trip

    The tool will:
    1. Calculate priority scores based on days since last purchase vs expected frequency
    2. Include items from urgent shopping list (with boosted priority)
    3. Return items sorted by priority

    Priority score explained:
    - 1.0 = exactly at expected purchase interval
    - >1.0 = overdue (higher = more overdue)
    - <1.0 = not yet due (with 0.8 threshold by default)

    Returns formatted predictions with reasoning.
    """
    current_app.logger.info("🔧 TOOL CALLED: get_shopping_predictions")

    conversation = ctx.deps.get("conversation")
    if not conversation:
        return "Error: No conversation context available."

    user_id = conversation.user_id

    db = current_app.extensions["database"]
    async with db.session_factory() as session:
        try:
            predictions = await grocery_service.calculate_predictions(
                session,
                user_id=user_id,
                min_priority=filters.min_priority,
                include_shopping_list=filters.include_shopping_list,
            )

            if not predictions:
                return (
                    "📋 No shopping predictions yet. I need at least 2 purchases of"
                    " each item to start predicting."
                )

            # Format predictions
            lines = ["📋 Shopping Predictions:\n"]

            for i, pred in enumerate(predictions, 1):
                # Priority emoji
                priority = pred["priority_score"]
                if priority >= 1.5:
                    priority_emoji = "🔴"
                elif priority >= 1.2:
                    priority_emoji = "🟠"
                elif priority >= 1.0:
                    priority_emoji = "🟡"
                else:
                    priority_emoji = ""

                # Item name with priority
                lines.append(
                    f"{i}. **{pred['item_name']}** (Priority: {priority})"
                    f" {priority_emoji}"
                )

                # Quantity
                if pred["quantity"] and pred["unit_type"]:
                    lines.append(
                        f"   - Quantity: {pred['quantity']} {pred['unit_type']}"
                    )
                elif pred["quantity"]:
                    lines.append(f"   - Quantity: {pred['quantity']}")

                # Reason
                lines.append(f"   - {pred['reason']}")

                # Urgent flag
                if pred["is_urgent"]:
                    urgency_emoji = {"high": "‼️", "normal": "⚠️", "low": "ℹ️"}.get(
                        pred["urgency_level"], "⚠️"
                    )
                    lines.append(f"   - {urgency_emoji} URGENT (on shopping list)")

                lines.append("")  # Blank line between items

            return "\n".join(lines).strip()

        except Exception as e:
            current_app.logger.error(f"Error getting predictions: {e}")
            return f"Error getting predictions: {str(e)}"


@grocery_toolset.tool
async def add_to_shopping_list(
    ctx: RunContext[dict], item_data: ShoppingListInput
) -> str:
    """Add urgent items or plan-ahead items to shopping list.

    Use this tool when:
    - User says "add X to shopping list"
    - User is planning ahead: "I need milk for the party"
    - User marks something as urgent: "I'm out of eggs"

    The tool will:
    1. Find or create the grocery item
    2. Add to shopping list with urgency level
    3. NOT modify frequency patterns (this is for planning/urgency only)

    Note: Items on shopping list get boosted priority in predictions.

    Returns confirmation message.
    """
    current_app.logger.info(
        f"🔧 TOOL CALLED: add_to_shopping_list for {item_data.item_name}"
    )

    conversation = ctx.deps.get("conversation")
    if not conversation:
        return "Error: No conversation context available."

    user_id = conversation.user_id

    # Validate urgency
    valid_urgency = {"low", "normal", "high"}
    if item_data.urgency not in valid_urgency:
        return (
            f"Error: Invalid urgency '{item_data.urgency}'. Must be one of:"
            f" {', '.join(valid_urgency)}"
        )

    db = current_app.extensions["database"]
    async with db.session_factory() as session:
        try:
            entry = await grocery_service.add_to_shopping_list(
                session,
                user_id=user_id,
                item_name=item_data.item_name,
                quantity=item_data.quantity,
                urgency=item_data.urgency,
                notes=item_data.notes,
            )

            # Get item name (capitalized)
            await session.refresh(entry.item)
            item_name = entry.item.name

            urgency_text = (
                f" with {item_data.urgency} urgency"
                if item_data.urgency != "normal"
                else ""
            )
            return f"✅ Added {item_name} to shopping list{urgency_text}"

        except Exception as e:
            current_app.logger.error(f"Error adding to shopping list: {e}")
            return f"Error adding to shopping list: {str(e)}"


@grocery_toolset.tool
async def remove_from_shopping_list(
    ctx: RunContext[dict],
    item_name: str,
    adjust_frequency: bool = False,
    frequency_adjustment_weeks: int = 2,
) -> str:
    """Remove item from shopping list, optionally adjust frequency.

    Use this tool when:
    - User says "remove X from shopping list"
    - User says "I don't need X for a while" (use adjust_frequency=True)
    - User wants to delay predictions: "Don't suggest coconut for a few weeks"

    Parameters:
    - item_name: Name of item to remove (case-insensitive)
    - adjust_frequency: If True, push next prediction out by N weeks
    - frequency_adjustment_weeks: How many weeks to delay (default 2)

    The tool will:
    1. Remove from shopping list
    2. Optionally adjust frequency to delay future predictions

    Example uses:
    - "Remove milk from list" → adjust_frequency=False
    - "I don't need coconut for 8 weeks" → adjust_frequency=True, weeks=8

    Returns confirmation with frequency change if applicable.
    """
    current_app.logger.info(
        f"🔧 TOOL CALLED: remove_from_shopping_list for {item_name}"
    )

    conversation = ctx.deps.get("conversation")
    if not conversation:
        return "Error: No conversation context available."

    user_id = conversation.user_id

    db = current_app.extensions["database"]
    async with db.session_factory() as session:
        try:
            message = await grocery_service.remove_from_shopping_list(
                session,
                user_id=user_id,
                item_name=item_name,
                adjust_frequency=adjust_frequency,
                frequency_adjustment_weeks=frequency_adjustment_weeks,
            )

            if not message:
                return f"Item '{item_name}' not found."

            return f"✅ {message}"

        except Exception as e:
            current_app.logger.error(f"Error removing from shopping list: {e}")
            return f"Error removing from shopping list: {str(e)}"


@grocery_toolset.tool
async def adjust_item_frequency(
    ctx: RunContext[dict], item_name: str, adjustment_weeks: int
) -> str:
    """Adjust purchase frequency based on user feedback.

    Use this tool when:
    - User says "I need X more often" (use negative weeks)
    - User says "Buy Y less frequently" (use positive weeks)
    - User gives explicit frequency feedback

    Parameters:
    - item_name: Name of item (case-insensitive)
    - adjustment_weeks: Weeks to adjust
      * Positive = less often (push predictions out)
      * Negative = more often (bring predictions forward)

    Examples:
    - "I need milk more often" → adjustment_weeks=-1
    - "Buy bananas less frequently" → adjustment_weeks=2
    - "I only need chocolate every 3 weeks" → adjustment_weeks=3 (if current is weekly)

    The adjustment is cumulative with previous adjustments.

    Returns confirmation of frequency change.
    """
    current_app.logger.info(
        f"🔧 TOOL CALLED: adjust_item_frequency for {item_name} by"
        f" {adjustment_weeks} weeks"
    )

    conversation = ctx.deps.get("conversation")
    if not conversation:
        return "Error: No conversation context available."

    user_id = conversation.user_id

    db = current_app.extensions["database"]
    async with db.session_factory() as session:
        try:
            item = await grocery_service.adjust_item_frequency(
                session,
                user_id=user_id,
                item_name=item_name,
                adjustment_weeks=adjustment_weeks,
            )

            if not item:
                return f"Item '{item_name}' not found."

            direction = "less often" if adjustment_weeks > 0 else "more often"
            weeks_text = (
                f"{abs(adjustment_weeks)} week{'s' if abs(adjustment_weeks) != 1 else ''}"
            )

            return (
                f"✅ Adjusted {item.name} frequency: {direction} by {weeks_text}. "
                "I'll suggest it accordingly in future predictions."
            )

        except Exception as e:
            current_app.logger.error(f"Error adjusting frequency: {e}")
            return f"Error adjusting frequency: {str(e)}"


@grocery_toolset.tool
async def get_shopping_list(ctx: RunContext[dict]) -> str:
    """View current shopping list with all items marked as needed.

    Use this tool when:
    - User asks "what's on my shopping list?"
    - User wants to see urgent items
    - User asks about items they've marked to buy

    Returns formatted list of all shopping list items with urgency levels.
    """
    current_app.logger.info("🔧 TOOL CALLED: get_shopping_list")

    conversation = ctx.deps.get("conversation")
    if not conversation:
        return "Error: No conversation context available."

    user_id = conversation.user_id

    db = current_app.extensions["database"]
    async with db.session_factory() as session:
        try:
            # Get all shopping list entries for user
            from src.models.grocery import ShoppingList

            entries = await ShoppingList.get_all_by_user(session, user_id)

            if not entries:
                return "📋 Your shopping list is empty."

            # Format response
            lines = ["📋 Shopping List:\n"]

            for i, entry in enumerate(entries, 1):
                # Urgency emoji
                urgency_emoji = {"high": "‼️", "normal": "⚠️", "low": "ℹ️"}.get(
                    entry.urgency, "⚠️"
                )

                # Load item details
                await session.refresh(entry.item)
                item_name = entry.item.name

                lines.append(f"{i}. **{item_name}** {urgency_emoji}")

                # Quantity if specified
                if entry.quantity_needed:
                    if entry.item.unit_type:
                        lines.append(
                            "   - Quantity:"
                            f" {entry.quantity_needed} {entry.item.unit_type}"
                        )
                    else:
                        lines.append(f"   - Quantity: {entry.quantity_needed}")

                # Notes if present
                if entry.notes:
                    lines.append(f"   - Note: {entry.notes}")

                lines.append("")  # Blank line

            return "\n".join(lines).strip()

        except Exception as e:
            current_app.logger.error(f"Error getting shopping list: {e}")
            return f"Error getting shopping list: {str(e)}"


@grocery_toolset.tool
async def get_item_history(
    ctx: RunContext[dict], item_name: str, limit: int = 10
) -> str:
    """Show purchase history and statistics for an item.

    Use this tool when:
    - User asks "how often do I buy X?"
    - User wants to see purchase history
    - User questions frequency predictions

    The tool returns:
    - Frequency settings (base learned + user adjustments)
    - Recent purchase history with dates and quantities
    - Statistics (average interval, quantities)

    Returns formatted history and statistics.
    """
    current_app.logger.info(f"🔧 TOOL CALLED: get_item_history for {item_name}")

    conversation = ctx.deps.get("conversation")
    if not conversation:
        return "Error: No conversation context available."

    user_id = conversation.user_id

    db = current_app.extensions["database"]
    async with db.session_factory() as session:
        try:
            history = await grocery_service.get_item_history(
                session, user_id=user_id, item_name=item_name, limit=limit
            )

            if not history:
                return f"No purchase history found for '{item_name}'."

            # Format response
            lines = [f"📊 Purchase History: {history['item_name']}\n"]

            # Frequency settings
            lines.append("Frequency Settings:")
            if history["base_frequency"]:
                lines.append(
                    f"- Base frequency: {history['base_frequency']} days (learned)"
                )
            else:
                lines.append("- Base frequency: Not yet calculated (need 2+ purchases)")

            lines.append(f"- User adjustment: {history['user_adjustment']:+d} days")
            lines.append(
                f"- Effective frequency: {history['effective_frequency']} days\n"
            )

            # Recent purchases
            if history["recent_purchases"]:
                lines.append(
                    f"Recent Purchases (last {len(history['recent_purchases'])}):"
                )
                for i, purchase in enumerate(history["recent_purchases"], 1):
                    price_text = ""
                    if purchase["unit_price"]:
                        price_text = f" @ ${purchase['unit_price']:.2f}"

                    lines.append(
                        f"{i}. {purchase['date']} -"
                        f" {purchase['quantity']}{price_text} ({purchase['supermarket']})"
                    )
                lines.append("")

            # Statistics
            stats = history["statistics"]
            lines.append("Statistics:")
            if stats["avg_interval_days"]:
                lines.append(
                    f"- Average interval: {stats['avg_interval_days']:.1f} days"
                )
            if stats["avg_quantity"]:
                lines.append(f"- Average quantity: {stats['avg_quantity']:.1f}")
            if stats["common_quantity"]:
                lines.append(f"- Most common quantity: {stats['common_quantity']}")
            lines.append(f"- Total purchases: {stats['total_purchases']}")

            return "\n".join(lines)

        except Exception as e:
            current_app.logger.error(f"Error getting item history: {e}")
            return f"Error getting item history: {str(e)}"
