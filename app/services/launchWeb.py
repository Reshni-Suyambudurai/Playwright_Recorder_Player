"""
Playwright Browser Service (Synchronous API)
Handles browser automation, screenshot capture, and DOM extraction
No asyncio complexity - simple, straightforward synchronous calls
"""
import logging
import traceback
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright

# Configure logging
logger = logging.getLogger(__name__)

class BrowserManager:
    def __init__(self):
        self.browser = None
        self.page = None
        self.playwright = None
        self.screenshots_dir = Path(__file__).parent.parent / "screenshots"
        self.screenshots_dir.mkdir(exist_ok=True)
        
        # Predefined viewport settings
        self.viewport = {
            "width": 1280,
            "height": 720
        }

    def initialize(self):
        """Initialize Playwright browser (Synchronous)"""
        try:
            logger.info("Starting Playwright initialization")
            self.playwright = sync_playwright().start()
            logger.debug("Playwright context started")
            self.browser = self.playwright.chromium.launch(headless=True)
            logger.debug("Chromium browser launched")
            self.page = self.browser.new_page(viewport=self.viewport)
            logger.info(f"Browser initialized with viewport {self.viewport}")
            return {"status": "success", "message": "Browser initialized"}
        except Exception as e:
            logger.error(f"Error during browser initialization: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {"status": "error", "message": str(e)}

    def close(self):
        """Close browser and cleanup"""
        try:
            logger.info("Closing browser")
            if self.page:
                self.page.close()
                logger.debug("Page closed")
            if self.browser:
                self.browser.close()
                logger.debug("Browser closed")
            if self.playwright:
                self.playwright.stop()
                logger.debug("Playwright context stopped")
            logger.info("Browser closed successfully")
            return {"status": "success", "message": "Browser closed"}
        except Exception as e:
            logger.error(f"Error closing browser: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {"status": "error", "message": str(e)}

    def open_url(self, url: str):
        """Open a URL in the browser"""
        if not self.page:
            logger.error("Attempted to open URL but browser not initialized")
            return {"status": "error", "message": "Browser not initialized"}
        
        try:
            logger.info(f"Opening URL: {url}")
            # Ensure URL has protocol
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
                logger.debug(f"Added https protocol to URL: {url}")
            
            logger.debug(f"Navigating to: {url}")
            self.page.goto(url, wait_until="networkidle")
            logger.info(f"Successfully navigated to: {url}")
            return {"status": "success", "url": url}
        except Exception as e:
            logger.error(f"Error opening URL {url}: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {"status": "error", "message": str(e)}

    def take_screenshot(self, name: str = None):
        """Take a screenshot and save to screenshots folder"""
        if not self.page:
            return {"status": "error", "message": "Browser not initialized"}
        
        try:
            if name is None:
                name = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            
            screenshot_path = self.screenshots_dir / name
            self.page.screenshot(path=str(screenshot_path))
            
            return {
                "status": "success",
                "screenshot_path": str(screenshot_path),
                "filename": name
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_dom(self):
        """Fetch the DOM of the current page"""
        if not self.page:
            return {"status": "error", "message": "Browser not initialized"}
        
        try:
            # Get HTML content
            html = self.page.content()
            
            # Get viewport dimensions
            viewport_size = self.page.evaluate("() => ({ width: window.innerWidth, height: window.innerHeight })")
            
            return {
                "status": "success",
                "html": html,
                "viewport": {
                    **self.viewport,
                    "actual_inner_width": viewport_size["width"],
                    "actual_inner_height": viewport_size["height"]
                }
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_element_at_coordinates(self, x: int, y: int):
        """
        Get element information at specific coordinates (x, y)
        Returns: selector, xpath, element name, and element details
        """
        if not self.page:
            return {"status": "error", "message": "Browser not initialized"}
        
        try:
            # Execute script to find element at coordinates
            result = self.page.evaluate(f"""
            (() => {{
                const element = document.elementFromPoint({x}, {y});
                
                if (!element) {{
                    return {{ error: 'No element found at coordinates' }};
                }}
                
                // Generate CSS selector
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
                            if (nth > 1) selector += ':nth-of-type(' + nth + ')';
                        }}
                        path.unshift(selector);
                        el = el.parentElement;
                    }}
                    return path.join(' > ');
                }}
                
                // Generate XPath
                function getXPath(el) {{
                    if (el.id)
                        return "//*[@id='" + el.id + "']";
                    if (el === document.body)
                        return "/body";
                    
                    var index = 0;
                    var sibling = el.previousSibling;
                    while (sibling) {{
                        if (sibling.nodeType === 1 && sibling.tagName.toLowerCase() === el.tagName.toLowerCase())
                            index++;
                        sibling = sibling.previousSibling;
                    }}
                    
                    var tagName = el.tagName.toLowerCase();
                    var position = (index + 1);
                    var parentPath = getXPath(el.parentNode);
                    return parentPath + '/' + tagName + '[' + position + ']';
                }}
                
                return {{
                    success: true,
                    tagName: element.tagName,
                    className: element.className,
                    id: element.id,
                    text: element.textContent.substring(0, 100),
                    selector: getSelector(element),
                    xpath: getXPath(element),
                    attributes: {{
                        href: element.getAttribute('href'),
                        name: element.getAttribute('name'),
                        type: element.getAttribute('type'),
                        placeholder: element.getAttribute('placeholder'),
                        value: element.getAttribute('value')
                    }},
                    html: element.outerHTML.substring(0, 500),
                    boundingRect: element.getBoundingClientRect()
                }};
            }})()
            """)
            
            if "error" in result:
                return {"status": "error", "message": result["error"], "coordinates": {"x": x, "y": y}}
            
            return {
                "status": "success",
                "coordinates": {"x": x, "y": y},
                "element": result
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": str(e),
                "coordinates": {"x": x, "y": y}
            }

# Global browser manager instance
browser_manager = BrowserManager()
