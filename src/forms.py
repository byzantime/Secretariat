"""Dynamic form generation from Pydantic Settings model."""

from typing import Any
from typing import Dict
from typing import get_args
from typing import get_origin

from flask_wtf import FlaskForm
from pydantic import ValidationError
from pydantic.fields import FieldInfo
from wtforms import BooleanField
from wtforms import IntegerField
from wtforms import SelectField
from wtforms import StringField
from wtforms import validators

from src.models.settings import Settings


def _is_optional(annotation) -> bool:
    """Check if a type annotation is Optional."""
    return get_origin(annotation) is type(None) or (
        get_origin(annotation) in (type(None), type(None) | type)
        or (hasattr(annotation, "__args__") and type(None) in get_args(annotation))
    )


def _unwrap_optional(annotation):
    """Unwrap Optional type to get the inner type."""
    if hasattr(annotation, "__origin__"):
        origin = get_origin(annotation)
        if origin is type(None) | type:  # Union with None (Optional)
            args = get_args(annotation)
            non_none_args = [arg for arg in args if arg is not type(None)]
            if non_none_args:
                return non_none_args[0]
    return annotation


def _is_literal(annotation) -> bool:
    """Check if annotation is a Literal type."""
    return (
        hasattr(annotation, "__origin__")
        and annotation.__origin__.__name__ == "Literal"
    )


def _get_wtform_field_for_pydantic_field(
    field_name: str, field_info: FieldInfo, annotation
):
    """Convert a Pydantic field to a WTForms field."""
    # Get field metadata
    description = field_info.description or field_name.replace("_", " ").title()
    default = field_info.default if field_info.default is not None else ""

    # Check if field is Optional and unwrap if needed
    is_optional = _is_optional(annotation)
    annotation = _unwrap_optional(annotation)

    # Build validators list
    field_validators = []
    if not is_optional and annotation is not bool:
        field_validators.append(validators.DataRequired())

    # Check for Literal annotation (for choices)
    if _is_literal(annotation):
        choices = [(choice, choice.title()) for choice in get_args(annotation)]
        return SelectField(
            description,
            choices=choices,
            default=default,
            validators=field_validators,
        )

    # Map Python types to WTForms fields
    if annotation is bool:
        return BooleanField(description, default=default)
    elif annotation is int:
        return IntegerField(description, default=default, validators=field_validators)
    else:
        # Default to StringField for strings and optional strings
        return StringField(description, default=default, validators=field_validators)


def _validate_with_pydantic(self, extra_validators=None, skip_csrf=False):
    """Custom validation using Pydantic model validation.

    Args:
        extra_validators: Additional validators to run
        skip_csrf: If True, skips WTForms validation (including CSRF). Useful for
                   validating existing settings on GET requests.
    """
    # Track validation results from both WTForms and Pydantic
    wtforms_valid = True
    pydantic_valid = True

    # Call parent validation only if not skipping CSRF
    # Don't return early - collect all errors from both validators
    if not skip_csrf:
        wtforms_valid = FlaskForm.validate(self, extra_validators)

    # Use Pydantic model validation as single source of truth
    try:
        settings_dict = self.to_settings_dict()
        Settings(**settings_dict)
    except ValidationError as e:
        pydantic_valid = False
        # Map Pydantic validation errors to form field errors
        for error in e.errors():
            field_name = error["loc"][0] if error["loc"] else None
            error_msg = error["msg"]

            if field_name and hasattr(self, field_name):
                field = getattr(self, field_name)
                # Convert field.errors tuple to list if needed, then append
                if isinstance(field.errors, tuple):
                    field.errors = list(field.errors)
                field.errors.append(error_msg)
                # Also add to form.errors dict for error summary
                if field_name not in self.errors:
                    self.errors[field_name] = []
                self.errors[field_name].append(error_msg)
            elif not field_name:
                # Model-level validation error without specific field
                # Add to a general "_schema" error list for display in error summary
                if "_schema" not in self.errors:
                    self.errors["_schema"] = []
                self.errors["_schema"].append(error_msg)

    # Return True only if both validators passed
    return wtforms_valid and pydantic_valid


def _populate_from_settings(self, settings: Settings):
    """Populate form fields from settings model."""
    for field_name in Settings.model_fields.keys():
        if hasattr(self, field_name):
            value = getattr(settings, field_name)
            if value is not None:
                field = getattr(self, field_name)
                field.data = value


def _to_settings_dict(self) -> Dict[str, Any]:
    """Convert form data to settings dictionary."""
    settings_dict = {}
    for field_name, field in self._fields.items():
        # Skip CSRF token field
        if field_name == "csrf_token":
            continue

        value = field.data
        # Include all values, even empty strings, so Pydantic validation can catch missing required fields
        # Convert empty strings to None for optional fields
        if value == "":
            settings_dict[field_name] = None
        elif value is not None:
            settings_dict[field_name] = value
    return settings_dict


def create_settings_form() -> type[FlaskForm]:
    """Dynamically create a settings form from the Pydantic Settings model."""
    # Fields to exclude from the form (internal/hidden fields)
    excluded_fields = {"debug", "log_level", "secret_key", "database_name", "data_dir"}

    # Build form fields dynamically
    form_fields = {}

    for field_name, field_info in Settings.model_fields.items():
        if field_name in excluded_fields:
            continue

        # Get the field annotation
        annotation = field_info.annotation

        # Create the WTForms field
        wtf_field = _get_wtform_field_for_pydantic_field(
            field_name, field_info, annotation
        )
        form_fields[field_name] = wtf_field

    # Create the form class dynamically
    SettingsFormClass = type("SettingsForm", (FlaskForm,), form_fields)

    # Add custom methods to the form class
    SettingsFormClass.validate = _validate_with_pydantic
    SettingsFormClass.populate_from_settings = _populate_from_settings
    SettingsFormClass.to_settings_dict = _to_settings_dict

    return SettingsFormClass


# Create the form class at module level
SettingsForm = create_settings_form()
