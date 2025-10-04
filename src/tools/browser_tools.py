"""Browser automation tools for agent."""

import os
import secrets

import browser_use
from browser_use import ActionResult
from browser_use import Tools
from pydantic import BaseModel
from pydantic import Field
from pydantic_ai import RunContext
from pydantic_ai.toolsets import FunctionToolset
from quart import current_app

# Create toolset for browser tools
browser_toolset = FunctionToolset()


def create_browser_llm():
    """Create browser-use compatible LLM using app configuration."""
    api_key = current_app.config["OPENROUTER_API_KEY"]
    model_name = current_app.config["BROWSER_USE_MODEL"]
    return browser_use.ChatOpenAI(
        model=model_name,
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )


class HumanAssistanceParams(BaseModel):
    """Parameters for requesting human assistance."""

    url: str = Field(description="URL where assistance is needed")
    instruction: str = Field(
        description=(
            "Simple, friendly instruction for the user about what they need to do."
            " Examples: 'I need you to solve the CAPTCHA for me', 'I need you to login"
            " to continue', 'Please complete the 2FA verification', 'I need you to fill"
            " in your personal information'"
        )
    )


@browser_toolset.tool
async def browse_web(ctx: RunContext[dict], task: str) -> str:
    """Use this tool for interactive web browsing, website navigation, and complex web interactions.

    **When to use this tool:**
    - User says "open [website]" or "go to [website]" or "navigate to [URL]"
    - User asks to visit a specific webpage or URL directly
    - User wants to interact with websites (fill forms, click buttons, submit data)
    - User requests tasks requiring persistent browser sessions or login
    - User needs to extract specific data from particular websites
    - User asks for complex multi-step website operations

    **This tool is ideal for:**
    - Direct website navigation and browsing
    - Interactive web tasks (forms, clicks, scrolling, typing)
    - Tasks requiring authentication or session persistence
    - Complex website workflows and multi-step processes
    - Specific data extraction from known websites
    - E-commerce tasks (shopping, cart management, checkout)

    **Do NOT use this tool for:**
    - Simple web searches or information lookups
    - General research questions
    - Getting current news or facts
    - Quick information retrieval

    This tool controls a persistent browser that can:
    - Navigate to any website or URL
    - Fill out forms and submit data
    - Click buttons, links, and interactive elements
    - Extract text, data, or content from web pages
    - Request human assistance for logins, CAPTCHAs, 2FA, personal info, etc.
    - Maintain session state across multiple requests
    - Take screenshots and capture page content

    Args:
        task: Describe what to do on the web. Be specific about the website and action.
              Examples:
              - "Navigate to amazon.com, search for 'wireless headphones', and get the first 3 product details"
              - "Fill out the contact form on example.com with my information"
              - "Go to my bank website and check my account balance" (will pause for human login)
              - "Open GitHub, navigate to my repositories, and create a new repository"

    Returns:
        A description of what was accomplished, including any extracted data or results.
    """
    current_app.logger.info(f"🔧 TOOL CALLED: browse_web - task: {task}")

    # Get DISPLAY environment variable for X11 connection
    display_env = os.environ.get("DISPLAY")
    current_app.logger.info(f"🖥️ DISPLAY environment variable: {display_env}")

    # Create browser instance (VNC already running from app startup)
    user_data_dir = current_app.config["BROWSER_USER_DATA_DIR"]
    browser_instance = browser_use.Browser(
        headless=False,
        user_data_dir=user_data_dir,  # Persistent session storage (cookies, login state)
        env=(
            {"DISPLAY": display_env} if display_env else None
        ),  # Explicitly pass DISPLAY for X11
    )

    # Create browser LLM for this tool
    browser_llm = create_browser_llm()

    # Create custom tools with authentication action
    tools = Tools()

    @tools.action(
        "Use this tool to request human assistance when you encounter ANY obstacle"
        " requiring user input: login screens, CAPTCHAs, 2FA prompts, personal"
        " information forms (credit card, address, etc.), age verification, or any task"
        " you cannot complete autonomously. The user will be shown the live browser via"
        " VNC to provide the needed input, then you can continue the task. MUST use"
        " this when stuck - do not give up! When providing the reason, use simple,"
        " friendly language that tells the user exactly what to do. Examples: 'I need"
        " you to solve the CAPTCHA for me', 'I need you to login to continue', 'Please"
        " complete the 2FA verification', 'I need you to fill in your personal"
        " information'",
        param_model=HumanAssistanceParams,
    )
    async def request_human_assistance(
        params: HumanAssistanceParams, browser_session
    ) -> ActionResult:
        """Custom action for browser-use to request human assistance.

        This gets called by browser-use's LLM when it encounters any obstacle
        requiring user input: logins, CAPTCHAs, 2FA, personal info, etc.
        """
        url = params.url
        instruction = params.instruction
        current_app.logger.info(
            f"👤 BROWSER-USE ACTION: request_human_assistance - {url}: {instruction}"
        )

        # Get services
        assistance_service = current_app.extensions["human_assistance_service"]
        assistance_monitor = current_app.extensions["assistance_monitor"]
        event_handler = current_app.extensions["event_handler"]

        # Get current URL from browser session
        tabs = await browser_session.get_tabs()
        if not tabs:
            return ActionResult(
                extracted_content="❌ No active browser tab found",
                error="No tabs available",
            )

        current_url = tabs[0].url
        current_app.logger.info(f"Current browser URL: {current_url}")

        # Create assistance session
        session_id, assistance_url = assistance_service.create_assistance_session(
            url, instruction
        )

        # Send assistance notification via event system
        message_id = secrets.token_urlsafe(8)
        notification_content = (
            f"**I need your help with `{url}`**\n\n"
            f"[{instruction}]({assistance_url})\n\n"
            "_Link expires in 5 minutes_"
        )

        # Emit message start event
        await event_handler.emit_to_services(
            "llm.message.start",
            {"message_id": message_id, "content": ""},
        )

        # Emit message complete event with content
        await event_handler.emit_to_services(
            "llm.message.complete",
            {"message_id": message_id, "content": notification_content},
        )

        # Monitor for completion of human assistance
        current_app.logger.info("Waiting for user to complete assistance...")
        success = await assistance_monitor.monitor_for_completion(
            browser_session, current_url, session_id, timeout=300
        )

        # Mark session complete
        if success:
            assistance_service.mark_session_complete(session_id)

            # Notify user via event system
            completion_message_id = secrets.token_urlsafe(8)
            completion_content = (
                "✅ Assistance completed!\n\nYour session has been saved and"
                " will persist across app restarts."
            )

            # Emit message start event
            await event_handler.emit_to_services(
                "llm.message.start",
                {"message_id": completion_message_id, "content": ""},
            )

            # Emit message complete event with content
            await event_handler.emit_to_services(
                "llm.message.complete",
                {"message_id": completion_message_id, "content": completion_content},
            )

            return ActionResult(
                extracted_content=(
                    f"✅ Human assistance completed for {url} ({instruction}). "
                    "You can now continue with the task."
                ),
                long_term_memory=f"User provided assistance for: {instruction}",
            )
        else:
            return ActionResult(
                extracted_content=(
                    "❌ Assistance timeout - user did not complete the request"
                    f" ({instruction}) within 5 minutes"
                ),
                error="Human assistance timeout",
            )

    task += "\nUse the request_human_assistance action to request assistance!"

    # Create browser-use agent with custom tools (including human assistance)
    browser_agent = browser_use.Agent(
        retries=3,
        task=task,
        llm=browser_llm,
        browser=browser_instance,
        tools=tools,  # Pass custom tools with authentication action
    )

    # Run the web browsing task
    current_app.logger.info(f"Starting web browsing task: {task}")
    history = await browser_agent.run()

    # Extract results
    if history and hasattr(history, "final_result"):
        result = history.final_result()
        if result:
            success_msg = f"✅ Web browsing completed successfully:\n{result}"
        else:
            success_msg = f"✅ Web browsing task completed: {task}"
    else:
        success_msg = f"✅ Web browsing task completed: {task}"

    # Add screenshot info if available
    if history and hasattr(history, "screenshot_paths") and history.screenshot_paths():
        screenshots = history.screenshot_paths()
        success_msg += f"\n📷 Screenshots saved: {len(screenshots)} files"

    current_app.logger.info(f"Web browsing completed: {task}")
    return success_msg
