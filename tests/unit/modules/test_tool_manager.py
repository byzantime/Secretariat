"""Unit tests for tool_manager.py."""

from typing import Any
from typing import Dict
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch
from uuid import uuid4

import pytest

from src.modules.tool_manager import Tool
from src.modules.tool_manager import ToolManager


class MockTestTool(Tool):
    """Concrete test implementation of Tool for testing."""

    def __init__(self, name="test_tool", description="Test tool", available=True):
        self._name = name
        self._description = description
        self._available = available
        self.execute_called = False
        self.execute_args = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def input_schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Test message"}
            },
            "required": ["message"],
        }

    async def execute(self, input_data: Dict, conversation) -> str:
        self.execute_called = True
        self.execute_args = (input_data, conversation)
        return f"Executed with: {input_data.get('message', 'no message')}"

    async def is_available(self, conversation) -> bool:
        return self._available


class FailingTool(Tool):
    """Test tool that always fails during execution."""

    @property
    def name(self) -> str:
        return "failing_tool"

    @property
    def description(self) -> str:
        return "Tool that fails"

    @property
    def input_schema(self) -> Dict:
        return {"type": "object"}

    async def execute(self, input_data: Dict, conversation) -> Any:
        raise ValueError("Test failure")


@pytest.fixture
def mock_app():
    """Mock Quart app for testing."""
    app = MagicMock()
    app.extensions = {}
    app.logger = MagicMock()
    return app


@pytest.fixture
def mock_conversation():
    """Mock conversation object for testing."""
    conversation = MagicMock()
    conversation.id = str(uuid4())
    conversation.user_id = "test_user"
    conversation.outbound = False
    return conversation


@pytest.fixture
def tool_manager(mock_app):
    """ToolManager instance for testing."""
    with patch("src.modules.tool_manager.current_app", mock_app):
        manager = ToolManager()
        # Clear builtin tools for clean testing
        manager.tools = {}
        manager.fallback_tool = MagicMock()
        manager.fallback_tool.name = "__fallback__"
        return manager


class TestToolAbstractBaseClass:
    """Tests for the Tool abstract base class."""

    def test_tool_without_name_fails(self):
        """Test that Tool without name property fails."""

        class IncompleteToolName(Tool):
            @property
            def description(self) -> str:
                return "test"

            @property
            def input_schema(self) -> Dict:
                return {}

            async def execute(self, input_data: Dict, conversation) -> Any:
                return None

        with pytest.raises(TypeError):
            IncompleteToolName()

    def test_tool_without_description_fails(self):
        """Test that Tool without description property fails."""

        class IncompleteToolDescription(Tool):
            @property
            def name(self) -> str:
                return "test"

            @property
            def input_schema(self) -> Dict:
                return {}

            async def execute(self, input_data: Dict, conversation) -> Any:
                return None

        with pytest.raises(TypeError):
            IncompleteToolDescription()

    def test_tool_without_schema_fails(self):
        """Test that Tool without input_schema property fails."""

        class IncompleteToolSchema(Tool):
            @property
            def name(self) -> str:
                return "test"

            @property
            def description(self) -> str:
                return "test"

            async def execute(self, input_data: Dict, conversation) -> Any:
                return None

        with pytest.raises(TypeError):
            IncompleteToolSchema()

    def test_tool_without_execute_fails(self):
        """Test that Tool without execute method fails."""

        class IncompleteToolExecute(Tool):
            @property
            def name(self) -> str:
                return "test"

            @property
            def description(self) -> str:
                return "test"

            @property
            def input_schema(self) -> Dict:
                return {}

        with pytest.raises(TypeError):
            IncompleteToolExecute()

    @pytest.mark.asyncio
    async def test_default_is_available_returns_true(self, mock_conversation):
        """Test that default is_available method returns True."""
        tool = MockTestTool()
        assert await tool.is_available(mock_conversation) is True

    def test_to_dict_returns_correct_format(self):
        """Test that to_dict returns correct format."""
        tool = MockTestTool(name="test_name", description="test_desc")
        result = tool.to_dict()

        expected = {
            "name": "test_name",
            "description": "test_desc",
            "input_schema": tool.input_schema,
        }
        assert result == expected

    @pytest.mark.asyncio
    async def test_concrete_implementation_works(self, mock_conversation):
        """Test that concrete tool implementation works correctly."""
        tool = MockTestTool()

        # Test properties
        assert tool.name == "test_tool"
        assert tool.description == "Test tool"
        assert isinstance(tool.input_schema, dict)

        # Test execution
        input_data = {"message": "test"}
        result = await tool.execute(input_data, mock_conversation)

        assert tool.execute_called is True
        assert tool.execute_args == (input_data, mock_conversation)
        assert result == "Executed with: test"


