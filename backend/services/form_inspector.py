"""
Form Inspector — DOM → Structured Snapshot.

Captures EVERY interactive field in a LinkedIn Easy Apply modal and returns
a clean, structured representation that the AI brain can reason over in
a single pass.

Design goals:
- Detect ALL field types LinkedIn actually uses (standard + SDUI custom)
- Resolve label text from MULTIPLE sources: <label for>, aria-label,
  aria-labelledby, placeholder, legend, nearest preceding text node
- Capture ALL options for selects/radios/comboboxes — full text exactly
  as rendered, so the LLM can pick verbatim
- Detect "required" markers + current value so we know what to fill
- Tag each field with a stable internal id so the LLM's answer maps
  back to the exact element

Output shape (JSON-serialisable except `element`):
    {
      "step_title": "Contact info",
      "page_text":  "<first 1500 chars of modal text>",
      "fields": [
        {
          "id": "f0",
          "label": "Mobile phone number",
          "type": "tel",            # text|number|tel|email|url|select|radio|checkbox|combobox|typeahead|textarea|file
          "options": [],
          "required": true,
          "current": "",
          "placeholder": "",
          "max_length": null,
          "element": <Selenium WebElement>,
          "source": "label_for"     # how we found it
        },
        ...
      ],
      "validation_errors": [
        "Please enter a valid mobile phone number"
      ]
    }
"""
from __future__ import annotations

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


def _is_visible(el) -> bool:
    try:
        return el.is_displayed() and el.is_enabled()
    except Exception:
        return False


def _clean(text: str) -> str:
    """Strip duplicates / 'Required' suffix from LinkedIn SDUI label text."""
    if not text:
        return ""
    lines = [l.strip() for l in text.split("\n")
             if l.strip() and l.strip().lower() != "required"]
    return lines[0] if lines else text.strip()


def _get_modal(driver, By):
    for sel in [".jobs-easy-apply-modal", "div[role='dialog'].artdeco-modal",
                ".artdeco-modal", "div[role='dialog']"]:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            if _is_visible(el):
                return el
        except Exception:
            pass
    return None


def _resolve_label(driver, By, inp, modal) -> tuple[str, str]:
    """
    Find the most descriptive label for an input.
    Returns (label_text, source) where source explains how it was found.
    """
    # 1. <label for="id">
    inp_id = (inp.get_attribute("id") or "").strip()
    if inp_id:
        try:
            lab = modal.find_element(By.CSS_SELECTOR, f"label[for='{inp_id}']")
            txt = _clean(lab.text or "")
            if txt:
                return txt, "label_for"
        except Exception:
            pass

    # 2. aria-labelledby
    lb_id = (inp.get_attribute("aria-labelledby") or "").strip()
    if lb_id:
        for tok in lb_id.split():
            try:
                ref = modal.find_element(By.ID, tok)
                txt = _clean(ref.text or "")
                if txt:
                    return txt, "aria_labelledby"
            except Exception:
                pass

    # 3. aria-label
    al = (inp.get_attribute("aria-label") or "").strip()
    if al:
        return _clean(al), "aria_label"

    # 4. Wrapping <label> (no `for` attr)
    try:
        wrap = inp.find_element(By.XPATH, "ancestor::label[1]")
        txt = _clean(wrap.text or "")
        if txt:
            return txt, "wrapping_label"
    except Exception:
        pass

    # 5. Wrapping <fieldset> → <legend>
    try:
        fs = inp.find_element(By.XPATH, "ancestor::fieldset[1]")
        try:
            leg = fs.find_element(By.CSS_SELECTOR, "legend")
            txt = _clean(leg.text or "")
            if txt:
                return txt, "fieldset_legend"
        except Exception:
            pass
    except Exception:
        pass

    # 6. Placeholder
    ph = (inp.get_attribute("placeholder") or "").strip()
    if ph:
        return _clean(ph), "placeholder"

    # 7. name attribute
    nm = (inp.get_attribute("name") or "").strip()
    if nm:
        return _clean(nm), "name_attr"

    # 8. Nearest preceding text node (last resort)
    try:
        prev = inp.find_element(By.XPATH,
            "preceding::*[normalize-space(text())][1]")
        txt = _clean(prev.text or "")
        if txt:
            return txt[:120], "preceding_text"
    except Exception:
        pass

    return "", "none"


