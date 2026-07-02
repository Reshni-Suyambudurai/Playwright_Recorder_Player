"""
Playwright Browser Service (Synchronous API)
Handles browser automation, screenshot capture, and DOM extraction
No asyncio complexity - simple, straightforward synchronous calls
"""
import logging
import traceback
import threading
import asyncio
import sys
import subprocess
import queue
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright

# Configure logging
logger = logging.getLogger(__name__)

# Set Windows event loop policy at module import time (before any asyncio contexts)
# Use ProactorEventLoopPolicy which supports subprocess on Windows
if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        logger.debug("Windows detected: Set event loop policy to WindowsProactorEventLoopPolicy at import time")
    except Exception as e:
        logger.warning(f"Could not set event loop policy: {e}")

class BrowserManager:
    def __init__(self):
        self.browser = None
        self.page = None
        self.playwright = None
        self.screenshots_dir = Path(__file__).parent.parent / "screenshots"
        self.screenshots_dir.mkdir(exist_ok=True)
        self._lock = threading.Lock()
        self._init_event = threading.Event()
        self._init_result = None
        self._browser_thread = None
        self._operation_queue = queue.Queue()
        self._running = False
        
        self.viewport = {
            "width": 1280,
            "height": 720
        }

    def _browser_thread_main(self):
        """Main loop for browser thread"""
        try:
            logger.info("Browser thread started")
            
            if sys.platform == "win32":
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                logger.debug("Created fresh ProactorEventLoop for browser thread")
            
            self.playwright = sync_playwright().start()
            logger.debug("Playwright context started")
            self.browser = self.playwright.chromium.launch(headless=True)
            logger.debug("Chromium browser launched")
            self.page = self.browser.new_page(viewport=self.viewport)
            logger.info(f"Browser initialized with viewport {self.viewport}")
            
            self._init_result = {"status": "success", "message": "Browser initialized"}
            self._running = True
            self._init_event.set()
            
            while self._running:
                try:
                    operation, args, result_event = self._operation_queue.get(timeout=1)
                    logger.debug(f"Processing: {operation}")
                    try:
                        result = self._execute_operation(operation, args)
                        result_event.result = result
                    except Exception as e:
                        logger.error(f"Operation error: {str(e)}")
                        result_event.result = {"status": "error", "message": str(e)}
                    finally:
                        result_event.set()
                except queue.Empty:
                    continue
                except Exception as e:
                    logger.error(f"Browser thread error: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Fatal error: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            self._init_result = {"status": "error", "message": str(e)}
            self._init_event.set()
        finally:
            self._cleanup_browser()

    def _execute_operation(self, operation, args):
        """Execute operation in browser thread"""
        if operation == "open_url":
            url = args[0]
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            logger.info(f"Navigating to: {url}")
            result = self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            return {
                "status": "success",
                "url": str(result.url) if result else url,
                "message": "URL opened successfully"
            }
        
        elif operation == "screenshot":
            filename = args[0] if args else f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            screenshot_path = self.screenshots_dir / filename
            self.page.screenshot(path=str(screenshot_path))
            return {
                "status": "success",
                "filename": filename,
                "screenshot_path": str(screenshot_path)
            }
        
        elif operation == "get_dom":
            html = self.page.content()
            viewport_size = self.page.evaluate("() => ({ width: window.innerWidth, height: window.innerHeight })")
            return {
                "status": "success",
                "html": html,
                "viewport": {**self.viewport, **viewport_size}
            }
        
        elif operation == "get_element_at_coordinates":
            x, y = args[0], args[1]
            result = self.page.evaluate(f"""
                (() => {{
                    const element = document.elementFromPoint({x}, {y});
                    if (!element) return {{ error: 'No element found' }};
                    
                    function getSelector(el) {{
                        if (el.id) return '#' + el.id;
                        let path = [];
                        while (el.parentElement) {{
                            let selector = el.tagName.toLowerCase();
                            if (el.id) {{
                                selector += '#' + el.id;
                                path.unshift(selector);
                                break;
                            }} else {{
                                let sibling = el;
                                let nth = 1;
                                while (sibling = sibling.previousElementSibling) {{
                                    if (sibling.tagName.toLowerCase() === selector) nth++;
                                }}
                                if (nth > 1) selector += `:nth-of-type(${{nth}})`;
                                path.unshift(selector);
                            }}
                            el = el.parentElement;
                        }}
                        return path.join(' > ');
                    }}
                    
                    function getXPath(el) {{
                        if (el.id !== '')
                            return "//*[@id='" + el.id + "']";
                        if (el === document.body)
                            return "//" + el.tagName.toLowerCase();
                        var ix = 0;
                        var siblings = el.parentNode.childNodes;
                        for (var i = 0; i < siblings.length; i++) {{
                            var sibling = siblings[i];
                            if (sibling === el)
                                return getXPath(el.parentNode) + "/" + el.tagName.toLowerCase() + "[" + (ix + 1) + "]";
                            if (sibling.nodeType === 1 && sibling.tagName.toLowerCase() === el.tagName.toLowerCase())
                                ix++;
                        }}
                    }}
                    
                    const rect = element.getBoundingClientRect();
                    
                    return {{
                        tagName: element.tagName,
                        text: element.textContent.substring(0, 100),
                        id: element.id || '',
                        class: element.className || '',
                        selector: getSelector(element),
                        xpath: getXPath(element),
                        boundingRect: {{
                            x: Math.round(rect.left),
                            y: Math.round(rect.top),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height)
                        }},
                        attributes: {{
                            href: element.getAttribute('href'),
                            name: element.getAttribute('name'),
                            type: element.getAttribute('type'),
                            placeholder: element.getAttribute('placeholder'),
                            value: element.getAttribute('value'),
                            title: element.getAttribute('title'),
                            label: element.getAttribute('aria-label')
                        }},
                        innerHTML: element.innerHTML.substring(0, 500),
                        outerHTML: element.outerHTML.substring(0, 500)
                    }};
                }})()
            """)
            return {
                "status": "success",
                "element": result,
                "coordinates": {"x": x, "y": y}
            }
        
        else:
            return {"status": "error", "message": f"Unknown operation: {operation}"}

    def _cleanup_browser(self):
        """Clean up browser resources"""
        try:
            if self.page:
                self.page.close()
                logger.debug("Page closed")
            if self.browser:
                self.browser.close()
                logger.debug("Browser closed")
            if self.playwright:
                self.playwright.stop()
                logger.debug("Playwright context stopped")
        except Exception as e:
            logger.error(f"Cleanup error: {str(e)}")

    def _execute_in_browser_thread(self, operation, args=None):
        """Execute operation in browser thread"""
        if args is None:
            args = []
        result_event = threading.Event()
        self._operation_queue.put((operation, args, result_event))
        if not result_event.wait(timeout=60):
            return {"status": "error", "message": "Operation timed out"}
        return result_event.result

    def initialize(self):
        """Initialize browser"""
        with self._lock:
            if self._browser_thread and self._browser_thread.is_alive():
                return {"status": "success", "message": "Browser already initialized"}
            self._browser_thread = threading.Thread(target=self._browser_thread_main, daemon=False)
            self._browser_thread.start()
            self._init_event.wait(timeout=60)
            if self._init_result is None:
                return {"status": "error", "message": "Browser initialization timed out"}
            return self._init_result

    def open_url(self, url: str):
        """Open URL"""
        return self._execute_in_browser_thread("open_url", [url])

    def take_screenshot(self, name: str = None):
        """Take screenshot"""
        if name is None:
            name = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        return self._execute_in_browser_thread("screenshot", [name])

    def get_dom(self):
        """Fetch page DOM"""
        return self._execute_in_browser_thread("get_dom", [])

    def get_element_at_coordinates(self, x: int, y: int):
        """Get element at coordinates"""
        return self._execute_in_browser_thread("get_element_at_coordinates", [x, y])

    def close(self):
        """Close browser"""
        try:
            logger.info("Closing browser")
            self._running = False
            if self._browser_thread:
                self._browser_thread.join(timeout=10)
            logger.info("Browser closed successfully")
            return {"status": "success", "message": "Browser closed"}
        except Exception as e:
            logger.error(f"Error closing browser: {str(e)}")
            return {"status": "error", "message": str(e)}


# Global instance
browser_manager = BrowserManager()

