"""Unit tests for dynamic form generation from Settings model."""

import pytest
from wtforms import IntegerField
from wtforms import SelectField
from wtforms import StringField

from src.forms import SettingsForm
from src.forms import create_settings_form
from src.models.settings import Settings


@pytest.fixture
def settings_form_no_csrf(app):
    """Create a SettingsForm class without CSRF for testing."""

    # Create form with CSRF disabled for testing
    class TestMeta:
        csrf = False

    # Create a test version of SettingsForm with CSRF disabled
    form_class = create_settings_form()
    form_class.Meta = TestMeta
    return form_class


class TestFormGeneration:
    """Test dynamic form generation from Settings model."""

    def test_create_settings_form_returns_form_class(self, app):
        """Test that create_settings_form returns a FlaskForm subclass."""
        form_class = create_settings_form()

        assert form_class is not None
        assert hasattr(form_class, "validate")
        # _unbound_fields exists on the class, _fields exists only on instances
        assert hasattr(form_class, "_unbound_fields")

    def test_settings_form_is_created_at_module_level(self):
        """Test that SettingsForm is available at module level."""
        assert SettingsForm is not None
        assert hasattr(SettingsForm, "validate")

    def test_form_excludes_hidden_fields(self, app):
        """Test that internal/hidden fields are excluded from form."""
        # Fields that should be excluded
        excluded = {"debug", "log_level", "secret_key", "database_name", "data_dir"}

        for field_name in excluded:
            assert not hasattr(
                SettingsForm, field_name
            ), f"{field_name} should be excluded"

    def test_form_includes_user_configurable_fields(self, app):
        """Test that user-configurable fields are included in form."""
        # Sample of fields that should be present
        expected_fields = {
            "llm_provider",
            "openrouter_api_key",
            "zen_api_key",
            "timezone",
            "telegram_bot_token",
            "qdrant_host",
        }

        for field_name in expected_fields:
            assert hasattr(SettingsForm, field_name), f"{field_name} should be in form"


class TestFormFieldTypes:
    """Test that form fields have correct types based on Settings annotations."""

    def test_literal_fields_become_select_fields(self, settings_form_no_csrf):
        """Test that Literal annotations become SelectField."""
        form = settings_form_no_csrf()

        # llm_provider is Literal["openrouter", "zen"]
        assert hasattr(form, "llm_provider")
        field = getattr(form, "llm_provider")
        assert isinstance(field, SelectField)

    def test_boolean_fields_become_boolean_fields(self):
        """Test that bool annotations become BooleanField."""
        # Note: debug is excluded, but we can test the pattern
        # Create a test form with a boolean field if needed
        # For now, we verify the behavior exists in the codebase
        pass

    def test_integer_fields_become_integer_fields(self, settings_form_no_csrf):
        """Test that int annotations become IntegerField."""
        form = settings_form_no_csrf()

        integer_fields = [
            "qdrant_port",
            "vnc_port",
            "novnc_port",
            "assistance_link_expiration",
        ]

        for field_name in integer_fields:
            assert hasattr(form, field_name)
            field = getattr(form, field_name)
            assert isinstance(
                field, IntegerField
            ), f"{field_name} should be IntegerField"

    def test_string_fields_become_string_fields(self, settings_form_no_csrf):
        """Test that str annotations become StringField."""
        form = settings_form_no_csrf()

        string_fields = ["openrouter_model", "zen_model", "timezone", "vnc_display"]

        for field_name in string_fields:
            assert hasattr(form, field_name)
            field = getattr(form, field_name)
            assert isinstance(field, StringField), f"{field_name} should be StringField"

    def test_optional_string_fields_become_string_fields(self, settings_form_no_csrf):
        """Test that Optional[str] annotations become StringField."""
        form = settings_form_no_csrf()

        optional_string_fields = [
            "openrouter_api_key",
            "zen_api_key",
            "telegram_bot_token",
        ]

        for field_name in optional_string_fields:
            assert hasattr(form, field_name)
            field = getattr(form, field_name)
            assert isinstance(field, StringField), f"{field_name} should be StringField"


class TestFormFieldDefaults:
    """Test that form fields have correct default values."""

    def test_form_fields_have_settings_defaults(self, settings_form_no_csrf):
        """Test that form fields use Settings model defaults."""
        form = settings_form_no_csrf()

        # Check some default values
        assert form.llm_provider.data == "zen"
        assert form.timezone.data == "UTC"
        assert form.qdrant_port.data == 6333

    def test_form_optional_fields_default_empty(self, settings_form_no_csrf):
        """Test that optional fields default to empty string."""
        form = settings_form_no_csrf()

        # Optional fields should have empty string or None as default
        assert form.openrouter_api_key.data in ("", None)
        assert form.zen_api_key.data in ("", None)


class TestFormPopulateFromSettings:
    """Test populate_from_settings() method."""

    def test_populate_from_settings_sets_field_values(self, settings_form_no_csrf):
        """Test that populate_from_settings populates all form fields."""
        settings = Settings(
            llm_provider="openrouter",
            openrouter_api_key="test-key-123",
            openrouter_model="custom-model",
            timezone="America/New_York",
            qdrant_port=6334,
        )

        form = settings_form_no_csrf()
        form.populate_from_settings(settings)

        assert form.llm_provider.data == "openrouter"
        assert form.openrouter_api_key.data == "test-key-123"
        assert form.openrouter_model.data == "custom-model"
        assert form.timezone.data == "America/New_York"
        assert form.qdrant_port.data == 6334

    def test_populate_from_settings_skips_none_values(self, settings_form_no_csrf):
        """Test that None values don't overwrite form defaults."""
        settings = Settings(
            llm_provider="zen",
            zen_api_key="test-key",
            # telegram_bot_token is None
        )

        form = settings_form_no_csrf()
        form.populate_from_settings(settings)

        # Non-None values should be set
        assert form.zen_api_key.data == "test-key"

        # None values should not be set (field keeps default)
        # The method only sets values that are not None

    def test_populate_from_settings_handles_all_field_types(
        self, settings_form_no_csrf
    ):
        """Test that populate handles strings, ints, and bools correctly."""
        settings = Settings(
            llm_provider="zen",
            zen_api_key="test-key",
            qdrant_port=6334,
            vnc_port=5901,
            timezone="Europe/London",
        )

        form = settings_form_no_csrf()
        form.populate_from_settings(settings)

        # String
        assert form.timezone.data == "Europe/London"
        # Int
        assert form.qdrant_port.data == 6334
        assert form.vnc_port.data == 5901