def _detect_type(inp) -> str:
    """Return one of: text|number|tel|email|url|select|radio|checkbox|combobox|typeahead|textarea|file"""
    try:
        tag = (inp.tag_name or "").lower()
        if tag == "select":
            return "select"
        if tag == "textarea":
            return "textarea"

        itype = (inp.get_attribute("type") or "text").lower()
        if itype == "checkbox":
            return "checkbox"
        if itype == "radio":
            return "radio"
        if itype == "file":
            return "file"
        if itype in ("number", "tel", "email", "url"):
            # These are still "text-like" but need type-specific validation
            role = (inp.get_attribute("role") or "").lower()
            if role == "combobox":
                return "combobox"
            return itype

        # Detect SDUI combobox / typeahead
        role = (inp.get_attribute("role") or "").lower()
        aria_auto = (inp.get_attribute("aria-autocomplete") or "").lower()
        if role == "combobox" or aria_auto in ("list", "both"):
            return "combobox"

        autocomp = (inp.get_attribute("autocomplete") or "").lower()
        if autocomp not in ("", "off", "on") or aria_auto == "inline":
            return "typeahead"

        return "text"
    except Exception:
        return "text"


def _get_options_for_select(inp) -> List[str]:
    """Standard <select> options — return visible text exactly as rendered."""
    try:
        from selenium.webdriver.support.ui import Select
        s = Select(inp)
        return [o.text.strip() for o in s.options if o.text and o.text.strip()]
    except Exception:
        return []


def _get_options_for_radio(driver, By, inp) -> List[str]:
    """Find sibling/ancestor fieldset and return all <label> texts."""
    try:
        fs = inp.find_element(By.XPATH, "ancestor::fieldset[1]")
        opts = []
        for lab in fs.find_elements(By.CSS_SELECTOR, "label"):
            t = (lab.text or "").strip()
            if t and t not in opts:
                opts.append(t)
        if opts:
            return opts
    except Exception:
        pass
    # Fallback: by `name` attribute group
    try:
        nm = inp.get_attribute("name")
        if nm:
            opts = []
            for r in driver.find_elements(By.CSS_SELECTOR, f"input[type='radio'][name='{nm}']"):
                # Find the label for this radio
                rid = r.get_attribute("id")
                if rid:
                    try:
                        lab = driver.find_element(By.CSS_SELECTOR, f"label[for='{rid}']")
                        t = (lab.text or "").strip()
                        if t and t not in opts:
                            opts.append(t)
                    except Exception:
                        pass
            return opts
    except Exception:
        pass
    return []


def _get_options_for_combobox(driver, By, inp) -> List[str]:
    """
    SDUI custom dropdowns — options live in a separate <ul role='listbox'>
    that is hidden until the trigger is clicked. We try to read the listbox
    if it's already in the DOM, otherwise return an empty list (the brain
    will know to send a free-form answer and the filler will handle clicking).
    """
    try:
        # Try aria-controls / aria-owns first
        ctrl = (inp.get_attribute("aria-controls") or
                inp.get_attribute("aria-owns") or "")
        if ctrl:
            try:
                listbox = driver.find_element(By.ID, ctrl.split()[0])
                opts = []
                for opt in listbox.find_elements(By.CSS_SELECTOR,
                        "[role='option'], li, [data-test-text-selectable-option]"):
                    t = (opt.text or "").strip()
                    if t and t not in opts:
                        opts.append(t)
                if opts:
                    return opts
            except Exception:
                pass
        # Fallback: any visible listbox in the modal
        for lb in driver.find_elements(By.CSS_SELECTOR,
                "[role='listbox'] [role='option'], .basic-typeahead__triggered-content li"):
            pass
    except Exception:
        pass
    return []


def _detect_required(inp, label_text: str) -> bool:
    try:
        if inp.get_attribute("required") is not None:
            return True
        if (inp.get_attribute("aria-required") or "").lower() == "true":
            return True
    except Exception:
        pass
    # LinkedIn's "Required" suffix in the label is the most reliable signal
    if label_text and "required" in label_text.lower():
        return True
    return False


def _validation_errors(driver, By, modal) -> List[str]:
    """Read inline validation messages currently visible in the modal."""
    errors = []
    if not modal:
        return errors
    for sel in [
        ".artdeco-inline-feedback__message",
        ".fb-form-element__error",
        "[data-test-form-element-error-message]",
        ".jobs-easy-apply-form-element__error",
        "[role='alert']",
    ]:
        try:
            for el in modal.find_elements(By.CSS_SELECTOR, sel):
                if not _is_visible(el):
                    continue
                t = (el.text or "").strip()
                if t and t not in errors and len(t) < 200:
                    errors.append(t)
        except Exception:
            pass
    return errors


def _step_title(modal, By=None) -> str:
    """Extract the step heading from the modal using the modern Selenium 4 API."""
    if modal is None:
        return ""
    try:
        from selenium.webdriver.common.by import By as _By
        _by = By or _By
        for sel in ["h3", "h2", "h1", "[role='heading']"]:
            try:
                for h in modal.find_elements(_by.CSS_SELECTOR, sel):
                    t = (h.text or "").strip()
                    if t:
                        return t[:80]
            except Exception:
                pass
    except Exception:
        pass
    return ""


