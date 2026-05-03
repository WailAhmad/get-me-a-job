"""
Form Filler — Smart per-type element interactions.

Given a (field, value) pair, this module figures out the right way to write
that value into the DOM. Each field type has a primary strategy and one or
more JS fallbacks for when LinkedIn's custom components don't respond to
standard Selenium calls.

Field types handled:
    text, email, url, tel       → clear() + send_keys()
    number                      → clear() + send_keys() with int coercion
    textarea                    → clear() + send_keys()
    select  (standard <select>) → Select.select_by_visible_text()
    radio                       → match label text and click()
    checkbox                    → click if state mismatch
    combobox (SDUI custom)      → click trigger, wait listbox, click matching option
    typeahead                   → send_keys, wait dropdown, click first/best suggestion
    file                        → skipped (LinkedIn uses your profile resume)

All fillers return True on success, False on failure. Failure does NOT raise.
"""
from __future__ import annotations

import logging
import time
from typing import Optional, List

from . import form_brain as brain

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# Low-level helpers
# ────────────────────────────────────────────────────────────────────────────

def _is_visible(el) -> bool:
    try:
        return el.is_displayed() and el.is_enabled()
    except Exception:
        return False


def _click(driver, el) -> bool:
    """Try multiple click strategies."""
    if el is None:
        return False
    # 1. Native
    try:
        el.click()
        return True
    except Exception:
        pass
    # 2. JS click
    try:
        driver.execute_script("arguments[0].click()", el)
        return True
    except Exception:
        pass
    # 3. ActionChains
    try:
        from selenium.webdriver.common.action_chains import ActionChains
        ActionChains(driver).move_to_element(el).click().perform()
        return True
    except Exception:
        pass
    return False


def _scroll_into_view(driver, el):
    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center', inline:'center', behavior:'instant'})",
            el)
        time.sleep(0.15)
    except Exception:
        pass


def _set_value_via_js(driver, el, value: str) -> bool:
    """
    Force-set an input's value via JS — used as the last-resort fallback for
    inputs that won't accept send_keys (e.g., readonly typeaheads).
    Fires `input` and `change` events so React listeners pick it up.
    """
    try:
        driver.execute_script("""
            const el = arguments[0];
            const val = arguments[1];
            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            setter.call(el, val);
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
        """, el, value)
        return True
    except Exception:
        return False


def _verify_value(el, expected: str, treat_blank_as_ok: bool = False) -> bool:
    """Confirm the input now contains the expected value (case-insensitive contains)."""
    try:
        actual = (el.get_attribute("value") or "").strip()
        if not actual:
            return treat_blank_as_ok
        return expected.strip().lower() in actual.lower() or actual.lower() in expected.strip().lower()
    except Exception:
        return False


# ────────────────────────────────────────────────────────────────────────────
# Per-type fillers
# ────────────────────────────────────────────────────────────────────────────

def fill_text(driver, field: dict, value: str) -> bool:
    el = field["element"]
    _scroll_into_view(driver, el)
    try:
        el.clear()
    except Exception:
        pass
    try:
        el.send_keys(value)
        if _verify_value(el, value):
            return True
    except Exception:
        pass
    # Fallback: JS-set value
    if _set_value_via_js(driver, el, value):
        return _verify_value(el, value)
    return False


def fill_number(driver, field: dict, value: str) -> bool:
    coerced = brain.coerce_to_number(value) or value
    return fill_text(driver, field, coerced)


def fill_textarea(driver, field: dict, value: str) -> bool:
    return fill_text(driver, field, value)