class TestToolManagerInitialization:
    """Tests for ToolManager initialization."""

    def test_init_without_app(self):
        """Test ToolManager initialization without app."""
        manager = ToolManager()
        assert manager.tools == {}
        assert manager.fallback_tool is None

    def test_init_with_app(self, mock_app):
        """Test ToolManager initialization with app."""
        with patch.object(ToolManager, "init_app") as mock_init_app:
            ToolManager(mock_app)
            mock_init_app.assert_called_once_with(mock_app)

    def test_init_app_registers_builtin_tools(self, mock_app):
        """Test that init_app registers builtin tools."""
        with patch("src.tools.fallback_tool.FallbackTool") as mock_fallback_class:
            # Setup mocks
            mock_fallback = MagicMock()
            mock_fallback.name = "__fallback__"
            mock_fallback_class.return_value = mock_fallback

            manager = ToolManager()
            manager.init_app(mock_app)

            # Check app setup
            assert manager.app == mock_app
            assert mock_app.extensions["tool_manager"] == manager

            # Check builtin tools registered
            assert len(manager.tools) == 1  # WebAutomationTool is registered
            assert "web_automation" in manager.tools
            assert manager.fallback_tool == mock_fallback

            # Check logging
            assert mock_app.logger.info.call_count >= 1  # At least fallback tool


class TestToolRegistration:
    """Tests for tool registration and unregistration."""

    def test_register_tool(self, tool_manager, mock_app):
        """Test registering a tool."""
        tool = MockTestTool(name="new_tool")
        tool_manager.app = mock_app  # Set app so logging will work

        with patch("src.modules.tool_manager.current_app", mock_app):
            tool_manager.register_tool(tool)

        assert "new_tool" in tool_manager.tools
        assert tool_manager.tools["new_tool"] == tool
        mock_app.logger.info.assert_called_with("Registered tool: new_tool")

    def test_register_tool_without_app_context(self, mock_app):
        """Test registering a tool without app context."""
        manager = ToolManager()
        tool = MockTestTool(name="no_context_tool")

        # Should not raise exception
        manager.register_tool(tool)
        assert "no_context_tool" in manager.tools

    def test_register_duplicate_tool_overwrites(self, tool_manager):
        """Test that registering duplicate tool name overwrites."""
        tool1 = MockTestTool(name="duplicate_tool", description="First tool")
        tool2 = MockTestTool(name="duplicate_tool", description="Second tool")

        tool_manager.register_tool(tool1)
        tool_manager.register_tool(tool2)

        assert tool_manager.tools["duplicate_tool"] == tool2
        assert tool_manager.tools["duplicate_tool"].description == "Second tool"

    def test_unregister_tool(self, tool_manager, mock_app):
        """Test unregistering a tool."""
        tool = MockTestTool(name="to_remove")
        tool_manager.register_tool(tool)
        tool_manager.app = mock_app  # Set app so logging will work

        with patch("src.modules.tool_manager.current_app", mock_app):
            tool_manager.unregister_tool("to_remove")

        assert "to_remove" not in tool_manager.tools
        mock_app.logger.info.assert_called_with("Unregistered tool: to_remove")

    def test_unregister_nonexistent_tool(self, tool_manager, mock_app):
        """Test unregistering a tool that doesn't exist."""
        with patch("src.modules.tool_manager.current_app", mock_app):
            # Should not raise exception
            tool_manager.unregister_tool("nonexistent_tool")

        # Should not have logged anything since tool didn't exist
        mock_app.logger.info.assert_not_called()

    def test_unregister_tool_without_app_context(self, tool_manager):
        """Test unregistering a tool without app context."""
        tool = MockTestTool(name="no_context_remove")
        tool_manager.register_tool(tool)

        # Should not raise exception
        tool_manager.unregister_tool("no_context_remove")
        assert "no_context_remove" not in tool_manager.tools


