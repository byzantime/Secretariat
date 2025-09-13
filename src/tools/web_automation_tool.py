"""Web automation tool for browser-based tasks using LLM guidance."""

import asyncio
import json
from typing import Dict

from quart import current_app

from src.modules.tool_manager import Tool


class WebAutomationTool(Tool):
    """Tool for automated web browsing with LLM guidance."""

    @property
    def name(self) -> str:
        return "web_automation"

    @property
    def description(self) -> str:
        return """Automate web browsing tasks using an AI-controlled browser. Can perform tasks like online shopping,
        form filling, information gathering, and other web-based activities. Provides visual feedback through screenshots
        and can request human intervention when needed (e.g., for captchas or complex interactions)."""

    @property
    def input_schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": (
                        "Description of the web automation task to perform (e.g., 'Buy"
                        " groceries: milk, bread, eggs from Countdown website')"
                    ),
                },
                "starting_url": {
                    "type": "string",
                    "description": (
                        "Optional starting URL. If not provided, the LLM will determine"
                        " where to start based on the task."
                    ),
                },
            },
            "required": ["task"],
        }

    async def execute(self, input_data: Dict, conversation) -> str:
        """Execute the web automation task."""
        task = input_data.get("task")
        starting_url = input_data.get("starting_url")

        current_app.logger.info(f"Starting web automation task: {task}")

        # Get browser service
        browser = current_app.extensions["browser"]
        if not browser:
            return "Browser service not available"

        # Start automation session
        automation_session = WebAutomationSession(
            browser, conversation, task, starting_url
        )
        result = await automation_session.execute()

        return result


