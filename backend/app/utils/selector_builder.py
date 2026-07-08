"""
SelectorBuilder — given a Playwright page and (x, y) viewport coordinates,
returns the best available selector for the element at that position plus
metadata needed to decide how to handle the action (click vs input overlay).
"""
import logging
from playwright.async_api import Page

logger = logging.getLogger("playwright_recorder.utils.selector_builder")

# JS that runs inside the browser to inspect the element at (x, y)
_INSPECT_JS = r"""
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
        const tag = e.tagName.toLowerCase();
        const itype = e.getAttribute('type') || '';

        // 1. id
        if (e.id) return { strategy: 'id', value: e.id };

        // 2. data-testid / data-id / data-cy (custom test attributes)
        for (const attr of ['data-testid', 'data-id', 'data-cy', 'data-qa']) {
            const v = e.getAttribute(attr);
            if (v) return { strategy: 'css', value: `[${attr}="${v}"]` };
        }

        // 3. aria-label
        const aria = e.getAttribute('aria-label');
        if (aria) return { strategy: 'css', value: `[aria-label="${CSS.escape(aria)}"]` };

        // 4. name
        const name = e.getAttribute('name');
        if (name) return { strategy: 'css', value: `${tag}[name="${name}"]` };

        // 5. label[for] — stable for <label> elements
        const forAttr = e.getAttribute('for');
        if (forAttr) return { strategy: 'css', value: `label[for="${CSS.escape(forAttr)}"]` };

        // 6. input[type=submit|button] by value (e.g. value="Sign in")
        if (tag === 'input' && (itype === 'submit' || itype === 'button')) {
            const val = e.getAttribute('value');
            if (val) {
                const q = `input[type="${itype}"][value="${val}"]`;
                if (document.querySelectorAll(q).length === 1)
                    return { strategy: 'css', value: q };
            }
        }

        // 7. role attribute (unique on page)
        const role = e.getAttribute('role');
        if (role) {
            const q = `[role="${role}"]`;
            if (document.querySelectorAll(q).length === 1)
                return { strategy: 'css', value: q };
            // role + title
            const title = e.getAttribute('title');
            if (title) {
                const q2 = `[role="${role}"][title="${title}"]`;
                if (document.querySelectorAll(q2).length === 1)
                    return { strategy: 'css', value: q2 };
            }
        }

        // 8. title attribute (unique)
        const title = e.getAttribute('title');
        if (title) {
            const q = `[title="${title}"]`;
            if (document.querySelectorAll(q).length === 1)
                return { strategy: 'css', value: q };
        }

        // 9. button/a/label by trimmed text content (unique → xpath text match)
        if (['button', 'a', 'label', 'span'].includes(tag)) {
            const txt = (e.textContent || '').trim().replace(/\s+/g, ' ');
            if (txt && txt.length >= 2 && txt.length <= 50) {
                const safe = txt.replace(/"/g, "'");
                const xp = `//${tag}[normalize-space(.)="${safe}"]`;
                try {
                    const res = document.evaluate(xp, document, null,
                        XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
                    if (res.snapshotLength === 1)
                        return { strategy: 'xpath', value: xp };
                } catch(_) {}
            }
        }

        // 10. CSS anchored to nearest ancestor with an id (shorter, more stable)
        function anchoredCSS(node) {
            let anchor = node.parentElement;
            while (anchor && anchor !== document.documentElement) {
                if (anchor.id) break;
                anchor = anchor.parentElement;
            }
            const hasId = anchor && anchor.id;
            const start = hasId ? anchor : document.body;
            const prefix = hasId ? `#${CSS.escape(anchor.id)}` : 'body';

            function relPath(n) {
                if (n === start) return prefix;
                const t = n.tagName.toLowerCase();
                const sibs = n.parentElement
                    ? Array.from(n.parentElement.children).filter(c => c.tagName === n.tagName)
                    : [n];
                const idx = sibs.indexOf(n) + 1;
                const sfx = sibs.length > 1 ? `:nth-of-type(${idx})` : '';
                return `${relPath(n.parentElement)} > ${t}${sfx}`;
            }
            try {
                const sel = relPath(node);
                if (document.querySelector(sel) === node) return sel;
            } catch(_) {}
            return null;
        }
        const anchored = anchoredCSS(target);
        if (anchored) return { strategy: 'css', value: anchored };

        // 11. XPath structural fallback (last resort)
        function getXPath(node) {
            if (!node || node === document.documentElement) return '/html';
            const t = node.tagName.toLowerCase();
            const sibs = node.parentElement
                ? Array.from(node.parentElement.children).filter(c => c.tagName === node.tagName)
                : [node];
            const idx = sibs.indexOf(node) + 1;
            return `${getXPath(node.parentElement)}/${t}${sibs.length > 1 ? `[${idx}]` : ''}`;
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

    // Compute occurrence_index: how many elements matching the same selector
    // appear before this element in DOM order (object-identity comparison).
    const sel = buildSelector(target);
    let occurrenceIndex = 0;
    try {
        let queryStr = '';
        if (sel.strategy === 'id') queryStr = `#${CSS.escape(sel.value)}`;
        else if (sel.strategy === 'css') queryStr = sel.value;
        // xpath: can't use querySelectorAll, leave index as 0
        if (queryStr) {
            const all = Array.from(document.querySelectorAll(queryStr));
            const idx = all.indexOf(target);
            if (idx > 0) occurrenceIndex = idx;
        }
    } catch(_) {}
    sel.occurrence_index = occurrenceIndex;

    return {
        tag,
        input_type: inputType || null,
        is_input: isTextInput,
        label: label || null,
        placeholder: target.getAttribute('placeholder') || null,
        current_value: target.value !== undefined ? target.value : (target.textContent || ''),
        is_password: inputType === 'password',
        selector: sel,
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
