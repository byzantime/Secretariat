import smtplib
from dataclasses import dataclass
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List
from typing import Optional


@dataclass
class SMTPConfig:
    """SMTP server configuration."""

    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    use_tls: bool = True
    timeout: int = 30

    @classmethod
    def from_dict(cls, cfg: Dict[str, Any]) -> "SMTPConfig":
        """Build SMTPConfig from an email config dict."""
        return cls(
            smtp_host=cfg.get("smtp_host", ""),
            smtp_port=cfg.get("smtp_port", 587),
            smtp_user=cfg.get("smtp_user", ""),
            smtp_password=cfg.get("smtp_password", ""),
            use_tls=cfg.get("use_tls", True),
            timeout=cfg.get("timeout", 30),
        )


class EmailService:
    def __init__(
        self, smtp_config: SMTPConfig | Dict[str, Any], logger: Optional[Any] = None
    ) -> None:
        if isinstance(smtp_config, dict):
            smtp_config = SMTPConfig.from_dict(smtp_config)
        self.smtp_config = smtp_config
        self.logger = logger
        self._validate_config()

    def _validate_config(self) -> None:
        """Ensure required SMTP configuration is present."""
        if not self.smtp_config.smtp_host:
            raise ValueError("SMTP host is required")
        if not self.smtp_config.smtp_user:
            raise ValueError("SMTP username is required")
        if not self.smtp_config.smtp_password:
            raise ValueError("SMTP password is required")

    @staticmethod
    def _normalise_list(items: Optional[List[str]]) -> List[str]:
        """Return a clean list of addresses (no None/blank strings)."""
        if not items:
            return []
        return [s.strip() for s in items if s and s.strip()]

    @staticmethod
    def _build_message(
        *,
        subject: str,
        from_address: str,
        to_recipients: List[str],
        cc_recipients: List[str],
        reply_to: Optional[str],
        headers: Dict[str, str],
        body: Optional[str],
        body_html: Optional[str],
    ) -> MIMEMultipart:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_address
        msg["To"] = ", ".join(to_recipients)
        if cc_recipients:
            msg["Cc"] = ", ".join(cc_recipients)
        if reply_to:
            msg["Reply-To"] = reply_to
        for k, v in headers.items():
            msg[k] = v
        if body:
            msg.attach(MIMEText(body, "plain"))
        if body_html:
            msg.attach(MIMEText(body_html, "html"))
        return msg

    @staticmethod
    def _attach_files(msg: MIMEMultipart, attachments: Optional[List[Path]]) -> None:
        if not attachments:
            return
        for file_path in attachments:
            if not file_path.exists():
                raise ValueError(f"Attachment not found: {file_path}")
            with open(file_path, "rb") as fh:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(fh.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition", f"attachment; filename={file_path.name}"
            )
            msg.attach(part)

    def _smtp_send(
        self, from_address: str, recipients: List[str], msg: MIMEMultipart
    ) -> None:
        with smtplib.SMTP(
            self.smtp_config.smtp_host,
            self.smtp_config.smtp_port,
            timeout=self.smtp_config.timeout,
        ) as server:
            if self.smtp_config.use_tls:
                server.starttls()
            server.login(self.smtp_config.smtp_user, self.smtp_config.smtp_password)
            server.sendmail(from_address, recipients, msg.as_string())

    def send_email(
        self,
        recipients: List[str],
        subject: str,
        body: str,
        *,
        from_address: Optional[str] = None,
        cc_addresses: Optional[List[str]] = None,
        bcc_addresses: Optional[List[str]] = None,
        body_html: Optional[str] = None,
        attachments: Optional[List[Path]] = None,
        reply_to: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> bool:
        """
        Send email via SMTP with full configuration support.
        """
        try:
            to = self._normalise_list(recipients)
            cc = self._normalise_list(cc_addresses)
            bcc = self._normalise_list(bcc_addresses)
            if not to:
                raise ValueError("At least one recipient address is required")

            sender = (from_address or self.smtp_config.smtp_user).strip()
            hdrs = headers or {}

            msg = self._build_message(
                subject=subject,
                from_address=sender,
                to_recipients=to,
                cc_recipients=cc,
                reply_to=reply_to,
                headers=hdrs,
                body=body,
                body_html=body_html,
            )

            self._attach_files(msg, attachments)

            all_recipients = to + cc + bcc
            self._smtp_send(sender, all_recipients, msg)

            if self.logger:
                self.logger.info(f"Email sent successfully to {all_recipients}")
            return True

        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to send email to {recipients}: {e}")
            raise smtplib.SMTPException(f"Failed to send email: {e}") from e
