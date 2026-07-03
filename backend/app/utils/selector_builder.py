"""
SelectorBuilder — given a Playwright page and (x, y) viewport coordinates,
returns the best available selector for the element at that position plus
metadata needed to decide how to handle the action (click vs input overlay).
"""
import logging
from playwright.async_api import Page

logger = logging.getLogger("playwright_recorder.utils.selector_builder")

# JS that runs inside the browser to inspect the element at (x, y)
_INSPECT_JS = """
(args) => {
    const { x, y } = args;
    const el = document.elementFromPoint(x, y);
    if (!el) return null;

    // Walk up to find the most meaningful interactive element
    function findInteractive(node) {
        const tags = ['a', 'button', 'input', 'textarea', 'select', 'label'];
        let cur = node;
        for (let i = 0; i < 5 && cur && cur !== document.body; i++) {
            if (tags.includes(cur.tagName.toLowerCase())) return cur;
            cur = cur.parentElement;
        }
        return node;
    }

    const target = findInteractive(el);

    // ── Selector priority ──────────────────────────────────────────
    function buildSelector(e) {
        // 1. id
        if (e.id) return { strategy: 'id', value: e.id };

        // 2. data-testid
        const testid = e.getAttribute('data-testid');
        if (testid) return { strategy: 'css', value: `[data-testid="${testid}"]` };

        // 3. aria-label
        const aria = e.getAttribute('aria-label');
        if (aria) return { strategy: 'css', value: `[aria-label="${CSS.escape(aria)}"]` };

        // 4. name (inputs/selects)
        const name = e.getAttribute('name');
        if (name) return { strategy: 'css', value: `${e.tagName.toLowerCase()}[name="${name}"]` };

        // 5. CSS nth-of-type chain (walk up 4 levels)
        function nthSelector(node) {
            if (!node || node === document.documentElement) return '';
            const tag = node.tagName.toLowerCase();
            const siblings = node.parentElement
                ? Array.from(node.parentElement.children).filter(c => c.tagName === node.tagName)
                : [node];
            const idx = siblings.indexOf(node) + 1;
            const suffix = siblings.length > 1 ? `:nth-of-type(${idx})` : '';
            const parent = nthSelector(node.parentElement);
            return parent ? `${parent} > ${tag}${suffix}` : `${tag}${suffix}`;
        }
        const cssSel = nthSelector(target);
        if (cssSel) {
            try {
                if (document.querySelector(cssSel) === target)
                    return { strategy: 'css', value: cssSel };
            } catch(_) {}
        }

        // 6. XPath fallback
        function getXPath(node) {
            if (!node || node === document.documentElement) return '/html';
            const tag = node.tagName.toLowerCase();
            const siblings = node.parentElement
                ? Array.from(node.parentElement.children).filter(c => c.tagName === node.tagName)
                : [node];
            const idx = siblings.indexOf(node) + 1;
            const suffix = siblings.length > 1 ? `[${idx}]` : '';
            return `${getXPath(node.parentElement)}/${tag}${suffix}`;
        }
        return { strategy: 'xpath', value: getXPath(target) };
    }

    const tag = target.tagName.toLowerCase();
    const inputType = target.getAttribute('type') || '';
    const isTextInput = (
        (tag === 'input' && !['submit','button','checkbox','radio','file','image','range','color'].includes(inputType))
        || tag === 'textarea'
        || target.getAttribute('contenteditable') === 'true'
    );

    // Label: aria-label > associated <label> > placeholder > title
    let label = target.getAttribute('aria-label') || target.getAttribute('placeholder') || target.getAttribute('title') || null;
    if (!label) {
        const id = target.id;
        if (id) {
            const lbl = document.querySelector(`label[for="${id}"]`);
            if (lbl) label = lbl.textContent.trim();
        }
    }

    return {
        tag,
        input_type: inputType || null,
        is_input: isTextInput,
        label: label || null,
        placeholder: target.getAttribute('placeholder') || null,
        current_value: target.value !== undefined ? target.value : (target.textContent || ''),
        is_password: inputType === 'password',
        selector: buildSelector(target),
        frame_selector: null
    };
}
"""


async def build_selector(page: Page, x: int, y: int) -> dict | None:
    """
    Inspect the DOM element at (x, y) and return selector + metadata.
    Returns None if no element found at that position.
    """
    try:
        result = await page.evaluate(_INSPECT_JS, {"x": x, "y": y})
        if result:
            logger.debug(f"Selector built at ({x},{y}): {result['selector']} is_input={result['is_input']}")
        return result
    except Exception as e:
        logger.warning(f"selector_builder failed at ({x},{y}): {e}")
        return None