def snapshot(driver, By) -> Optional[dict]:
    """
    Capture the full state of the current Easy Apply modal.
    Returns None if no modal is present.
    """
    modal = _get_modal(driver, By)
    if not modal:
        return None

    # Get title + page text for LLM context
    page_text = ""
    try:
        page_text = (modal.text or "")[:1500]
    except Exception:
        pass

    title = ""
    try:
        for sel in ["h3", "h2", "h1"]:
            try:
                hs = modal.find_elements(By.CSS_SELECTOR, sel)
                for h in hs:
                    if _is_visible(h):
                        t = (h.text or "").strip()
                        if t:
                            title = t[:80]
                            break
                if title:
                    break
            except Exception:
                pass
    except Exception:
        pass

    fields: List[dict] = []
    seen_radio_groups: set = set()
    seen_ids: set = set()
    counter = 0

    def _add_field(inp, ftype: str, options: List[str], label: str, source: str):
        nonlocal counter
        try:
            current = (inp.get_attribute("value") or "").strip()
            placeholder = inp.get_attribute("placeholder") or ""
            max_len = inp.get_attribute("maxlength")
            try:
                max_len = int(max_len) if max_len else None
            except Exception:
                max_len = None
            required = _detect_required(inp, label)
            field_id = f"f{counter}"
            counter += 1
            fields.append({
                "id": field_id,
                "label": label,
                "type": ftype,
                "options": options,
                "required": required,
                "current": current,
                "placeholder": placeholder,
                "max_length": max_len,
                "element": inp,
                "source": source,
            })
        except Exception as e:
            logger.debug("Failed to add field: %s", e)

    # ── 1. Standard form inputs ─────────────────────────────────────────
    selectors = (
        "input:not([type='hidden']):not([type='submit']):not([type='button']):not([type='reset']),"
        " select, textarea"
    )
    try:
        for inp in modal.find_elements(By.CSS_SELECTOR, selectors):
            if not _is_visible(inp):
                continue
            inp_id = inp.get_attribute("id") or ""

            ftype = _detect_type(inp)

            # Radios: collapse a whole group into ONE field entry
            if ftype == "radio":
                # Group key: prefer <fieldset> ancestor, fall back to name attr
                try:
                    fs = inp.find_element(By.XPATH, "ancestor::fieldset[1]")
                    group_key = "fs_" + (fs.get_attribute("id") or
                                         fs.get_attribute("data-test-form-builder-radio-button-form-component") or
                                         str(id(fs)))
                except Exception:
                    group_key = "name_" + (inp.get_attribute("name") or inp_id)

                if group_key in seen_radio_groups:
                    continue
                seen_radio_groups.add(group_key)

                label, source = _resolve_label(driver, By, inp, modal)
                # For radio groups, the legend is the question — try fieldset first
                try:
                    fs = inp.find_element(By.XPATH, "ancestor::fieldset[1]")
                    leg = fs.find_element(By.CSS_SELECTOR, "legend")
                    leg_txt = _clean(leg.text or "")
                    if leg_txt:
                        label = leg_txt
                        source = "fieldset_legend"
                except Exception:
                    pass

                opts = _get_options_for_radio(driver, By, inp)
                _add_field(inp, "radio", opts, label, source)
                continue

            # Skip if we already captured this id (avoid double-counting)
            if inp_id and inp_id in seen_ids:
                continue
            if inp_id:
                seen_ids.add(inp_id)

            label, source = _resolve_label(driver, By, inp, modal)

            opts: List[str] = []
            if ftype == "select":
                opts = _get_options_for_select(inp)
            elif ftype == "combobox":
                opts = _get_options_for_combobox(driver, By, inp)

            _add_field(inp, ftype, opts, label, source)
    except Exception as e:
        logger.warning("snapshot scan error: %s", e)

    # ── 2. SDUI custom dropdown buttons (no <input> at all) ─────────────
    # LinkedIn sometimes renders dropdowns as <button aria-haspopup="listbox">
    try:
        for btn in modal.find_elements(By.CSS_SELECTOR,
                "button[aria-haspopup='listbox'], [role='combobox'][aria-haspopup]"):
            if not _is_visible(btn):
                continue
            btn_id = btn.get_attribute("id") or ""
            if btn_id and btn_id in seen_ids:
                continue
            if btn_id:
                seen_ids.add(btn_id)
            label, source = _resolve_label(driver, By, btn, modal)
            opts = _get_options_for_combobox(driver, By, btn)
            _add_field(btn, "combobox", opts, label, source)
    except Exception:
        pass

    return {
        "step_title": title,
        "page_text": page_text,
        "fields": fields,
        "validation_errors": _validation_errors(driver, By, modal),
    }
