from quart_compress import Compress

from src.models.user import UserManager
from src.modules.assets import init_assets
from src.modules.browser_service import BrowserService
from src.modules.conversation_manager import ConversationManager
from src.modules.database import Database
from src.modules.event_handler import EventHandler
from src.modules.llm_service import LLMService
from src.modules.logging_helper import LoggingHelper
from src.modules.tool_manager import ToolManager

# Create instances without initializing
compress = Compress()
logging_helper = LoggingHelper()
database = Database()
event_handler = EventHandler()
browser_service = BrowserService()
conversation_manager = ConversationManager()
llm_service = LLMService()
user_manager = UserManager()
tool_manager = ToolManager()


def init_extensions(app):
    """Initialize all extensions with the application."""
    # Initialise in a specific order to handle dependencies
    compress.init_app(app)
    init_assets(app)
    logging_helper.init_app(app)
    database.init_app(app)  # Database must come early
    user_manager.init_app(app)  # User manager depends on database
    event_handler.init_app(app)
    browser_service.init_app(app)  # Browser service can be initialized early
    conversation_manager.init_app(app)  # Initialize before LLM service
    tool_manager.init_app(app)  # Initialize before LLM service so tools are available
    llm_service.init_app(app)