class TestToolAvailabilityAndListing:
    """Tests for tool availability and listing methods."""

    @pytest.mark.asyncio
    async def test_get_available_tools_all_available(
        self, tool_manager, mock_conversation, mock_app
    ):
        """Test get_available_tools when all tools are available."""
        tool1 = MockTestTool(name="tool1", available=True)
        tool2 = MockTestTool(name="tool2", available=True)

        tool_manager.register_tool(tool1)
        tool_manager.register_tool(tool2)

        with patch("src.modules.tool_manager.current_app", mock_app):
            available = await tool_manager.get_available_tools(mock_conversation)

        assert len(available) == 2
        tool_names = [tool["name"] for tool in available]
        assert "tool1" in tool_names
        assert "tool2" in tool_names

        # Check format
        for tool_dict in available:
            assert "name" in tool_dict
            assert "description" in tool_dict
            assert "input_schema" in tool_dict

    @pytest.mark.asyncio
    async def test_get_available_tools_filtered_by_availability(
        self, tool_manager, mock_conversation, mock_app
    ):
        """Test get_available_tools respects tool availability."""
        available_tool = MockTestTool(name="available", available=True)
        unavailable_tool = MockTestTool(name="unavailable", available=False)

        tool_manager.register_tool(available_tool)
        tool_manager.register_tool(unavailable_tool)

        with patch("src.modules.tool_manager.current_app", mock_app):
            available = await tool_manager.get_available_tools(mock_conversation)

        assert len(available) == 1
        assert available[0]["name"] == "available"

    @pytest.mark.asyncio
    async def test_get_available_tools_logs_debug_info(
        self, tool_manager, mock_conversation, mock_app
    ):
        """Test that get_available_tools logs debug information."""
        tool = MockTestTool(name="debug_tool")
        tool_manager.register_tool(tool)

        with patch("src.modules.tool_manager.current_app", mock_app):
            await tool_manager.get_available_tools(mock_conversation)

        # Should log available tools
        mock_app.logger.debug.assert_called_once()
        log_call = mock_app.logger.debug.call_args[0][0]
        assert "Available tools for conversation" in log_call
        assert mock_conversation.id in log_call

    def test_get_tool_names(self, tool_manager):
        """Test get_tool_names returns correct list."""
        tool1 = MockTestTool(name="first_tool")
        tool2 = MockTestTool(name="second_tool")

        tool_manager.register_tool(tool1)
        tool_manager.register_tool(tool2)

        names = tool_manager.get_tool_names()
        assert set(names) == {"first_tool", "second_tool"}

    def test_get_tool_names_empty(self, tool_manager):
        """Test get_tool_names with no tools."""
        names = tool_manager.get_tool_names()
        assert names == []

    def test_get_tool_existing(self, tool_manager):
        """Test get_tool returns correct tool."""
        tool = MockTestTool(name="existing_tool")
        tool_manager.register_tool(tool)

        result = tool_manager.get_tool("existing_tool")
        assert result == tool

    def test_get_tool_nonexistent(self, tool_manager):
        """Test get_tool returns None for nonexistent tool."""
        result = tool_manager.get_tool("nonexistent")
        assert result is None


