import re

from flask_wtf import FlaskForm
from wtforms.fields import PasswordField
from wtforms.fields import StringField
from wtforms.validators import Email
from wtforms.validators import InputRequired
from wtforms.validators import Length
from wtforms.validators import ValidationError


class HostnameValidation:
    """Custom hostname validation class based on WTForms' internal HostnameValidation.

    Validates hostnames/domains without requiring a URL scheme, adapted from
    WTForms source code to handle our specific domain validation needs.
    """

    hostname_part = re.compile(r"^(xn-|[a-z0-9_]+)(-[a-z0-9_-]+)*$", re.IGNORECASE)
    tld_part = re.compile(r"^([a-z]{2,20}|xn--([a-z0-9]+-)*[a-z0-9]+)$", re.IGNORECASE)

    def __init__(self, require_tld=True, allow_ip=False):
        self.require_tld = require_tld
        self.allow_ip = allow_ip

    def __call__(self, hostname):
        if not hostname:
            return True  # Empty hostnames are handled by Optional/Required validators

        # Basic IP validation if allowed (simplified version)
        if self.allow_ip:
            # Simple IPv4 check
            parts = hostname.split(".")
            if len(parts) == 4 and all(
                part.isdigit() and 0 <= int(part) <= 255 for part in parts
            ):
                return True

        # Handle IDNA encoding
        try:
            hostname_bytes = hostname.encode("idna")
            hostname = hostname_bytes.decode("ascii")
        except (UnicodeError, UnicodeDecodeError):
            return False

        # Length check
        if len(hostname) > 253:
            return False

        # Split into parts and validate each
        parts = hostname.split(".")

        for part in parts:
            if not part or len(part) > 63:
                return False
            if not self.hostname_part.match(part):
                return False

        # TLD validation if required
        if self.require_tld and (len(parts) < 2 or not self.tld_part.match(parts[-1])):
            return False

        return True


def validate_domain_with_optional_port(message=None):
    """Custom validator for domain names with optional port numbers.

    Uses a custom HostnameValidation class (based on WTForms internal implementation)
    to properly validate domains while allowing optional port specifications.
    Accepts formats like:
    - domain.com
    - subdomain.domain.com
    - domain.com:8080
    - stun.l.google.com:19302
    """
    if message is None:
        message = "Invalid domain format"

    def _validate_domain_with_port(form, field):
        if not field.data or not field.data.strip():
            return

        domain_with_port = field.data.strip()

        # Split domain and port if port exists
        if ":" in domain_with_port:
            domain_part, port_part = domain_with_port.rsplit(":", 1)

            # Validate port is numeric and within valid range
            try:
                port_num = int(port_part)
                if not (1 <= port_num <= 65535):
                    raise ValidationError(
                        f"{message}: Port must be between 1 and 65535"
                    )
            except ValueError:
                raise ValidationError(f"{message}: Port must be numeric")
        else:
            domain_part = domain_with_port

        # Validate hostname using our custom validator
        hostname_validator = HostnameValidation(require_tld=True, allow_ip=False)
        if not hostname_validator(domain_part):
            raise ValidationError(f"{message}: Invalid domain name format")

    return _validate_domain_with_port


def validate_domain_or_ip(message=None):
    """Custom validator for domain names or IP addresses (no port allowed).

    Uses a custom HostnameValidation class to validate both domain names and IP addresses.
    Suitable for SIP domain configuration where both domains and IPs are valid.
    """
    if message is None:
        message = "Invalid domain or IP address format"

    def _validate_domain_or_ip(form, field):
        if not field.data or not field.data.strip():
            return

        domain_or_ip = field.data.strip()

        # Check for port (not allowed in this validator)
        if ":" in domain_or_ip:
            raise ValidationError(f"{message}: Port numbers not allowed")

        # Validate hostname or IP using our custom validator with IP support enabled
        hostname_validator = HostnameValidation(require_tld=True, allow_ip=True)
        if not hostname_validator(domain_or_ip):
            raise ValidationError(
                f"{message}: Invalid domain name or IP address format"
            )

    return _validate_domain_or_ip


class LoginForm(FlaskForm):
    email = StringField(
        "Email address", [Email(message="Invalid email address"), InputRequired()]
    )
    password = PasswordField("Password", [Length(min=10, max=256), InputRequired()])
