"""Telegram blueprint for webhook handling."""

import asyncio

from quart import Blueprint
from quart import current_app
from quart import request

try:
    from telegram import Update

    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False

telegram_bp = Blueprint("telegram", __name__, url_prefix="/telegram")


@telegram_bp.route("/webhook", methods=["POST"])
async def telegram_webhook():
    """Handle incoming Telegram webhook updates."""
    if not TELEGRAM_AVAILABLE:
        current_app.logger.error("Telegram not available but webhook called")
        return "Telegram not available", 500

    try:
        # Get the update data
        update_data = await request.get_json()
        if not update_data:
            current_app.logger.warning("Empty webhook payload received")
            return "Bad Request", 400

        # Parse the update
        update = Update.de_json(update_data, bot=None)
        if not update:
            current_app.logger.warning("Invalid update format")
            return "Bad Request", 400

        # Get the Telegram channel from communication service
        communication_service = current_app.extensions["communication_service"]
        telegram_channel = communication_service.channels.get("telegram")
        if not telegram_channel:
            current_app.logger.error("Telegram channel not registered")
            return "Internal Server Error", 500

        # Process the update
        asyncio.create_task(_process_telegram_update(telegram_channel, update))

        return "OK", 200

    except Exception as e:
        current_app.logger.error(f"Telegram webhook error: {e}", exc_info=True)
        return "Internal Server Error", 500


async def _process_telegram_update(telegram_channel, update: "Update"):
    """Process a Telegram update."""
    # Handle text messages
    if update.message and update.message.text:
        chat_id = update.message.chat.id
        user_id = update.message.from_user.id if update.message.from_user else chat_id
        text = update.message.text
        user_name = (
            update.message.from_user.first_name
            if update.message.from_user
            else "Unknown"
        )

        current_app.logger.info(
            f"Received message from {user_name} ({user_id}): {text}"
        )

        # Check authorization at webhook level (defense in depth)
        if not telegram_channel.is_user_authorized(user_id):
            current_app.logger.warning(
                f"Unauthorized user {user_id} blocked at webhook level"
            )
            # Send rejection message directly via bot if possible
            if telegram_channel.bot:
                try:
                    await telegram_channel.bot.send_message(
                        chat_id=chat_id,
                        text=(
                            "You are not authorised.\n\nThis is *Secretariat* - an AI "
                            "personal assistant.\nCreate your own: "
                            "https://github.com/byzantime/Secretariat"
                        ),
                        parse_mode="Markdown",
                    )
                except Exception as e:
                    current_app.logger.error(f"Failed to send rejection message: {e}")
            return

        # Process the message through the telegram channel
        await telegram_channel.process_incoming_message(chat_id, text)

    # Handle other update types (can be extended later)
    elif update.callback_query:
        # Handle callback queries from inline keyboards
        current_app.logger.info("Received callback query - not implemented yet")

    elif update.edited_message:
        # Handle edited messages
        current_app.logger.info("Received edited message - not implemented yet")

    else:
        current_app.logger.debug(f"Unhandled update type: {update}")


@telegram_bp.route("/webhook_info", methods=["GET"])
async def get_webhook_info():
    """Get current webhook information."""
    if not TELEGRAM_AVAILABLE:
        return {"error": "Telegram not available"}, 500

    # Get the communication service
    communication_service = current_app.extensions["communication_service"]
    telegram_channel = communication_service.channels.get("telegram")
    if not telegram_channel:
        return {"error": "Telegram channel not registered"}, 500

    try:
        webhook_info = await telegram_channel.bot.get_webhook_info()
        return {
            "url": webhook_info.url,
            "has_custom_certificate": webhook_info.has_custom_certificate,
            "pending_update_count": webhook_info.pending_update_count,
            "last_error_date": (
                webhook_info.last_error_date.isoformat()
                if webhook_info.last_error_date
                else None
            ),
            "last_error_message": webhook_info.last_error_message,
            "max_connections": webhook_info.max_connections,
            "allowed_updates": webhook_info.allowed_updates,
        }, 200

    except Exception as e:
        current_app.logger.error(f"Error getting webhook info: {e}")
        return {"error": str(e)}, 500