class TestToolExecution:
    """Tests for tool execution functionality."""

    @pytest.mark.asyncio
    async def test_execute_tool_success(
        self, tool_manager, mock_conversation, mock_app
    ):
        """Test successful tool execution."""
        tool = MockTestTool(name="success_tool")
        tool_manager.register_tool(tool)

        input_data = {"message": "test input"}

        with patch("src.modules.tool_manager.current_app", mock_app):
            result = await tool_manager.execute_tool(
                "success_tool", input_data, mock_conversation
            )

        assert result == ("Executed with: test input", False)
        assert tool.execute_called is True
        assert tool.execute_args == (input_data, mock_conversation)

        # Check logging
        mock_app.logger.info.assert_called_with(
            f"Executing tool 'success_tool' for conversation {mock_conversation.id}"
        )
        mock_app.logger.debug.assert_called_with(
            f"Tool 'success_tool' execution result: {result}"
        )

    @pytest.mark.asyncio
    async def test_execute_unknown_tool_uses_fallback(
        self, tool_manager, mock_conversation, mock_app
    ):
        """Test that unknown tool execution uses fallback tool."""
        fallback_result = "Fallback executed"
        tool_manager.fallback_tool.execute = AsyncMock(return_value=fallback_result)
        tool_manager.fallback_tool.name = "__fallback__"

        input_data = {"message": "unknown tool test"}

        with patch("src.modules.tool_manager.current_app", mock_app):
            result = await tool_manager.execute_tool(
                "unknown_tool", input_data, mock_conversation
            )

        assert result == (fallback_result, False)
        tool_manager.fallback_tool.execute.assert_called_once_with(
            input_data, mock_conversation
        )

        # Check warning logged
        mock_app.logger.warning.assert_called_with(
            "Unknown tool 'unknown_tool' called, using fallback tool"
        )

    @pytest.mark.asyncio
    async def test_execute_tool_handles_exceptions(
        self, tool_manager, mock_conversation, mock_app
    ):
        """Test that tool execution handles and logs exceptions."""
        failing_tool = FailingTool()
        tool_manager.register_tool(failing_tool)

        input_data = {"test": "data"}

        with patch("src.modules.tool_manager.current_app", mock_app):
            result = await tool_manager.execute_tool(
                "failing_tool", input_data, mock_conversation
            )

        # Should return error message with is_error=True
        assert result == ("Error executing tool 'failing_tool': Test failure", True)

        # Check error logging
        mock_app.logger.error.assert_called_with(
            "Error executing tool 'failing_tool': Test failure", exc_info=True
        )


class TestIntegration:
    """Integration tests for ToolManager."""

    @pytest.mark.asyncio
    async def test_full_workflow_register_check_execute(
        self, mock_app, mock_conversation
    ):
        """Test full workflow: register -> check availability -> execute."""
        with patch("src.modules.tool_manager.current_app", mock_app):
            manager = ToolManager()
            manager.tools = {}  # Clear builtin tools
            manager.fallback_tool = MagicMock()

            # Register tool
            tool = MockTestTool(name="workflow_tool", available=True)
            manager.register_tool(tool)

            # Check availability
            available_tools = await manager.get_available_tools(mock_conversation)
            assert len(available_tools) == 1
            assert available_tools[0]["name"] == "workflow_tool"

            # Execute tool
            input_data = {"message": "workflow test"}
            result = await manager.execute_tool(
                "workflow_tool", input_data, mock_conversation
            )

            assert result == ("Executed with: workflow test", False)
            assert tool.execute_called is True

    @pytest.mark.asyncio
    async def test_tool_availability_affects_listing(self, mock_app, mock_conversation):
        """Test that tool availability affects get_available_tools."""
        with patch("src.modules.tool_manager.current_app", mock_app):
            manager = ToolManager()
            manager.tools = {}

            # Tool that changes availability based on conversation
            class ConditionalTool(MockTestTool):
                async def is_available(self, conversation):
                    return conversation.user_id == "allowed_user"

            tool = ConditionalTool(name="conditional_tool")
            manager.register_tool(tool)

            # Test with allowed user
            mock_conversation.user_id = "allowed_user"
            available = await manager.get_available_tools(mock_conversation)
            assert len(available) == 1

            # Test with different user
            mock_conversation.user_id = "other_user"
            available = await manager.get_available_tools(mock_conversation)
            assert len(available) == 0

    def test_manager_with_app_extensions(self, mock_app):
        """Test ToolManager properly sets up app extensions."""
        with patch("src.tools.fallback_tool.FallbackTool") as mock_fallback_class:
            # Setup mocks
            mock_fallback = MagicMock()
            mock_fallback.name = "__fallback__"
            mock_fallback_class.return_value = mock_fallback

            manager = ToolManager()
            manager.init_app(mock_app)

            # Should have registered builtin tools
            assert len(manager.tools) == 1  # WebAutomationTool is registered
            assert "web_automation" in manager.tools
            assert manager.fallback_tool is not None
            assert manager.fallback_tool.name == "__fallback__"

            # Should be accessible via app extensions
            assert mock_app.extensions["tool_manager"] == manager
