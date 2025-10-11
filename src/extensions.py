from quart_compress import Compress

from src.models.user import UserManager
from src.modules.assets import init_assets
from src.modules.assistance_monitor import AssistanceMonitor
from src.modules.conversation_manager import ConversationManager
from src.modules.database import Database
from src.modules.event_handler import EventHandler
from src.modules.human_assistance_service import HumanAssistanceService
from src.modules.llm_service import LLMService
from src.modules.logging_helper import LoggingHelper
from src.modules.memory import MemoryService
from src.modules.ngrok_service import NgrokService
from src.modules.novnc_proxy import NoVNCProxy
from src.modules.scheduling_service import SchedulingService
from src.modules.user_messaging_service import CommunicationService
from src.modules.vnc_server import VNCServer
from src.modules.wtforms_helpers import WTFormsHelpers

# Create instances without initializing
compress = Compress()
logging_helper = LoggingHelper()
database = Database()
event_handler = EventHandler()
conversation_manager = ConversationManager()
memory_service = MemoryService()
llm_service = LLMService()
scheduling_service = SchedulingService()
ngrok_service = NgrokService()
communication_service = CommunicationService()
user_manager = UserManager()
human_assistance_service = HumanAssistanceService()
assistance_monitor = AssistanceMonitor()
vnc_server = VNCServer()
novnc_proxy = NoVNCProxy()
wtforms_helpers = WTFormsHelpers()


def init_core_extensions(app):
    """Initialize core extensions that don't require user configuration."""
    # Initialise in a specific order to handle dependencies
    compress.init_app(app)
    init_assets(app)
    logging_helper.init_app(app)
    database.init_app(app)  # Database must come early
    event_handler.init_app(app)
    user_manager.init_app(app)  # User manager depends on database
    conversation_manager.init_app(app)  # Initialize before LLM service
    ngrok_service.init_app(app)  # Initialize before communication service
    communication_service.init_app(app)  # Initialize after event handler
    wtforms_helpers.init_app(app)


def init_feature_extensions(app):
    """Initialize optional feature extensions that require user configuration."""
    memory_service.init_app(app)  # Initialize memory service
    llm_service.init_app(app)
    scheduling_service.init_app(app)  # Initialize after database
    human_assistance_service.init_app(app)  # Initialize human assistance services
    assistance_monitor.init_app(app)
    vnc_server.init_app(app)
    novnc_proxy.init_app(app)


def init_extensions(app):
    """Initialize all extensions with the application."""
    init_core_extensions(app)

    # Only initialize feature extensions if not in setup mode
    if not app.config.get("SETUP_MODE", False):
        init_feature_extensions(app)
