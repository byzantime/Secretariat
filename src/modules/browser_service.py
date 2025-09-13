"""Browser automation service using Selenium WebDriver."""

import asyncio
import base64
import os
import tempfile
from typing import Dict
from typing import Optional

from quart import current_app
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class BrowserService:
    """Service for browser automation with Selenium."""

    def __init__(self, app=None):
        self.driver: Optional[webdriver.Chrome] = None
        self.temp_dir = None
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialize the browser service with app."""
        self.app = app
        app.extensions["browser"] = self
        app.logger.info("BrowserService initialized")

    def _create_driver(self, headless: bool = True) -> webdriver.Chrome:
        """Create a Chrome WebDriver instance with optimized settings."""
        options = Options()

        if headless:
            options.add_argument("--headless")

        # Basic anti-detection measures
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        # User agent to appear more human-like
        options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        # Window size for consistent screenshots
        options.add_argument("--window-size=1280,720")

        # Create temp directory for downloads if needed
        if not self.temp_dir:
            self.temp_dir = tempfile.mkdtemp()

        prefs = {
            "download.default_directory": self.temp_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
        }
        options.add_experimental_option("prefs", prefs)

        try:
            driver = webdriver.Chrome(options=options)

            # Execute script to remove webdriver property
            driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            return driver
        except Exception as e:
            current_app.logger.error(f"Failed to create Chrome driver: {e}")
            raise

    async def start_session(self, headless: bool = True) -> bool:
        """Start a new browser session."""
        try:
            if self.driver:
                await self.close_session()

            # Run driver creation in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            self.driver = await loop.run_in_executor(
                None, self._create_driver, headless
            )

            current_app.logger.info("Browser session started")
            return True
        except Exception as e:
            current_app.logger.error(f"Failed to start browser session: {e}")
            return False

    async def close_session(self):
        """Close the current browser session."""
        if self.driver:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self.driver.quit)
                current_app.logger.info("Browser session closed")
            except Exception as e:
                current_app.logger.error(f"Error closing browser session: {e}")
            finally:
                self.driver = None

    async def navigate_to(self, url: str) -> bool:
        """Navigate to a URL."""
        if not self.driver:
            return False

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.driver.get, url)
            current_app.logger.info(f"Navigated to: {url}")
            return True
        except Exception as e:
            current_app.logger.error(f"Failed to navigate to {url}: {e}")
            return False

    async def get_screenshot_base64(self) -> Optional[str]:
        """Take a screenshot and return as base64 string."""
        if not self.driver:
            return None

        try:
            loop = asyncio.get_event_loop()
            screenshot_png = await loop.run_in_executor(
                None, self.driver.get_screenshot_as_png
            )
            screenshot_base64 = base64.b64encode(screenshot_png).decode("utf-8")
            return screenshot_base64
        except Exception as e:
            current_app.logger.error(f"Failed to take screenshot: {e}")
            return None

    async def get_page_info(self) -> Dict:
        """Get current page information."""
        if not self.driver:
            return {}

        try:
            loop = asyncio.get_event_loop()

            def _get_info():
                return {
                    "url": self.driver.current_url,
                    "title": self.driver.title,
                    "page_source_length": len(self.driver.page_source),
                }

            info = await loop.run_in_executor(None, _get_info)
            return info
        except Exception as e:
            current_app.logger.error(f"Failed to get page info: {e}")
            return {}

    async def find_element_by_text(self, text: str, tag: str = "*") -> bool:
        """Find element by text content."""
        if not self.driver:
            return False

        try:
            loop = asyncio.get_event_loop()

            def _find_element():
                xpath = f"//{tag}[contains(text(), '{text}')]"
                element = self.driver.find_element(By.XPATH, xpath)
                return element is not None

            found = await loop.run_in_executor(None, _find_element)
            return found
        except Exception:
            return False

    async def click_element_by_text(self, text: str, tag: str = "*") -> bool:
        """Click element by text content."""
        if not self.driver:
            return False

        try:
            loop = asyncio.get_event_loop()

            def _click_element():
                xpath = f"//{tag}[contains(text(), '{text}')]"
                wait = WebDriverWait(self.driver, 10)
                element = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
                element.click()
                return True

            success = await loop.run_in_executor(None, _click_element)
            current_app.logger.info(f"Clicked element with text: {text}")
            return success
        except Exception as e:
            current_app.logger.error(f"Failed to click element with text '{text}': {e}")
            return False

    async def type_in_field(
        self, field_identifier: str, text: str, by_type: str = "name"
    ) -> bool:
        """Type text in an input field."""
        if not self.driver:
            return False

        try:
            loop = asyncio.get_event_loop()

            def _type_text():
                by_mapping = {
                    "name": By.NAME,
                    "id": By.ID,
                    "class": By.CLASS_NAME,
                    "xpath": By.XPATH,
                }

                by_method = by_mapping.get(by_type, By.NAME)
                wait = WebDriverWait(self.driver, 10)
                element = wait.until(
                    EC.presence_of_element_located((by_method, field_identifier))
                )
                element.clear()
                element.send_keys(text)
                return True

            success = await loop.run_in_executor(None, _type_text)
            current_app.logger.info(f"Typed in field {field_identifier}")
            return success
        except Exception as e:
            current_app.logger.error(f"Failed to type in field {field_identifier}: {e}")
            return False

    async def wait_for_element(
        self, selector: str, by_type: str = "css", timeout: int = 10
    ) -> bool:
        """Wait for element to appear."""
        if not self.driver:
            return False

        try:
            loop = asyncio.get_event_loop()

            def _wait_for_element():
                by_mapping = {
                    "css": By.CSS_SELECTOR,
                    "id": By.ID,
                    "name": By.NAME,
                    "class": By.CLASS_NAME,
                    "xpath": By.XPATH,
                }

                by_method = by_mapping.get(by_type, By.CSS_SELECTOR)
                wait = WebDriverWait(self.driver, timeout)
                element = wait.until(
                    EC.presence_of_element_located((by_method, selector))
                )
                return element is not None

            found = await loop.run_in_executor(None, _wait_for_element)
            return found
        except Exception:
            return False

    def __del__(self):
        """Cleanup on destruction."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass

        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                import shutil

                shutil.rmtree(self.temp_dir)
            except Exception:
                pass
