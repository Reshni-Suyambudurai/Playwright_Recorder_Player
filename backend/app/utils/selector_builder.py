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
import asyncio
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

    function isEditableControl(node) {
        if (!node || node.nodeType !== Node.ELEMENT_NODE) return false;
        const tag = node.tagName.toLowerCase();
        const itype = (node.getAttribute('type') || '').toLowerCase();
        const role = (node.getAttribute('role') || '').toLowerCase();
        if (tag === 'textarea') return true;
        if (node.getAttribute('contenteditable') === 'true') return true;
        if (role === 'textbox' || role === 'searchbox') return true;
        if (tag === 'input') {
            return !['submit', 'button', 'checkbox', 'radio', 'file', 'image', 'range', 'color'].includes(itype);
        }
        return false;
    }

    function findInteractive(node) {
        // If click lands on editable text-entry controls, keep them as target even
        // when wrapped by semantic combobox/listbox widgets.
        // NOTE: Only walk UP (ancestors), not DOWN (descendants), to avoid false positives
        // where clicking on a parent returns a hidden/unrelated nested input.
        const editableSelfOrAncestor = node.closest('input, textarea, [contenteditable="true"], [role="textbox"], [role="searchbox"]');
        if (editableSelfOrAncestor && isEditableControl(editableSelfOrAncestor)) return editableSelfOrAncestor;

        // Otherwise prefer semantic dropdown containers before generic targets.
        const dropdownOwner = node.closest('[role="combobox"], [role="listbox"], select, [aria-haspopup="listbox"]');
        if (dropdownOwner && !isEditableControl(dropdownOwner)) return dropdownOwner;

        // Walk up the DOM tree to find interactive candidates
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
    const inputType = (target.getAttribute('type') || '').toLowerCase();
    const semanticRole = (target.getAttribute('role') || '').toLowerCase();
    const hasPopupListbox = (target.getAttribute('aria-haspopup') || '').toLowerCase() === 'listbox';
    const isDropdownContainer = tag === 'select' || semanticRole === 'listbox' || (semanticRole === 'combobox' && !isEditableControl(target)) || (hasPopupListbox && !isEditableControl(target));

    const isTextInput = !isDropdownContainer && isEditableControl(target);

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

    // For dropdown containers, extract ONLY the selected option text (not all options)
    function getDropdownSelectedText(container) {
        const role = (container.getAttribute('role') || '').toLowerCase();
        const tag = container.tagName.toLowerCase();
        const isDropdown = tag === 'select' || role === 'listbox' || role === 'combobox';
        
        if (!isDropdown) return null;
        
        // Native <select>
        if (tag === 'select') {
            const selected = container.options[container.selectedIndex];
            if (selected) return (selected.textContent || selected.value || '').trim();
            return null;
        }
        
        // ARIA dropdown - find selected option by various indicators
        const selectedOption = 
            container.querySelector('[aria-selected="true"]') ||
            container.querySelector('[data-selected="true"]') ||
            container.querySelector('[selected]') ||
            container.querySelector('.selected');
        
        if (selectedOption) {
            return (selectedOption.textContent || selectedOption.getAttribute('value') || '').trim();
        }
        
        return null;
    }

    // For dropdown containers, only use the selected option value; don't include all option text
    const isDropdownRole = (target.getAttribute('role') || '').toLowerCase();
    const isDropdownTag = target.tagName.toLowerCase() === 'select';
    const isDropdownElement = isDropdownRole === 'listbox' || isDropdownRole === 'combobox' || isDropdownTag === 'select';
    
    let textValue = '';
    let currentValue = '';
    
    if (isDropdownElement) {
        // For dropdowns: extract selected value only, NEVER use textContent (which includes all options)
        const selectedText = getDropdownSelectedText(target);
        textValue = selectedText || (target.getAttribute('aria-label') || target.getAttribute('title') || target.getAttribute('placeholder') || '').trim();
        currentValue = selectedText || '';
    } else {
        // For non-dropdown elements: use normal text extraction
        const selectedText = getDropdownSelectedText(target);
        textValue = selectedText || (() => {
            const metaTextTarget = findBestTextTarget(target);
            return (metaTextTarget?.textContent || target.textContent || '').trim().replace(/\s+/g, ' ');
        })();
        
        if (target.value !== undefined) {
            currentValue = target.value;
        }
    }
    
    textValue = textValue.replace(/\s+/g, ' ');
    
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
        current_value: currentValue || '',
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
    attempts = 3
    for attempt in range(attempts):
        try:
            result = await page.evaluate(_INSPECT_JS, {"x": x, "y": y})
            if result:
                tag = (result.get("tag") or "").lower()
                if tag in {"body", "html"} and attempt < attempts - 1:
                    await asyncio.sleep(0.15)
                    continue
                logger.debug(f"Selector built at ({x},{y}): {result['selector']} is_input={result['is_input']}")
            return result
        except Exception as e:
            if attempt == attempts - 1:
                logger.warning(f"selector_builder failed at ({x},{y}): {e}")
                return None
            await asyncio.sleep(0.15)
    return None


# JS for assertion discovery — captures all data (visibility, text, value)
# Dropdown-detection helper — recognizes native <select> AND ARIA-based custom dropdowns
# (role="combobox"/"listbox", via aria-activedescendant/aria-controls/aria-owns linking or
# the nearest role="listbox" ancestor). Used by the value-assertion extraction below.
_COLLECT_DROPDOWN_DATA_JS = r"""
    function normalizeText(value) {
        return (value || '').trim().replace(/\s+/g, ' ');
    }

    function uniqueNonEmpty(values) {
        const seen = new Set();
        const result = [];
        for (const raw of values) {
            const text = normalizeText(raw);
            if (!text) continue;
            const key = text.toLowerCase();
            if (seen.has(key)) continue;
            seen.add(key);
            result.push(text);
        }
        return result;
    }

    function collectDropdownData(target) {
        const tag = target.tagName.toLowerCase();
        const ariaRole = (target.getAttribute('role') || '').toLowerCase();
        const isSelect = tag === 'select';
        const isAriaDropdown = ariaRole === 'combobox' || ariaRole === 'listbox';

        if (!isSelect && !isAriaDropdown) {
            return { selectedOption: null, dropdownOptions: [], optionCount: null };
        }

        if (isSelect) {
            const selectOptions = Array.from(target.options || []);
            const dropdownOptions = uniqueNonEmpty(selectOptions.map((opt) => opt.textContent || opt.value || ''));
            const selected = selectOptions.find((opt) => opt.selected);
            const selectedOption = normalizeText(selected?.textContent || selected?.value || target.value || '') || null;
            return {
                selectedOption,
                dropdownOptions,
                optionCount: dropdownOptions.length,
            };
        }

        const candidateContainers = [];
        const candidateNodes = [];

        function isLikelySelectedOption(node) {
            if (!node) return false;
            if (node.getAttribute('aria-selected') === 'true') return true;
            if (node.hasAttribute('selected')) return true;
            if (node.getAttribute('data-selected') === 'true') return true;
            const classText = (node.className || '').toString().toLowerCase();
            return classText.includes('selected');
        }

        function pushContainerById(rawId) {
            const id = normalizeText(rawId);
            if (!id) return;
            const container = document.getElementById(id);
            if (container) candidateContainers.push(container);
        }

        pushContainerById(target.getAttribute('aria-controls'));
        pushContainerById(target.getAttribute('aria-owns'));

        const activeId = target.getAttribute('aria-activedescendant');
        let selectedOption = null;
        if (activeId) {
            const activeNode = document.getElementById(activeId);
            const activeContainer = activeNode?.closest('[role="listbox"]') || activeNode?.parentElement || null;
            if (activeContainer) candidateContainers.push(activeContainer);
            selectedOption = normalizeText(activeNode?.textContent || activeNode?.getAttribute('value') || '') || null;
        }

        if (ariaRole === 'listbox') {
            candidateContainers.push(target);
        }

        if (ariaRole === 'listbox' && target.id) {
            const escapedId = window.CSS && window.CSS.escape ? window.CSS.escape(target.id) : target.id;
            const controller = document.querySelector(
                `[aria-controls="${escapedId}"], [aria-owns="${escapedId}"]`
            );
            if (controller) {
                const controllerValue = normalizeText(
                    controller.value
                    || controller.getAttribute('value')
                    || controller.getAttribute('aria-label')
                    || ''
                );
                if (controllerValue) {
                    selectedOption = controllerValue;
                }

                pushContainerById(controller.getAttribute('aria-controls'));
                pushContainerById(controller.getAttribute('aria-owns'));
            }
        }

        const nearestListbox = target.closest('[role="listbox"]');
        if (nearestListbox) {
            candidateContainers.push(nearestListbox);
        }

        const seen = new Set();
        const uniqueContainers = [];
        for (const container of candidateContainers) {
            if (!container || seen.has(container)) continue;
            seen.add(container);
            uniqueContainers.push(container);
        }

        for (const container of uniqueContainers) {
            candidateNodes.push(...Array.from(container.querySelectorAll('[role="option"], option, li')));
        }

        const dropdownOptions = uniqueNonEmpty(candidateNodes.map((node) => node.textContent || node.getAttribute('value') || ''));
        if (!selectedOption) {
            const selectedNode = candidateNodes.find((node) => isLikelySelectedOption(node));
            selectedOption = normalizeText(selectedNode?.textContent || selectedNode?.getAttribute('value') || '') || null;
        }

        if (!selectedOption) {
            selectedOption = normalizeText(target.value || target.getAttribute('value') || '') || null;
        }

        return {
            selectedOption,
            dropdownOptions,
            optionCount: dropdownOptions.length,
        };
    }
"""

# Element-based core: extracts assertion data from a known element handle directly — no
# pixel hit-testing involved. This is what playback uses once it has already resolved the
# right element via the recorded selector, so it never has to re-guess which element is at
# some computed coordinate (that re-guess is what broke on large container elements like a
# listbox, whose bounding-box center is covered by a child option, not the listbox itself).
_INSPECT_ELEMENT_FOR_ASSERTION_JS = r"""
(el) => {
    if (!el) return null;

    %s

    // Helper to build selector (reuse same logic as _INSPECT_JS)
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
            if (expected && all[0] !== expected) return false;
            return true;
        } catch(_) {
            return false;
        }
    }

    function buildSelector(e) {
        const tag = e.tagName.toLowerCase();
        const itype = e.getAttribute('type') || '';

        if (e.id && isStableId(e.id) && isUniqueCss(`#${CSS.escape(e.id)}`, e)) {
            return { strategy: 'id', value: e.id };
        }

        for (const attr of ['data-testid', 'data-id', 'data-cy', 'data-qa']) {
            const v = e.getAttribute(attr);
            if (!v) continue;
            const q = `[${attr}="${CSS.escape(v)}"]`;
            if (isUniqueCss(q, e)) return { strategy: 'css', value: q };
        }

        const aria = e.getAttribute('aria-label');
        if (aria) {
            const q = `[aria-label="${CSS.escape(aria)}"]`;
            if (isUniqueCss(q, e)) return { strategy: 'css', value: q };
        }

        const name = e.getAttribute('name');
        if (name) {
            const q = `${tag}[name="${CSS.escape(name)}"]`;
            if (isUniqueCss(q, e)) return { strategy: 'css', value: q };
        }

        if (tag === 'input' && (itype === 'submit' || itype === 'button')) {
            const val = e.getAttribute('value');
            if (val) {
                const q = `input[type="${itype}"][value="${val}"]`;
                if (document.querySelectorAll(q).length === 1)
                    return { strategy: 'css', value: q };
            }
        }

        const role = e.getAttribute('role');
        if (role) {
            const q = `[role="${role}"]`;
            if (document.querySelectorAll(q).length === 1)
                return { strategy: 'css', value: q };
        }

        const title = e.getAttribute('title');
        if (title) {
            const q = `[title="${CSS.escape(title)}"]`;
            if (document.querySelectorAll(q).length === 1)
                return { strategy: 'css', value: q };
        }

        function getXPath(node) {
            if (!node || node === document.documentElement) return '/html';
            const t = node.tagName.toLowerCase();
            const sibs = node.parentElement
                ? Array.from(node.parentElement.children).filter(c => c.tagName === node.tagName)
                : [node];
            const idx = sibs.indexOf(node) + 1;
            return `${getXPath(node.parentElement)}/${t}${sibs.length > 1 ? `[${idx}]` : ''}`;
        }
        return { strategy: 'xpath', value: getXPath(e) };
    }

    // Compute visibility
    const rect = el.getBoundingClientRect();
    const computed = window.getComputedStyle(el);
    const visible = rect.width > 0 && rect.height > 0 && computed.display !== 'none' && computed.visibility !== 'hidden';
    const display = computed.display || 'unknown';
    const opacity = parseFloat(computed.opacity) || 1.0;

    // Extract text
    const text = (el.textContent || '').trim().replace(/\s+/g, ' ');
    const wordCount = text.split(/\s+/).filter(w => w).length;
    const charCount = text.length;
    const accessibleName = el.getAttribute('aria-label') || el.getAttribute('title') || el.getAttribute('placeholder') || '';

    // Extract value (for inputs, selects, textareas)
    const tag = el.tagName.toLowerCase();
    const value = el.value !== undefined ? el.value : '';
    const inputType = (el.getAttribute('type') || '').toLowerCase();

    // Extract dropdown options — recognizes native <select> and ARIA combobox/listbox widgets
    const dropdownData = collectDropdownData(el);

    return {
        visible,
        display,
        opacity,
        text,
        wordCount,
        charCount,
        accessibleName,
        value,
        type: inputType || 'unknown',
        dropdownOptions: dropdownData.dropdownOptions,
        selectedOption: dropdownData.selectedOption,
        optionCount: dropdownData.optionCount,
        selector: buildSelector(el)
    };
}
""" % _COLLECT_DROPDOWN_DATA_JS

# Point-based wrapper: only used for live hover during recording, where the browser genuinely
# needs to hit-test "what's under the mouse right now". It just locates the element, then hands
# off to the same element-based core above.
_INSPECT_FOR_ASSERTION_JS = r"""
(args) => {
    const { x, y } = args;
    const el = document.elementFromPoint(x, y);
    if (!el) return null;
    return (%s)(el);
}
""" % _INSPECT_ELEMENT_FOR_ASSERTION_JS


async def discover_by_assertion_mode(page: Page, x: float, y: float, mode: str) -> dict | None:
    """
    Inspect element at (x, y) and extract assertion data for the given mode.
    Reuses _INSPECT_FOR_ASSERTION_JS to capture all data in one pass.
    
    Args:
        page: Playwright page
        x: viewport x coordinate
        y: viewport y coordinate
        mode: 'visibility' | 'text' | 'value'
        
    Returns:
        Mode-specific assertion data dict, or None on error
    """
    try:
        result = await page.evaluate(_INSPECT_FOR_ASSERTION_JS, {"x": x, "y": y})
        return result
    except Exception as e:
        logger.warning(f"assertion discovery failed at ({x},{y}) mode={mode}: {e}")
        return None


async def discover_assertion_data_from_element(element, mode: str) -> dict | None:
    """
    Extract assertion data directly from an already-resolved element handle — no pixel
    hit-testing. Used by playback once it has found the right element via the recorded
    selector, so it never has to re-guess the element at some computed coordinate (that
    re-guess breaks for large container elements, e.g. a listbox whose bounding-box center
    is covered by a child option rather than the listbox itself).
    """
    try:
        return await element.evaluate(_INSPECT_ELEMENT_FOR_ASSERTION_JS)
    except Exception as e:
        logger.warning(f"assertion discovery from element failed mode={mode}: {e}")
        return None
