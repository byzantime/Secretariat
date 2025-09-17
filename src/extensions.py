from quart_compress import Compress

from src.models.user import UserManager
from src.modules.assets import init_assets
from src.modules.conversation_manager import ConversationManager
from src.modules.database import Database
from src.modules.llm_service import LLMService
from src.modules.logging_helper import LoggingHelper
from src.modules.scheduling_service import SchedulingService

# Create instances without initializing
compress = Compress()
logging_helper = LoggingHelper()
database = Database()
conversation_manager = ConversationManager()
llm_service = LLMService()
scheduling_service = SchedulingService()
user_manager = UserManager()


def init_extensions(app):
    """Initialize all extensions with the application."""
    # Initialise in a specific order to handle dependencies
    compress.init_app(app)
    init_assets(app)
    logging_helper.init_app(app)
    database.init_app(app)  # Database must come early
    user_manager.init_app(app)  # User manager depends on database
    conversation_manager.init_app(app)  # Initialize before LLM service
    llm_service.init_app(app)
    scheduling_service.init_app(app)  # Initialize after database
