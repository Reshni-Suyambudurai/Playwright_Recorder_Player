"""
SelectorBuilder — given a Playwright page and (x, y) viewport coordinates,
returns the best available selector for the element at that position plus
metadata needed to decide how to handle the action (click vs input overlay).


page.evaluate() executes JavaScript inside the browser page and returns the result back to Python.

| Priority | Selector Type                                 | Example                                |
| -------- | --------------------------------------------- | -------------------------------------- |
| 1        | **id**                                        | `#loginBtn`                            |
| 2        | **data-testid / data-id / data-cy / data-qa** | `[data-testid="submit"]`               |
| 3        | **aria-label**                                | `[aria-label="Username"]`              |
| 4        | **name**                                      | `input[name="username"]`               |
| 5        | **label[for]**                                | `label[for="email"]`                   |
| 6        | **input[type=submit/button] + value**         | `input[type="submit"][value="Login"]`  |
| 7        | **role** (or role + title)                    | `[role="button"]`                      |
| 8        | **title**                                     | `[title="Refresh"]`                    |
| 9        | **Text-based XPath**                          | `//button[normalize-space(.)="Login"]` |
| 10       | **Anchored CSS Path**                         | `#form > button > span`                |
| 11       | **Full XPath (last resort)**                  | `/html/body/div/form/button[1]`        |

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
    function isStableId(value) {
        if (!value) return false;
        if (value.startsWith(':') || value.includes(':')) return false;
        if (value.endsWith('-')) return false;
        if (/^__next$/i.test(value) || /^__nuxt$/i.test(value) || /^root$/i.test(value) || /^app$/i.test(value)) return false;
        if (/^(mui|headlessui|radix)-/i.test(value)) return false;
        return true;
    }

    function isUniqueCss(selector, expected = null) {
        try {
            const all = Array.from(document.querySelectorAll(selector));
            if (all.length !== 1) return false;
            return expected ? all[0] === expected : true;
        } catch (_) {
            return false;
        }
    }

    function isInteractiveCandidate(node) {
        if (!node || node.nodeType !== Node.ELEMENT_NODE) return false;
        const tag = node.tagName.toLowerCase();
        const role = (node.getAttribute('role') || '').toLowerCase();
        if (['a', 'button', 'input', 'textarea', 'select', 'label', 'option'].includes(tag)) return true;
        if (['button', 'link', 'tab', 'menuitem', 'option', 'checkbox', 'radio', 'switch', 'combobox', 'listbox'].includes(role)) return true;
        if (node.hasAttribute('aria-label') || node.hasAttribute('data-testid') || node.hasAttribute('data-id') || node.hasAttribute('data-cy') || node.hasAttribute('data-qa')) return true;
        if (node.hasAttribute('aria-haspopup') || node.hasAttribute('aria-expanded')) return true;
        if (node.hasAttribute('onclick')) return true;
        const tabIndex = node.getAttribute('tabindex');
        if (tabIndex !== null && tabIndex !== '-1') return true;
        if ((node.textContent || '').trim().length > 0 && ['div', 'span', 'li'].includes(tag)) return true;
        return false;
    }

    function normalizeText(value) {
        return (value || '').trim().replace(/\s+/g, ' ').toLowerCase();
    }

    function classHints(node) {
        const raw = (node.getAttribute('class') || '').split(/\s+/).filter(Boolean);
        return raw.filter(token => {
            if (!token) return false;
            if (token.length > 32) return false;
            if (/^(mui-style-|css-|jss|sc-)/i.test(token)) return false;
            if (/^Mui[A-Z]/.test(token)) return false;
            return /[a-zA-Z]/.test(token);
        }).slice(0, 6);
    }

    function findBestTextTarget(node) {
        let cur = node;
        for (let i = 0; i < 6 && cur && cur !== document.body; i++) {
            const txt = (cur.textContent || '').trim().replace(/\s+/g, ' ');
            if (txt && txt.length >= 2 && txt.length <= 50) return cur;
            cur = cur.parentElement;
        }
        return node;
    }

    function findInteractive(node) {
        let cur = node;
        for (let i = 0; i < 6 && cur && cur !== document.body; i++) {
            if (isInteractiveCandidate(cur)) return cur;
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
        if (e.id && isStableId(e.id) && isUniqueCss(`#${CSS.escape(e.id)}`, e)) {
            return { strategy: 'id', value: e.id };
        }

        // 2. data-testid / data-id / data-cy (custom test attributes)
        for (const attr of ['data-testid', 'data-id', 'data-cy', 'data-qa']) {
            const v = e.getAttribute(attr);
            if (!v) continue;
            const q = `[${attr}="${CSS.escape(v)}"]`;
            if (isUniqueCss(q, e)) return { strategy: 'css', value: q };
        }

        // 3. aria-label
        const aria = e.getAttribute('aria-label');
        if (aria) {
            const q = `[aria-label="${CSS.escape(aria)}"]`;
            if (isUniqueCss(q, e)) return { strategy: 'css', value: q };
            const qTag = `${tag}[aria-label="${CSS.escape(aria)}"]`;
            if (isUniqueCss(qTag, e)) return { strategy: 'css', value: qTag };
        }

        // 4. name
        const name = e.getAttribute('name');
        if (name) {
            const q = `${tag}[name="${CSS.escape(name)}"]`;
            if (isUniqueCss(q, e)) return { strategy: 'css', value: q };
        }

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
            const q = `[title="${CSS.escape(title)}"]`;
            if (document.querySelectorAll(q).length === 1)
                return { strategy: 'css', value: q };
            const qTag = `${tag}[title="${CSS.escape(title)}"]`;
            if (isUniqueCss(qTag, e))
                return { strategy: 'css', value: qTag };
        }

        // 9. Interactive elements by trimmed text content (unique → xpath text match)
        const textTarget = findBestTextTarget(e);
        const textTag = textTarget.tagName.toLowerCase();
        if (['button', 'a', 'label', 'span', 'div', 'li'].includes(textTag)) {
            const txt = (textTarget.textContent || '').trim().replace(/\s+/g, ' ');
            if (txt && txt.length >= 2 && txt.length <= 50) {
                const safe = txt.replace(/"/g, "'");
                const exactXp = `//${textTag}[normalize-space(.)="${safe}"]`;
                const containsXp = `//${textTag}[contains(normalize-space(.),"${safe}")]`;
                try {
                    const res = document.evaluate(exactXp, document, null,
                        XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
                    if (res.snapshotLength === 1)
                        return { strategy: 'xpath', value: exactXp };
                    const containsRes = document.evaluate(containsXp, document, null,
                        XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
                    if (containsRes.snapshotLength === 1)
                        return { strategy: 'xpath', value: containsXp };
                } catch(_) {}
            }
        }

        // 10. CSS anchored to nearest ancestor with an id (shorter, more stable)
        function anchoredCSS(node) {
            let anchor = node.parentElement;
            while (anchor && anchor !== document.documentElement) {
                if (anchor.id && isStableId(anchor.id) && isUniqueCss(`#${CSS.escape(anchor.id)}`, anchor)) break;
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

    const metaTextTarget = findBestTextTarget(target);
    const textValue = (metaTextTarget?.textContent || target.textContent || '').trim().replace(/\s+/g, ' ');
    const role = target.getAttribute('role');
    const targetMeta = {
        tag,
        role: role || null,
        text: textValue || null,
        normalizedText: normalizeText(textValue) || null,
        ariaLabel: target.getAttribute('aria-label') || null,
        title: target.getAttribute('title') || null,
        name: target.getAttribute('name') || null,
        id: isStableId(target.id || '') ? target.id : null,
        dataTestId: target.getAttribute('data-testid') || null,
        dataId: target.getAttribute('data-id') || null,
        dataCy: target.getAttribute('data-cy') || null,
        dataQa: target.getAttribute('data-qa') || null,
        classHints: classHints(target),
    };

    return {
        tag,
        input_type: inputType || null,
        is_input: isTextInput,
        label: label || null,
        placeholder: target.getAttribute('placeholder') || null,
        current_value: target.value !== undefined ? target.value : (target.textContent || ''),
        is_password: inputType === 'password',
        selector: sel,
        target_meta: targetMeta,
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