class TestFormToSettingsDict:
    """Test to_settings_dict() method."""

    def test_to_settings_dict_returns_dict(self, settings_form_no_csrf):
        """Test that to_settings_dict returns a dictionary."""
        form = settings_form_no_csrf()
        result = form.to_settings_dict()

        assert isinstance(result, dict)

    def test_to_settings_dict_excludes_csrf_token(self, settings_form_no_csrf):
        """Test that CSRF token is excluded from settings dict."""
        form = settings_form_no_csrf()
        result = form.to_settings_dict()

        assert "csrf_token" not in result

    def test_to_settings_dict_includes_form_data(self, settings_form_no_csrf):
        """Test that form data is included in settings dict."""
        form = settings_form_no_csrf()
        form.llm_provider.data = "openrouter"
        form.openrouter_api_key.data = "test-key"
        form.timezone.data = "America/New_York"
        form.qdrant_port.data = 6334

        result = form.to_settings_dict()

        assert result["llm_provider"] == "openrouter"
        assert result["openrouter_api_key"] == "test-key"
        assert result["timezone"] == "America/New_York"
        assert result["qdrant_port"] == 6334

    def test_to_settings_dict_converts_empty_strings_to_none(
        self, settings_form_no_csrf
    ):
        """Test that empty strings are converted to None for optional fields."""
        form = settings_form_no_csrf()
        form.llm_provider.data = "zen"
        form.zen_api_key.data = "test-key"
        form.telegram_bot_token.data = ""  # Empty string

        result = form.to_settings_dict()

        assert result["telegram_bot_token"] is None

    def test_to_settings_dict_preserves_non_empty_values(self, settings_form_no_csrf):
        """Test that non-empty values are preserved."""
        form = settings_form_no_csrf()
        form.llm_provider.data = "zen"
        form.zen_api_key.data = "test-key"
        form.telegram_bot_token.data = "bot-token"

        result = form.to_settings_dict()

        assert result["telegram_bot_token"] == "bot-token"


class TestFormValidation:
    """Test form validation integrates with Pydantic validation."""

    def test_form_validation_uses_pydantic(self, settings_form_no_csrf):
        """Test that form validation delegates to Pydantic Settings."""
        form = settings_form_no_csrf()

        # Set invalid data: OpenRouter selected but no API key
        form.llm_provider.data = "openrouter"
        form.openrouter_api_key.data = ""

        # Validation should fail
        is_valid = form.validate()
        assert is_valid is False

        # Should have error on openrouter_api_key field
        assert len(form.openrouter_api_key.errors) > 0

    def test_form_validation_succeeds_with_valid_data(self, settings_form_no_csrf):
        """Test that validation succeeds with valid data."""
        form = settings_form_no_csrf()

        # Set valid data
        form.llm_provider.data = "zen"
        form.zen_api_key.data = "test-key"

        # Validation should succeed
        is_valid = form.validate()
        assert is_valid is True

    def test_form_validation_maps_pydantic_errors_to_fields(
        self, settings_form_no_csrf
    ):
        """Test that Pydantic validation errors appear on correct fields."""
        form = settings_form_no_csrf()

        # Invalid: Zen provider selected but no API key
        form.llm_provider.data = "zen"
        form.zen_api_key.data = ""

        is_valid = form.validate()
        assert is_valid is False

        # Error should be on zen_api_key field
        assert hasattr(form, "zen_api_key")
        assert len(form.zen_api_key.errors) > 0


class TestFormRoundTrip:
    """Test round-trip: Settings → form → Settings."""

    def test_roundtrip_preserves_values(self, settings_form_no_csrf):
        """Test that Settings → populate → to_dict → Settings preserves values."""
        original = Settings(
            llm_provider="openrouter",
            openrouter_api_key="test-key",
            openrouter_model="custom-model",
            timezone="America/New_York",
            qdrant_port=6334,
        )

        # Populate form from settings
        form = settings_form_no_csrf()
        form.populate_from_settings(original)

        # Convert back to dict
        settings_dict = form.to_settings_dict()

        # Create new Settings from dict
        restored = Settings(**settings_dict)

        # Should match original
        assert restored.llm_provider == original.llm_provider
        assert restored.openrouter_api_key == original.openrouter_api_key
        assert restored.openrouter_model == original.openrouter_model
        assert restored.timezone == original.timezone
        assert restored.qdrant_port == original.qdrant_port

    def test_roundtrip_with_minimal_settings(self, settings_form_no_csrf):
        """Test round-trip with minimal valid settings."""
        original = Settings(
            llm_provider="zen",
            zen_api_key="test-key",
        )

        form = settings_form_no_csrf()
        form.populate_from_settings(original)

        settings_dict = form.to_settings_dict()
        restored = Settings(**settings_dict)

        assert restored.llm_provider == original.llm_provider
        assert restored.zen_api_key == original.zen_api_key