class WebAutomationSession:
    """Manages a single web automation session."""

    def __init__(
        self, browser_service, conversation, task: str, starting_url: str = None
    ):
        self.browser = browser_service
        self.conversation = conversation
        self.task = task
        self.starting_url = starting_url
        self.session_id = f"automation_{conversation.id}"
        self.max_steps = 50  # Prevent infinite loops
        self.current_step = 0
        self.intervention_requested = False

    async def execute(self) -> str:
        """Execute the automation task."""
        # Start browser session
        success = await self.browser.start_session(headless=True)
        if not success:
            return "Failed to start browser session"

        await self._emit_status("Starting web automation session...")

        try:
            # Begin automation loop
            result = await self._automation_loop()
            return result
        finally:
            # Always cleanup browser session
            await self.browser.close_session()

    async def _automation_loop(self) -> str:
        """Main automation loop with LLM decision making."""

        # Initial step - navigate to starting URL or analyze task
        if self.starting_url:
            await self._emit_status(f"Navigating to {self.starting_url}...")
            success = await self.browser.navigate_to(self.starting_url)
            if not success:
                return f"Failed to navigate to {self.starting_url}"
        else:
            # Let LLM decide where to start based on task
            await self._emit_status("Analyzing task to determine starting website...")
            starting_url = await self._llm_determine_starting_url()
            if starting_url:
                await self._emit_status(f"Navigating to {starting_url}...")
                success = await self.browser.navigate_to(starting_url)
                if not success:
                    return f"Failed to navigate to {starting_url}"
            else:
                return "Could not determine starting URL for the task"

        # Take initial screenshot and send to user
        await self._take_and_emit_screenshot()

        # Main automation loop
        while self.current_step < self.max_steps:
            self.current_step += 1

            # Get current page state
            page_info = await self.browser.get_page_info()
            screenshot = await self.browser.get_screenshot_base64()

            # Ask LLM for next action
            await self._emit_status(
                f"Step {self.current_step}: Analyzing page and planning next action..."
            )

            action = await self._llm_get_next_action(page_info, screenshot)

            if not action:
                return "LLM failed to determine next action"

            # Execute the action
            result = await self._execute_action(action)

            if result.get("completed"):
                await self._emit_status("Task completed successfully!")
                return result.get("message", "Web automation task completed")

            if result.get("intervention_needed"):
                # Request human intervention
                intervention_result = await self._request_intervention(
                    result.get("message")
                )
                if intervention_result == "abort":
                    return "Task aborted by user"
                # Continue with automation after intervention

            if result.get("error"):
                return f"Automation failed: {result.get('message')}"

            # Small delay between actions
            await asyncio.sleep(2)

        return f"Automation stopped after {self.max_steps} steps without completion"

    async def _llm_determine_starting_url(self) -> str:
        """Use LLM to determine starting URL based on task."""
        system_prompt = """You are helping determine the best starting website for an automation task.
        Based on the task description, provide the most appropriate starting URL.

        For shopping tasks, consider popular grocery/retail websites.
        For booking tasks, consider relevant booking platforms.

        Respond with just the URL, nothing else."""

        messages = [{
            "role": "user",
            "content": f"Task: {self.task}\n\nWhat website should I start with?",
        }]

        llm_service = current_app.extensions["llm"]
        response = await llm_service._call_llm(
            system_prompt=system_prompt,
            messages=messages,
            max_tokens=100,
            conversation_id=self.conversation.id,
        )
        current_app.logger.info(f"LLM response: {response}")
        # Extract URL from response (basic validation)
        response = response.strip()
        if response.startswith(("http://", "https://")):
            return response
        elif response.startswith("www."):
            return f"https://{response}"
        else:
            # Try to construct URL
            return f"https://{response}" if "." in response else None

    async def _llm_get_next_action(self, page_info: Dict, screenshot: str) -> Dict:
        """Get next action from LLM based on current page state."""
        system_prompt = """You are controlling a web browser to complete automation tasks.

        Based on the current page information and screenshot, determine the next action to take.

        Available actions:
        - click_text: Click on text/button (provide text to find)
        - type_field: Type in input field (provide field name/id and text)
        - navigate: Go to a new URL
        - wait: Wait for page to load
        - intervention: Request human help (for captchas, complex forms, etc.)
        - completed: Task is finished

        Respond with JSON containing:
        {"action": "action_name", "params": {...}, "reasoning": "why this action"}"""

        page_summary = f"""
        Current URL: {page_info.get('url', 'Unknown')}
        Page Title: {page_info.get('title', 'Unknown')}

        Task: {self.task}
        Current Step: {self.current_step}
        """

        messages = [{
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": page_summary + "\n\nWhat should be the next action?",
                },
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": screenshot,
                    },
                },
            ],
        }]

        llm_service = current_app.extensions["llm"]
        response = await llm_service._call_llm(
            system_prompt=system_prompt,
            messages=messages,
            max_tokens=300,
            conversation_id=self.conversation.id,
        )

        # Try to parse JSON response - let JSON errors bubble up
        action_data = json.loads(response)
        current_app.logger.info(f"LLM suggested action: {action_data}")
        return action_data

    async def _execute_action(self, action: Dict) -> Dict:
        """Execute the specified action."""
        action_type = action.get("action")
        params = action.get("params", {})
        reasoning = action.get("reasoning", "")

        await self._emit_status(f"Executing: {action_type} - {reasoning}")

        if action_type == "click_text":
            text = params.get("text")
            if not text:
                return {
                    "error": True,
                    "message": "No text provided for click action",
                }

            success = await self.browser.click_element_by_text(text)
            if success:
                await self._take_and_emit_screenshot()
                return {"success": True, "message": f"Clicked on '{text}'"}
            else:
                return {
                    "intervention_needed": True,
                    "message": (
                        f"Could not find clickable element with text '{text}'."
                        " Please help."
                    ),
                }

        elif action_type == "type_field":
            field = params.get("field")
            text = params.get("text")
            if not field or not text:
                return {
                    "error": True,
                    "message": "Missing field or text for type action",
                }

            success = await self.browser.type_in_field(field, text)
            if success:
                await self._take_and_emit_screenshot()
                return {"success": True, "message": f"Typed in field '{field}'"}
            else:
                return {
                    "intervention_needed": True,
                    "message": f"Could not find input field '{field}'. Please help.",
                }

        elif action_type == "navigate":
            url = params.get("url")
            if not url:
                return {"error": True, "message": "No URL provided for navigation"}

            success = await self.browser.navigate_to(url)
            if success:
                await self._take_and_emit_screenshot()
                return {"success": True, "message": f"Navigated to {url}"}
            else:
                return {"error": True, "message": f"Failed to navigate to {url}"}

        elif action_type == "wait":
            duration = params.get("duration", 3)
            await asyncio.sleep(duration)
            await self._take_and_emit_screenshot()
            return {"success": True, "message": f"Waited {duration} seconds"}

        elif action_type == "intervention":
            message = params.get("message", "Human intervention needed")
            return {"intervention_needed": True, "message": message}

        elif action_type == "completed":
            message = params.get("message", "Task completed successfully")
            return {"completed": True, "message": message}

        else:
            return {"error": True, "message": f"Unknown action type: {action_type}"}

    async def _take_and_emit_screenshot(self):
        """Take screenshot and emit via SSE."""
        screenshot = await self.browser.get_screenshot_base64()
        if screenshot:
            await self._emit_screenshot(screenshot)

    async def _emit_status(self, message: str):
        """Emit status update via SSE."""
        current_app.logger.info(f"Automation status: {message}")
        # Import here to avoid circular imports
        from src.routes import _broadcast_event

        await _broadcast_event("automation_status", message)

    async def _emit_screenshot(self, screenshot_base64: str):
        """Emit screenshot via SSE."""
        # Import here to avoid circular imports
        from src.routes import _broadcast_event

        screenshot_html = (
            f'<img src="data:image/png;base64,{screenshot_base64}" class="w-full'
            ' h-auto rounded" alt="Browser Screenshot">'
        )
        await _broadcast_event("automation_screenshot", screenshot_html)

    async def _request_intervention(self, message: str) -> str:
        """Request human intervention."""
        await self._emit_status(f"Requesting intervention: {message}")
        # Import here to avoid circular imports
        from src.routes import _broadcast_event

        await _broadcast_event("automation_intervention", message)
        # For now, just wait a bit and continue
        await asyncio.sleep(10)
        return "continue"