def fill_select(driver, By, field: dict, value: str) -> bool:
    """Standard <select> element."""
    el = field["element"]
    options = field.get("options") or []
    target = brain.best_option_match(value, options) or value

    try:
        from selenium.webdriver.support.ui import Select
        sel = Select(el)

        # 1. Visible text
        try:
            sel.select_by_visible_text(target)
            return True
        except Exception:
            pass

        # 2. Iterate options & match
        target_norm = brain.normalise_for_match(target)
        for opt in sel.options:
            if brain.normalise_for_match(opt.text) == target_norm:
                sel.select_by_visible_text(opt.text)
                return True

        # 3. Substring fallback
        for opt in sel.options:
            if target_norm in brain.normalise_for_match(opt.text):
                sel.select_by_visible_text(opt.text)
                return True

        # 4. First non-empty option as last resort if select is required
        if field.get("required"):
            for opt in sel.options:
                if (opt.text or "").strip() and (opt.get_attribute("value") or "").strip():
                    sel.select_by_visible_text(opt.text)
                    return True
    except Exception as e:
        logger.warning("fill_select failed for %r: %s", field.get("label"), e)
    return False


def fill_radio(driver, By, field: dict, value: str) -> bool:
    """Click the radio whose label best matches `value`."""
    el = field["element"]
    options = field.get("options") or []
    target = brain.best_option_match(value, options) or value
    target_norm = brain.normalise_for_match(target)

    # Find the fieldset containing our radio group
    try:
        fs = el.find_element(By.XPATH, "ancestor::fieldset[1]")
    except Exception:
        fs = None

    # 1. Click the matching <label>
    if fs is not None:
        for lab in fs.find_elements(By.CSS_SELECTOR, "label"):
            try:
                if not _is_visible(lab):
                    continue
                lab_norm = brain.normalise_for_match(lab.text or "")
                if not lab_norm:
                    continue
                if lab_norm == target_norm or target_norm in lab_norm or lab_norm in target_norm:
                    _scroll_into_view(driver, lab)
                    if _click(driver, lab):
                        time.sleep(0.2)
                        return True
            except Exception:
                continue

    # 2. Click the matching <input type="radio"> directly via data-test attr
    if fs is not None:
        for r in fs.find_elements(By.CSS_SELECTOR, "input[type='radio']"):
            try:
                attr = (r.get_attribute("data-test-text-selectable-option__input") or "").strip()
                if attr and brain.normalise_for_match(attr) == target_norm:
                    _scroll_into_view(driver, r)
                    if _click(driver, r):
                        time.sleep(0.2)
                        return True
            except Exception:
                continue

    # 3. Word-overlap pick
    if fs is not None:
        target_words = set(target_norm.split())
        target_words.discard("or"); target_words.discard("and")
        best_lab = None
        best_score = 0
        for lab in fs.find_elements(By.CSS_SELECTOR, "label"):
            try:
                lab_norm = brain.normalise_for_match(lab.text or "")
                lab_words = set(lab_norm.split())
                lab_words.discard("or"); lab_words.discard("and")
                overlap = len(target_words & lab_words)
                if overlap > best_score and _is_visible(lab):
                    best_score = overlap
                    best_lab = lab
            except Exception:
                continue
        if best_lab and best_score >= 1:
            _scroll_into_view(driver, best_lab)
            if _click(driver, best_lab):
                time.sleep(0.2)
                return True

    return False


def fill_checkbox(driver, field: dict, value: str) -> bool:
    el = field["element"]
    want_checked = (value or "").strip().lower() in {"yes", "true", "y", "1", "agree", "checked", "on"}
    try:
        is_checked = el.is_selected()
    except Exception:
        is_checked = False

    if is_checked == want_checked:
        return True
    return _click(driver, el)


