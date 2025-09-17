from quart_compress import Compress

from src.models.user import UserManager
from src.modules.assets import init_assets
from src.modules.conversation_manager import ConversationManager
from src.modules.database import Database
from src.modules.event_handler import EventHandler
from src.modules.llm_service import LLMService
from src.modules.logging_helper import LoggingHelper
from src.modules.scheduling_service import SchedulingService
from src.modules.user_messaging_service import UserMessagingService

# Create instances without initializing
compress = Compress()
logging_helper = LoggingHelper()
database = Database()
event_handler = EventHandler()
conversation_manager = ConversationManager()
llm_service = LLMService()
scheduling_service = SchedulingService()
user_messaging_service = UserMessagingService()
user_manager = UserManager()


def init_extensions(app):
    """Initialize all extensions with the application."""
    # Initialise in a specific order to handle dependencies
    compress.init_app(app)
    init_assets(app)
    logging_helper.init_app(app)
    database.init_app(app)  # Database must come early
    event_handler.init_app(app)
    user_manager.init_app(app)  # User manager depends on database
    conversation_manager.init_app(app)  # Initialize before LLM service
    llm_service.init_app(app)
    scheduling_service.init_app(app)  # Initialize after database
    user_messaging_service.init_app(app)  # Initialize after event handler
