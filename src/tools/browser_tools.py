"""Browser automation tools for agent."""

from pydantic_ai import RunContext
from pydantic_ai.toolsets import FunctionToolset
from quart import current_app

# Create toolset for browser tools
browser_toolset = FunctionToolset()

try:
    import browser_use

    BROWSER_USE_AVAILABLE = True
except ImportError:
    BROWSER_USE_AVAILABLE = False


def create_browser_llm():
    """Create browser-use compatible LLM using app configuration."""
    api_key = current_app.config["OPENROUTER_API_KEY"]
    model_name = current_app.config["BROWSER_USE_MODEL"]
    return browser_use.ChatOpenAI(
        model=model_name,
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )


# Only register browser tool if dependencies available
if BROWSER_USE_AVAILABLE:

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
        - Handle login flows (will pause for user input when needed)
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

        # Get browser instance from context (stored in LLMService)
        browser_instance = ctx.deps.get("browser_instance")

        # Initialize browser if needed
        if browser_instance is None:
            browser_instance = browser_use.Browser(
                headless=False,
                keep_alive=True,  # Persistent session
            )
            # Store for future use
            ctx.deps["browser_instance"] = browser_instance

        # Create browser LLM for this tool
        browser_llm = create_browser_llm()

        # Create browser-use agent with preconfigured LLM
        browser_agent = browser_use.Agent(
            retries=3,
            task=task,
            llm=browser_llm,
            browser=browser_instance,
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
        if (
            history
            and hasattr(history, "screenshot_paths")
            and history.screenshot_paths()
        ):
            screenshots = history.screenshot_paths()
            success_msg += f"\n📷 Screenshots saved: {len(screenshots)} files"

        current_app.logger.info(f"Web browsing completed: {task}")
        return success_msg