def fill_combobox(driver, By, field: dict, value: str) -> bool:
    """
    LinkedIn SDUI custom dropdown:
      <button aria-haspopup="listbox">  OR  <input role="combobox">
    Strategy:
      1. Click the trigger to open the listbox
      2. Wait for visible options
      3. Click the option matching `value`
    """
    el = field["element"]
    target = brain.best_option_match(value, field.get("options") or []) or value
    target_norm = brain.normalise_for_match(target)

    _scroll_into_view(driver, el)

    # If it's actually a standard <select>, fall back to that path
    try:
        if (el.tag_name or "").lower() == "select":
            return fill_select(driver, By, field, value)
    except Exception:
        pass

    # 1. Open the dropdown
    if not _click(driver, el):
        return False
    time.sleep(0.4)

    # 2. Find a visible listbox
    listbox = None
    for sel in [
        "[role='listbox']:not([hidden])",
        ".basic-typeahead__triggered-content",
        ".artdeco-typeahead__results-list",
        "ul[role='listbox']",
    ]:
        try:
            for lb in driver.find_elements(By.CSS_SELECTOR, sel):
                if _is_visible(lb):
                    listbox = lb
                    break
            if listbox:
                break
        except Exception:
            continue

    if listbox is None:
        # Try typing into the trigger if it's an input
        try:
            if el.tag_name.lower() == "input":
                el.send_keys(target)
                time.sleep(0.5)
                # Re-find listbox
                for sel in ["[role='listbox']", ".basic-typeahead__triggered-content"]:
                    try:
                        for lb in driver.find_elements(By.CSS_SELECTOR, sel):
                            if _is_visible(lb):
                                listbox = lb
                                break
                    except Exception:
                        pass
        except Exception:
            pass

    if listbox is None:
        return False

    # 3. Pick the matching option
    try:
        opts = listbox.find_elements(By.CSS_SELECTOR,
            "[role='option'], li, [data-test-text-selectable-option]")
        # Exact match first
        for o in opts:
            if not _is_visible(o):
                continue
            if brain.normalise_for_match(o.text or "") == target_norm:
                if _click(driver, o):
                    time.sleep(0.2)
                    return True
        # Substring
        for o in opts:
            if not _is_visible(o):
                continue
            o_norm = brain.normalise_for_match(o.text or "")
            if o_norm and (target_norm in o_norm or o_norm in target_norm):
                if _click(driver, o):
                    time.sleep(0.2)
                    return True
    except Exception as e:
        logger.warning("combobox option-pick failed: %s", e)

    return False


def fill_typeahead(driver, By, field: dict, value: str) -> bool:
    """
    LinkedIn typeahead (city, school, company name):
    type the value, wait for the dropdown, click the first suggestion.
    """
    el = field["element"]
    _scroll_into_view(driver, el)
    try:
        el.clear()
    except Exception:
        pass
    try:
        el.send_keys(value)
    except Exception:
        return False

    time.sleep(0.7)

    for sel in [
        "div[role='option']",
        "li[role='option']",
        ".artdeco-typeahead__option",
        ".basic-typeahead__triggered-content li",
        "[data-test-text-selectable-option]",
    ]:
        try:
            opts = driver.find_elements(By.CSS_SELECTOR, sel)
            visible = [o for o in opts if _is_visible(o)]
            if visible:
                if _click(driver, visible[0]):
                    time.sleep(0.2)
                    return True
        except Exception:
            continue

    # No dropdown — Tab out to commit the typed value
    try:
        from selenium.webdriver.common.keys import Keys
        el.send_keys(Keys.TAB)
        return True
    except Exception:
        return False


# ────────────────────────────────────────────────────────────────────────────
# Public dispatcher
# ────────────────────────────────────────────────────────────────────────────

def fill_field(driver, By, field: dict, value: str) -> bool:
    """Dispatch to the right per-type filler. Returns True on success."""
    if value is None:
        return False
    value = str(value).strip()
    if value == "":
        return False

    ftype = (field.get("type") or "text").lower()

    try:
        if ftype == "select":
            return fill_select(driver, By, field, value)
        if ftype == "radio":
            return fill_radio(driver, By, field, value)
        if ftype == "checkbox":
            return fill_checkbox(driver, field, value)
        if ftype == "combobox":
            return fill_combobox(driver, By, field, value)
        if ftype == "typeahead":
            return fill_typeahead(driver, By, field, value)
        if ftype == "number":
            return fill_number(driver, field, value)
        if ftype == "textarea":
            return fill_textarea(driver, field, value)
        if ftype == "file":
            # LinkedIn uses the user's profile resume — skip
            return True
        # Default: text-like fields
        return fill_text(driver, field, value)
    except Exception as e:
        logger.warning("fill_field error for %r (%s): %s",
                      field.get("label"), ftype, e)
        return False
