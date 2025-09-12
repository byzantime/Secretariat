"""Tool management system for LLM tool use capabilities."""

from abc import ABC
from abc import abstractmethod
from typing import Dict
from typing import List
from typing import Optional

from quart import current_app


class Tool(ABC):
    """Abstract base class for LLM tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the tool name."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Return the tool description."""
        pass

    @property
    @abstractmethod
    def input_schema(self) -> Dict:
        """Return the tool input schema."""
        pass

    @abstractmethod
    async def execute(self, input_data: Dict, conversation) -> str:
        """Execute the tool with given input data.

        Should return a simple string describing the result.
        Raise exceptions for errors - the ToolManager will handle formatting.
        """
        pass

    async def is_available(self, conversation) -> bool:
        """Check if this tool is available for the given conversation.

        Override this method in subclasses to implement conditional tool availability.
        By default, tools are always available.

        Args:
            conversation: The conversation context

        Returns:
            bool: True if the tool should be available, False otherwise
        """
        return True

    def to_dict(self) -> Dict:
        """Convert tool to dictionary format for LLM API."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class ToolManager:
    """Manages LLM tools and their execution."""

    def __init__(self, app=None):
        """Initialize the tool manager."""
        self.tools: Dict[str, Tool] = {}
        self.fallback_tool = None
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialize the app with the ToolManager."""
        self.app = app
        app.extensions["tool_manager"] = self

        # Register built-in tools
        self._register_builtin_tools()

        app.logger.info("ToolManager initialized")

    def _register_builtin_tools(self):
        """Register hard-coded list of available tools."""
        from src.tools.fallback_tool import FallbackTool
        from src.tools.web_automation_tool import WebAutomationTool

        # Pre-register all available tools
        builtin_tools = [
            WebAutomationTool(),
        ]

        # Register the fallback tool separately (not included in regular tool list)
        self.fallback_tool = FallbackTool()
        self.app.logger.info(f"Registered fallback tool: {self.fallback_tool.name}")

        for tool in builtin_tools:
            self.tools[tool.name] = tool
            self.app.logger.info(f"Registered builtin tool: {tool.name}")

    def register_tool(self, tool: Tool):
        """Register a tool."""
        self.tools[tool.name] = tool
        if hasattr(self, "app"):
            current_app.logger.info(f"Registered tool: {tool.name}")

    def unregister_tool(self, tool_name: str):
        """Unregister a tool."""
        if tool_name in self.tools:
            del self.tools[tool_name]
            if hasattr(self, "app"):
                current_app.logger.info(f"Unregistered tool: {tool_name}")

    async def get_available_tools(self, conversation) -> List[Dict]:
        """Get available tools for a conversation as API format."""
        available_tools = []
        for tool in self.tools.values():
            if await tool.is_available(conversation):
                available_tools.append(tool.to_dict())
        current_app.logger.debug(
            f"Available tools for conversation {conversation.id}:"
            f" {[tool['name'] for tool in available_tools]}"
        )
        return available_tools

    async def execute_tool(
        self, tool_name: str, input_data: Dict, conversation
    ) -> tuple[str, bool]:
        """Execute a tool with given input data.

        Returns:
            tuple[str, bool]: (result_text, is_error)
        """
        if tool_name not in self.tools:
            # Use fallback tool for unknown tool calls
            current_app.logger.warning(
                f"Unknown tool '{tool_name}' called, using fallback tool"
            )
            tool = self.fallback_tool
        else:
            tool = self.tools[tool_name]

        current_app.logger.info(
            f"Executing tool '{tool.name}' for conversation {conversation.id}"
        )

        try:
            result = await tool.execute(input_data, conversation)
            result_tuple = (result, False)
            current_app.logger.debug(
                f"Tool '{tool.name}' execution result: {result_tuple}"
            )
            return result_tuple
        except Exception as e:
            error_msg = f"Error executing tool '{tool.name}': {str(e)}"
            current_app.logger.error(error_msg, exc_info=True)
            return error_msg, True

    def get_tool_names(self) -> List[str]:
        """Get list of registered tool names."""
        return list(self.tools.keys())

    def get_tool(self, tool_name: str) -> Optional[Tool]:
        """Get a specific tool by name."""
        return self.tools.get(tool_name)
