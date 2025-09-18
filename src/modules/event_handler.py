"""EventHandler is the hub for all inter-service communication."""

import asyncio
import traceback
from collections import defaultdict
from typing import Optional

from quart import current_app


class EventHandler:
    """Manages both inter-service and WebSocket event handling."""

    def __init__(self, app=None):
        """Initialise the EventHandler.

        Args:
            app (Quart, optional): The Quart application instance.
        """
        # Store subscribers as: {event: [(callback, org), ...]}
        # org is None for global listeners, string for org-specific listeners
        self.subscribers = defaultdict(list)
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialise the EventHandler with the Quart app.

        Args:
            app (Quart): The Quart application instance.
        """
        app.extensions["event_handler"] = self

    def on(self, event: str, callback, org: Optional[str] = None):
        """Subscribe to an inter-service event.

        Args:
            event: Event name to subscribe to
            callback: Function to call when event is emitted
            org: Optional organization name to filter events by
        """
        self.subscribers[event].append((callback, org))

    async def emit_to_services(
        self,
        event: str,
        data: Optional[dict] = None,
        org: Optional[str] = None,
    ):
        """Emit event to inter-service subscribers.

        Args:
            event: Event name to emit
            data: Optional event data
            org: Organization name for the event (used for filtering subscribers)
        """
        data = data or {}
        tasks = []

        for callback, subscriber_org in self.subscribers[event]:
            # Only call callback if:
            # 1. Subscriber has no org filter (subscriber_org is None), OR
            # 2. Event has org and subscriber is listening for that org
            if subscriber_org is None or subscriber_org == org:
                try:
                    tasks.append(asyncio.create_task(callback(data)))
                except Exception as e:
                    # Get full traceback
                    tb = traceback.format_exc()
                    error_msg = (
                        f"Error in event {event} callback: {str(e)}\n"
                        f"Data: {data}\n"
                        f"Traceback:\n{tb}"
                    )
                    current_app.logger.error(error_msg)
                    # Re-raise if it's a critical error that should stop processing
                    if isinstance(e, (KeyboardInterrupt, SystemExit)):
                        raise

        if tasks:
            await asyncio.gather(*tasks)
