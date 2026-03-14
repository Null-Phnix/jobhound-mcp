"""
Stealth Playwright-based application submitter for Ashby, Greenhouse, and Lever.

Strategy per ATS:
  Ashby     — navigate to applyUrl, fill standard + custom fields, submit
  Greenhouse — navigate to absolute_url, fill form, submit
  Lever     — navigate to hostedUrl + /apply, fill form, submit
  Fallback  — Blackreach for anything else
"""
import asyncio
import json
import random
import tempfile
import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
from urllib.parse import urlparse

from jobhound.log import get_logger

log = get_logger("jobhound.playwright")

_COOLDOWN_FILE = Path.home() / ".jobhound" / "ats_cooldowns.json"
_ASHBY_COOLDOWN_SECS = 600  # 10 minutes between submissions to same Ashby domain


def _get_domain(url: str) -> str:
    return urlparse(url).netloc.lower()


def _check_ashby_cooldown(url: str) -> Optional[float]:
    """Returns seconds remaining on cooldown, or None if clear to proceed."""
    try:
        if not _COOLDOWN_FILE.exists():
            return None
        data = json.loads(_COOLDOWN_FILE.read_text())
        domain = _get_domain(url)
        last = data.get(domain)
        if last is None:
            return None
        remaining = _ASHBY_COOLDOWN_SECS - (time.time() - last)
        return remaining if remaining > 0 else None
    except Exception:
        return None


def _record_ashby_submission(url: str) -> None:
    """Record submission timestamp for this domain."""
    try:
        _COOLDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if _COOLDOWN_FILE.exists():
            try:
                data = json.loads(_COOLDOWN_FILE.read_text())
            except Exception:
                pass
        data[_get_domain(url)] = time.time()
        _COOLDOWN_FILE.write_text(json.dumps(data, indent=2))
    except Exception as e:
        log.debug("Failed to record cooldown: %s", e)

# Common field selectors ordered by confidence
_NAME_SELECTORS = [
    'input[name*="name" i]:not([name*="company" i]):not([name*="last" i])',
    'input[placeholder*="full name" i]',
    'input[placeholder*="your name" i]',
    'input[id*="first_name" i]',
    'input[id*="name" i]:not([id*="last" i])',
    'input[autocomplete="name"]',
]
_FIRST_NAME_SELECTORS = [
    'input[name="first_name"]',
    'input[id="first_name"]',
    'input[placeholder*="first name" i]',
    'input[autocomplete="given-name"]',
]
_LAST_NAME_SELECTORS = [
    'input[name="last_name"]',
    'input[id="last_name"]',
    'input[placeholder*="last name" i]',
    'input[autocomplete="family-name"]',
]
_EMAIL_SELECTORS = [
    'input[type="email"]',
    'input[name*="email" i]',
    'input[placeholder*="email" i]',
    'input[id*="email" i]',
]
_PHONE_SELECTORS = [
    'input[type="tel"]',
    'input[name*="phone" i]',
    'input[placeholder*="phone" i]',
    'input[id*="phone" i]',
]
_RESUME_SELECTORS = [
    'input[type="file"][name*="resume" i]',
    'input[type="file"][accept*="pdf" i]',
    'input[type="file"][id*="resume" i]',
    'input[type="file"]',
]
_COVER_SELECTORS = [
    'textarea[name*="cover" i]',
    'textarea[id*="cover" i]',
    'textarea[placeholder*="cover" i]',
    'textarea[name*="letter" i]',
    'textarea[id*="letter" i]',
    'textarea[placeholder*="letter" i]',
]
_LINKEDIN_SELECTORS = [
    'input[name*="linkedin" i]',
    'input[placeholder*="linkedin" i]',
    'input[id*="linkedin" i]',
    'input[autocomplete*="linkedin" i]',
]
# Greenhouse-style custom question labels to match for common fields
_WEBSITE_LABEL_HINTS = ["github", "website", "blog", "portfolio", "personal site", "url"]
_LINKEDIN_LABEL_HINTS = ["linkedin"]
_SUBMIT_SELECTORS = [
    'button[type="submit"]',
    'input[type="submit"]',
    'button:has-text("Submit")',
    'button:has-text("Apply")',
    'button:has-text("Send application")',
    'button:has-text("Submit Application")',
    'a:has-text("Submit Application")',
    '[class*="submit"]:visible',
]


@dataclass
class Applicant:
    name: str
    email: str
    phone: str
    linkedin: str = ""


async def _jitter(min_ms: int = 400, max_ms: int = 1200) -> None:
    await asyncio.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


async def _jitter_slow(min_ms: int = 800, max_ms: int = 2500) -> None:
    """Slower jitter for CAPTCHA-sensitive ATSs like Lever."""
    await asyncio.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


async def _try_fill(page, selectors: list[str], value: str, label: str = "") -> bool:
    """Try each selector until one is visible and fillable. Returns True on success."""
    for sel in selectors:
        try:
            el = page.locator(sel).first
            if await el.count() > 0 and await el.is_visible():
                await el.click()
                await _jitter(100, 300)
                await el.fill(value)
                await _jitter(100, 300)
                log.debug("Filled %s with selector: %s", label, sel)
                return True
        except Exception:
            continue
    return False


async def _try_fill_by_label(page, label_hints: list[str], value: str, label: str = "") -> bool:
    """Fill an input by finding it near a label containing any of the hint strings."""
    for hint in label_hints:
        try:
            el = page.get_by_label(hint, exact=False).first
            if await el.count() > 0 and await el.is_visible():
                await el.click()
                await _jitter(100, 300)
                await el.fill(value)
                await _jitter(100, 300)
                log.debug("Filled %s via label hint '%s'", label, hint)
                return True
        except Exception:
            continue
    return False


async def _try_greenhouse_cover_letter(page, letter: str) -> bool:
    """Handle Greenhouse's 'Enter manually' cover letter button pattern."""
    try:
        btn = page.get_by_role("button", name="Enter manually").first
        if await btn.count() > 0 and await btn.is_visible():
            await btn.click()
            await _jitter(400, 700)
            # Textarea should appear — get the one nearest the button by checking all visible textareas
            # and picking the one that was just revealed (newly visible = empty)
            textareas = page.locator("textarea")
            count = await textareas.count()
            for i in range(count):
                ta = textareas.nth(i)
                if await ta.is_visible():
                    val = await ta.input_value()
                    if not val:
                        await ta.fill(letter)
                        await _jitter(200, 400)
                        log.debug("Filled cover letter via Greenhouse 'Enter manually' button")
                        return True
    except Exception:
        pass
    return False


async def _fill_custom_questions(page, letter: str) -> None:
    """
    Handle Greenhouse-style custom application questions after standard fields.
    - React-select dropdowns: click and pick first option (or Yes for yes/no)
    - Empty visible textareas: fill with cover letter excerpt
    - Text inputs with unfilled label-matched content (API scale, etc.)
    """
    # EEO/sensitive question label keywords — prefer "Prefer not to answer" for these
    _EEO_HINTS = {"gender", "race", "ethnicity", "hispanic", "veteran", "disability",
                  "latino", "sexual", "orientation", "pronouns"}
    # Options to prefer for EEO fields (pick first match in this list)
    _DECLINE_OPTIONS = ["prefer not to answer", "prefer not to disclose", "decline",
                        "i don't wish", "i do not wish", "choose not to"]

    # 1. Handle React-select dropdowns (Greenhouse uses class*="select__control")
    try:
        controls = page.locator('[class*="select__control"], [class*="SelectInput__control"]')
        count = await controls.count()
        for i in range(count):
            ctrl = controls.nth(i)
            if not await ctrl.is_visible():
                continue
            # Check if it still shows placeholder (unfilled)
            placeholder = ctrl.locator('[class*="placeholder"]')
            if await placeholder.count() == 0:
                continue  # already filled

            # Try to detect label context for this control
            ctrl_label = ""
            try:
                parent = ctrl.locator("xpath=ancestor::div[contains(@class,'field') or contains(@class,'question')][1]")
                if await parent.count() > 0:
                    ctrl_label = (await parent.inner_text()).lower()
            except Exception:
                pass

            await ctrl.click()
            await _jitter(200, 400)

            opts = page.locator('[class*="option"]')
            opts_count = await opts.count()

            picked = False
            # For EEO/sensitive questions, prefer decline options
            if any(h in ctrl_label for h in _EEO_HINTS):
                for decline in _DECLINE_OPTIONS:
                    for j in range(opts_count):
                        opt_text = (await opts.nth(j).inner_text()).lower()
                        if decline in opt_text:
                            await opts.nth(j).click()
                            picked = True
                            break
                    if picked:
                        break

            if not picked:
                # Work authorization: Canadian applicant — honest answers
                if "authorized to work in the united states" in ctrl_label or "authorized to work in the us" in ctrl_label:
                    for j in range(opts_count):
                        opt_text = (await opts.nth(j).inner_text()).lower().strip()
                        if opt_text == "no":
                            await opts.nth(j).click()
                            picked = True
                            break
                elif "sponsorship" in ctrl_label or "visa" in ctrl_label or "work authorization" in ctrl_label:
                    for j in range(opts_count):
                        opt_text = (await opts.nth(j).inner_text()).lower().strip()
                        if opt_text == "yes":
                            await opts.nth(j).click()
                            picked = True
                            break
                elif "years" in ctrl_label and "experience" in ctrl_label:
                    # Pick "1-2 years" or "Less than 1" — be honest
                    for j in range(opts_count):
                        opt_text = (await opts.nth(j).inner_text()).lower().strip()
                        if "1" in opt_text and ("2" in opt_text or "year" in opt_text):
                            await opts.nth(j).click()
                            picked = True
                            break
                elif "18" in ctrl_label or "age" in ctrl_label:
                    for j in range(opts_count):
                        opt_text = (await opts.nth(j).inner_text()).lower().strip()
                        if opt_text == "yes":
                            await opts.nth(j).click()
                            picked = True
                            break

            if not picked:
                # Generic: prefer "Yes" for yes/no
                for j in range(opts_count):
                    opt_text = (await opts.nth(j).inner_text()).lower().strip()
                    if opt_text == "yes":
                        await opts.nth(j).click()
                        picked = True
                        break

            if not picked and opts_count > 0:
                start = 1 if opts_count > 1 else 0
                await opts.nth(start).click()

            await _jitter(200, 400)
            log.debug("Filled React-select dropdown %d (label: %s)", i, ctrl_label[:40])
    except Exception as e:
        log.debug("React-select fill error: %s", e)

    # 2. Fill any remaining visible empty textareas
    try:
        textareas = page.locator("textarea")
        count = await textareas.count()
        for i in range(count):
            ta = textareas.nth(i)
            if not await ta.is_visible():
                continue
            val = await ta.input_value()
            if not val:
                await ta.fill(letter[:600])
                await _jitter(100, 200)
                log.debug("Filled empty textarea %d with cover letter excerpt", i)
    except Exception as e:
        log.debug("Textarea fill error: %s", e)

    # 3. Fill any visible empty text inputs not caught by standard selectors
    # (e.g. "Are you based in Canada?" text field, "largest API scale", etc.)
    try:
        inputs = page.locator('input[type="text"]:visible, input:not([type]):visible')
        count = await inputs.count()
        for i in range(count):
            inp = inputs.nth(i)
            val = await inp.input_value()
            if val:
                continue  # already filled
            # Try to get label text for context
            try:
                label_text = ""
                inp_id = await inp.get_attribute("id")
                if inp_id:
                    lbl = page.locator(f'label[for="{inp_id}"]')
                    if await lbl.count() > 0:
                        label_text = (await lbl.inner_text()).lower()
            except Exception:
                pass
            if "canada" in label_text or "location" in label_text or "city" in label_text:
                await inp.fill("Toronto, ON, Canada")
                await _jitter(100, 200)
            elif "salary" in label_text or "compensation" in label_text:
                await inp.fill("Open to discussion")
                await _jitter(100, 200)
            elif "phonetic" in label_text or "pronounce" in label_text or "pronunciation" in label_text:
                await inp.fill("ho-SEE-mar")
                await _jitter(100, 200)
                log.debug("Filled phonetic name field")
            elif "pronoun" in label_text:
                await inp.fill("He/Him")
                await _jitter(100, 200)
    except Exception as e:
        log.debug("Custom input fill error: %s", e)


async def _fill_ashby_yesno(page) -> None:
    """
    Handle Ashby's Yes/No button-based questions.
    Each question is a `ashby-application-form-field-entry` div with a label + two buttons.
    """
    try:
        entries = page.locator('[class*="ashby-application-form-field-entry"]')
        count = await entries.count()
        for i in range(count):
            entry = entries.nth(i)
            yesno = entry.locator('[class*="_yesno_"]')
            if await yesno.count() == 0:
                continue
            label_el = entry.locator('[class*="ashby-application-form-question-title"]').first
            if await label_el.count() == 0:
                continue
            question = (await label_el.inner_text()).lower().strip()
            yes_btn = yesno.locator('button:has-text("Yes")').first
            no_btn = yesno.locator('button:has-text("No")').first

            if "18 years of age" in question:
                click_yes = True
            elif "authorized to work in the united states" in question or "authorized to work in the us" in question:
                click_yes = False   # Canadian applicant
            elif "sponsorship" in question or "visa" in question:
                click_yes = True    # Yes, will need sponsorship
            elif "3 days per week" in question or "work from" in question and "office" in question:
                click_yes = False   # Not in Bay Area
            elif "relocate" in question or "relocation" in question:
                click_yes = False   # Not willing to relocate
            else:
                click_yes = True    # Default yes

            btn = yes_btn if click_yes else no_btn
            if await btn.count() > 0 and await btn.is_visible():
                await btn.click()
                await _jitter(150, 300)
                log.debug("Ashby Yes/No: '%s...' → %s", question[:50], "Yes" if click_yes else "No")
    except Exception as e:
        log.debug("Ashby Yes/No fill error: %s", e)


async def _fill_ashby_location_combobox(page, location: str = "Toronto, ON, Canada") -> bool:
    """Fill Ashby's autocomplete location combobox."""
    try:
        combo = page.locator('[role="combobox"][class*="_input_"]').first
        if await combo.count() == 0:
            combo = page.locator('input[placeholder="Start typing..."]').first
        if await combo.count() == 0 or not await combo.is_visible():
            return False
        await combo.click()
        await _jitter(200, 400)
        await combo.fill("Toronto")
        await _jitter(1200, 1800)  # Wait for autocomplete suggestions
        # Click first dropdown option
        for opt_sel in ['[role="option"]', '[class*="_option_"]', '[class*="option"]']:
            opts = page.locator(opt_sel)
            if await opts.count() > 0 and await opts.first.is_visible():
                await opts.first.click()
                await _jitter(200, 400)
                log.debug("Filled Ashby location combobox with first autocomplete result")
                return True
        # Fallback: dismiss and leave what was typed
        await page.keyboard.press("Escape")
        log.debug("Ashby location combobox: no autocomplete options, left typed value")
    except Exception as e:
        log.debug("Ashby location combobox error: %s", e)
    return False


async def _fill_ashby_radios(page) -> None:
    """
    Fill Ashby radio button groups and remaining text inputs by scanning field entries.
    More reliable than ancestor XPath — walks all field entries and matches by question text.
    """
    _DECLINE_VALUES = ["decline", "prefer not", "do not wish", "i don't wish", "choose not"]
    try:
        entries = page.locator('[class*="_fieldEntry_"], [class*="ashby-application-form-field-entry"]')
        count = await entries.count()
        for i in range(count):
            entry = entries.nth(i)
            try:
                entry_text = (await entry.inner_text()).lower()
            except Exception:
                continue

            # --- Radio group handling ---
            radios = entry.locator('input[type="radio"]')
            radio_count = await radios.count()
            if radio_count > 0:
                picked = False

                # Years of experience
                if "years" in entry_text and "experience" in entry_text:
                    # Prefer any early-career option: "0-1", "1-2", "1-3", "less than", "<1"
                    _EARLY_CAREER = ["0-1", "1-2", "1-3", "less than", "<1", "0 to 1", "1 to 3"]
                    for j in range(radio_count):
                        r = radios.nth(j)
                        try:
                            parent = r.locator("xpath=parent::*")
                            opt_text = (await parent.first.inner_text()).lower() if await parent.count() > 0 else ""
                        except Exception:
                            opt_text = ""
                        if any(ec in opt_text for ec in _EARLY_CAREER):
                            try:
                                await r.click(force=True)
                            except Exception:
                                try:
                                    await page.evaluate("el => el.click()", await r.element_handle())
                                except Exception:
                                    pass
                            picked = True
                            log.debug("Ashby radio: years of experience → %s", opt_text.strip())
                            break
                    if not picked:
                        # Fallback: JS-click first radio (most likely the lowest range)
                        try:
                            r = radios.nth(0)
                            await page.evaluate("el => el.click()", await r.element_handle())
                            picked = True
                            log.debug("Ashby radio: years of experience → first option (fallback)")
                        except Exception:
                            pass

                # Office/relocation Yes/No radios — answer No (Toronto-based, not relocating)
                elif any(kw in entry_text for kw in ["days per week", "work from our", "relocate", "relocation", "willing to move", "in the bay area", "in the office"]):
                    # Find "No" radio — typically index 1, but scan for it
                    for j in range(radio_count):
                        r = radios.nth(j)
                        try:
                            parent = r.locator("xpath=parent::*")
                            opt_text = (await parent.first.inner_text()).lower() if await parent.count() > 0 else ""
                        except Exception:
                            opt_text = ""
                        if "no" in opt_text.strip().split():
                            try:
                                await r.click(force=True)
                            except Exception:
                                try:
                                    await page.evaluate("el => el.click()", await r.element_handle())
                                except Exception:
                                    pass
                            picked = True
                            log.debug("Ashby radio: office/relocation → No")
                            break
                    if not picked and radio_count >= 2:
                        # Fallback: second radio is usually "No"
                        try:
                            await page.evaluate("el => el.click()", await radios.nth(1).element_handle())
                            picked = True
                        except Exception:
                            pass

                # EEO fields: prefer decline
                elif any(h in entry_text for h in ["gender", "race", "veteran", "ethnicity", "hispanic"]):
                    for j in range(radio_count):
                        r = radios.nth(j)
                        try:
                            parent = r.locator("xpath=parent::*")
                            opt_text = (await parent.first.inner_text()).lower() if await parent.count() > 0 else ""
                        except Exception:
                            opt_text = ""
                        if any(d in opt_text for d in _DECLINE_VALUES):
                            try:
                                await r.click(force=True)
                            except Exception:
                                try:
                                    parent = r.locator("xpath=parent::*")
                                    if await parent.count() > 0:
                                        await parent.first.click()
                                except Exception:
                                    pass
                            picked = True
                            log.debug("Ashby radio: EEO → decline")
                            break

                await _jitter(100, 200)
                continue

            # --- Text input handling for named Ashby fields ---
            text_inp = entry.locator('input[type="text"]').first
            if await text_inp.count() == 0:
                continue
            val = await text_inp.input_value()
            if val:
                continue  # Already filled
            if not await text_inp.is_visible():
                continue

            if any(kw in entry_text for kw in ["salary", "compensation", "pay", "desired", "range", "expectation"]):
                await text_inp.fill("Open to discussion")
                await _jitter(100, 200)
                log.debug("Ashby field entry: salary/comp → Open to discussion")

    except Exception as e:
        log.debug("Ashby radio/field fill error: %s", e)


async def _try_upload(page, cv_text: str) -> bool:
    """Write CV to a temp file and upload it. Handles both direct input and button-triggered file choosers."""
    with tempfile.NamedTemporaryFile(
        suffix=".pdf", prefix="resume_", delete=False, mode="w", encoding="utf-8"
    ) as f:
        f.write(cv_text)
        tmp_path = f.name

    try:
        # 0. Ashby-specific: target file input inside the labeled "Resume" field entry
        try:
            resume_entry = page.locator('[class*="ashby-application-form-field-entry"]').filter(has_text="Resume")
            if await resume_entry.count() > 0:
                file_inp = resume_entry.first.locator('input[type="file"]').first
                if await file_inp.count() > 0:
                    await file_inp.set_input_files(tmp_path)
                    await _jitter(400, 800)
                    log.debug("Uploaded resume via Ashby resume field entry")
                    return True
        except Exception:
            pass

        # 1. Direct file input — prefer last match (Ashby puts autofill first, resume second)
        for sel in _RESUME_SELECTORS:
            try:
                all_els = page.locator(sel)
                count = await all_els.count()
                if count == 0:
                    continue
                for idx in range(count - 1, -1, -1):  # Last first = skip autofill inputs
                    try:
                        el = all_els.nth(idx)
                        await el.set_input_files(tmp_path)
                        await _jitter(300, 700)
                        log.debug("Uploaded resume via selector (idx %d): %s", idx, sel)
                        return True
                    except Exception:
                        continue
            except Exception:
                continue

        # 2. Button-triggered file chooser — prefer "Upload File" (capital F = resume, not autofill)
        upload_buttons = [
            'button:has-text("Upload File")',   # Ashby resume field (capital F)
            'button:has-text("Upload file")',
            'button:has-text("Upload")',
            'button:has-text("Attach")',
            'button:has-text("Choose file")',
            'label:has-text("Upload")',
        ]
        for sel in upload_buttons:
            try:
                btns = page.locator(sel)
                btn_count = await btns.count()
                for idx in range(btn_count - 1, -1, -1):  # Last first
                    btn = btns.nth(idx)
                    if not await btn.is_visible():
                        continue
                    try:
                        async with page.expect_file_chooser(timeout=3000) as fc_info:
                            await btn.click()
                        file_chooser = await fc_info.value
                        await file_chooser.set_files(tmp_path)
                        await _jitter(500, 900)
                        log.debug("Uploaded resume via file chooser: %s (idx %d)", sel, idx)
                        return True
                    except Exception:
                        continue
            except Exception:
                continue
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    return False


async def _fill_standard_fields(page, applicant: Applicant, cv: str, letter: str) -> dict:
    """Fill all standard form fields. Returns dict of what was filled."""
    filled = {}

    # Try split name first, then full name
    first, *rest = applicant.name.split(" ", 1)
    last = rest[0] if rest else ""

    if last and await _try_fill(page, _FIRST_NAME_SELECTORS, first, "first_name"):
        filled["first_name"] = True
        await _try_fill(page, _LAST_NAME_SELECTORS, last, "last_name")
        filled["last_name"] = True
    else:
        if await _try_fill(page, _NAME_SELECTORS, applicant.name, "name"):
            filled["name"] = True

    if await _try_fill(page, _EMAIL_SELECTORS, applicant.email, "email"):
        filled["email"] = True

    if applicant.phone and await _try_fill(page, _PHONE_SELECTORS, applicant.phone, "phone"):
        filled["phone"] = True

    if applicant.linkedin:
        if (await _try_fill(page, _LINKEDIN_SELECTORS, applicant.linkedin, "linkedin") or
                await _try_fill_by_label(page, _LINKEDIN_LABEL_HINTS, applicant.linkedin, "linkedin")):
            filled["linkedin"] = True

    # GitHub / website field (common on Greenhouse and Ashby)
    website = "https://github.com/Null-Phnix"
    if await _try_fill_by_label(page, _WEBSITE_LABEL_HINTS, website, "website"):
        filled["website"] = True

    # Location field — try freeform input first, then Ashby autocomplete combobox
    location_selectors = [
        'input[name*="location" i]',
        'input[placeholder*="location" i]',
        'input[id*="location" i]',
    ]
    if await _try_fill(page, location_selectors, "Toronto, ON, Canada", "location"):
        filled["location"] = True
    elif await _try_fill_by_label(page, ["location", "city", "where are you"], "Toronto, ON, Canada", "location"):
        filled["location"] = True
    elif await _fill_ashby_location_combobox(page):
        filled["location"] = True

    if await _try_upload(page, cv):
        filled["resume"] = True

    # Cover letter — try plain textarea first, then Greenhouse button pattern
    if (await _try_fill(page, _COVER_SELECTORS, letter, "cover_letter") or
            await _try_greenhouse_cover_letter(page, letter)):
        filled["cover_letter"] = True

    # Custom questions — React-select dropdowns, extra textareas, label-matched inputs
    await _fill_custom_questions(page, letter)

    # Ashby-specific: Yes/No button questions and radio groups
    await _fill_ashby_yesno(page)
    await _fill_ashby_radios(page)

    return filled


async def _submit(page) -> bool:
    for sel in _SUBMIT_SELECTORS:
        try:
            el = page.locator(sel).first
            if await el.count() > 0 and await el.is_visible():
                await _jitter(500, 1000)
                await el.click()
                await _jitter(2000, 4000)
                log.debug("Submitted via: %s", sel)
                return True
        except Exception:
            continue
    return False


async def _handle_verification_code(page, code: str) -> bool:
    """Enter Greenhouse email verification code if the screen appears."""
    try:
        # Greenhouse verification uses individual character input boxes
        boxes = page.locator('input[type="text"][maxlength="1"], input[maxlength="1"]')
        count = await boxes.count()
        if count >= 6 and len(code) >= count:
            for i in range(count):
                await boxes.nth(i).fill(code[i])
                await _jitter(80, 150)
            log.info("Entered %d-char verification code", count)
            # Click submit/verify button
            for sel in ['button[type="submit"]', 'button:has-text("Verify")',
                        'button:has-text("Submit")', 'button:has-text("Confirm")']:
                btn = page.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click()
                    await _jitter(2000, 3000)
                    return True
        # Fallback: single input field for the whole code
        single = page.get_by_label("Security code", exact=False).first
        if await single.count() == 0:
            single = page.locator('input[placeholder*="code" i]').first
        if await single.count() > 0 and await single.is_visible():
            await single.fill(code)
            await _jitter(200, 400)
            for sel in ['button[type="submit"]', 'button:has-text("Verify")',
                        'button:has-text("Submit")', 'button:has-text("Confirm")']:
                btn = page.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click()
                    await _jitter(2000, 3000)
                    return True
    except Exception as e:
        log.debug("Verification code entry error: %s", e)
    return False


async def apply_with_playwright(
    url: str,
    applicant: Applicant,
    cv: str,
    cover_letter: str,
    ats: str = "unknown",
    screenshot_on_fail: bool = True,
    verification_code: str = "",
) -> tuple[bool, str]:
    """
    Fill and submit a job application form using stealth Playwright.
    Returns (success, method_or_error).
    """
    try:
        from playwright.async_api import async_playwright
        from playwright_stealth import Stealth
    except ImportError:
        return False, "playwright not installed"

    apply_url = _get_apply_url(url, ats)
    log.info("Playwright apply: %s -> %s", ats, apply_url)

    # Ashby spam prevention — enforce per-domain cooldown
    if ats == "ashby":
        remaining = _check_ashby_cooldown(apply_url)
        if remaining is not None:
            log.warning("Ashby cooldown active for %s — %.0fs remaining, skipping", _get_domain(apply_url), remaining)
            return False, f"ashby_cooldown:{int(remaining)}s"

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="en-CA",
            timezone_id="America/Toronto",
        )
        page = await ctx.new_page()
        await Stealth().apply_stealth_async(page)

        try:
            try:
                await page.goto(apply_url, wait_until="networkidle", timeout=30000)
            except Exception:
                # Lever and some slow ATSs hang on networkidle — fall back to load event
                log.debug("networkidle timeout, retrying with load event")
                await page.goto(apply_url, wait_until="load", timeout=45000)

            # Use slower pacing for Lever to avoid triggering reCAPTCHA
            if ats == "lever":
                await _jitter_slow(1500, 3000)
            else:
                await _jitter(1000, 2000)

            # Early CAPTCHA check — look for visible challenge elements, not script references
            captcha_visible = False
            for captcha_sel in [
                'iframe[src*="recaptcha/api2/anchor"]:visible',
                'iframe[src*="hcaptcha.com/captcha"]:visible',
                '.g-recaptcha:visible',
                '#hcaptcha:visible',
            ]:
                if await page.locator(captcha_sel).count() > 0:
                    captcha_visible = True
                    break
            if captcha_visible:
                log.warning("CAPTCHA challenge visible on page load — cannot auto-apply (needs manual)")
                if screenshot_on_fail:
                    await _screenshot(page, url)
                return False, "captcha_required"

            filled = await _fill_standard_fields(page, applicant, cv, cover_letter)
            log.info("Fields filled: %s", list(filled.keys()))

            if not filled.get("email"):
                log.warning("Email field not found — form may have loaded differently")
                if screenshot_on_fail:
                    await _screenshot(page, url)
                return False, "email field not found"

            # Check for CAPTCHA before attempting submit — visible challenge only
            captcha_before_submit = False
            for captcha_sel in [
                'iframe[src*="recaptcha/api2/anchor"]:visible',
                'iframe[src*="hcaptcha.com/captcha"]:visible',
                '.g-recaptcha:visible',
                '#hcaptcha:visible',
                'iframe[title*="recaptcha" i]:visible',
            ]:
                if await page.locator(captcha_sel).count() > 0:
                    captcha_before_submit = True
                    break
            if captcha_before_submit:
                log.warning("CAPTCHA challenge visible before submit — cannot auto-submit (needs manual)")
                if screenshot_on_fail:
                    await _screenshot(page, url)
                return False, "captcha_required"

            submitted = await _submit(page)
            if not submitted:
                log.warning("Submit button not found")
                if screenshot_on_fail:
                    await _screenshot(page, url)
                return False, "submit button not found"

            # Check for email verification code screen
            await _jitter(1000, 2000)
            page_text = (await page.content()).lower()
            if "verification code" in page_text or "security code" in page_text:
                if verification_code:
                    log.info("Verification code screen detected — entering code")
                    await _handle_verification_code(page, verification_code)
                    await _jitter(2000, 3000)
                else:
                    log.warning("Verification code required — re-run with verification_code=")
                    if screenshot_on_fail:
                        await _screenshot(page, url)
                    return False, "needs_verification_code"

            # Check for success indicators
            await _jitter(1500, 3000)
            success = await _check_success(page)
            if success:
                log.info("Application submitted: %s", apply_url)
                if ats == "ashby":
                    _record_ashby_submission(apply_url)
                return True, f"playwright_{ats}"
            else:
                log.warning("No success confirmation detected after submit")
                if screenshot_on_fail:
                    await _screenshot(page, url)
                return False, "no success confirmation"

        except Exception as e:
            log.exception("Playwright apply error: %s", e)
            if screenshot_on_fail:
                try:
                    await _screenshot(page, url)
                except Exception:
                    pass
            return False, str(e)
        finally:
            await browser.close()


def _get_apply_url(job_url: str, ats: str) -> str:
    """Derive the direct application URL from job URL."""
    url = job_url.rstrip("/")
    if ats == "ashby":
        if "/application" not in url:
            return url + "/application"
        return url
    elif ats == "lever":
        if "/apply" not in url:
            return url + "/apply"
        return url
    elif ats == "greenhouse":
        # GH job boards use the absolute_url directly
        return url
    return url


async def _check_success(page) -> bool:
    """Check page for success confirmation text."""
    success_phrases = [
        "application submitted",
        "thank you for applying",
        "thanks for applying",
        "we've received your application",
        "application received",
        "successfully submitted",
        "you have applied",
        "your application has been submitted",
        "application has been received",
        "we have received your application",
        "you've successfully applied",
        "application complete",
    ]
    spam_phrases = [
        "flagged as possible spam",
        "submission was flagged",
        "marked as spam",
    ]
    try:
        content = (await page.content()).lower()
        if any(phrase in content for phrase in spam_phrases):
            log.warning("Application flagged as spam by ATS — needs manual retry later")
            return False
        return any(phrase in content for phrase in success_phrases)
    except Exception:
        return False


async def _screenshot(page, url: str) -> None:
    try:
        from pathlib import Path
        shots_dir = Path.home() / ".jobhound" / "screenshots"
        shots_dir.mkdir(parents=True, exist_ok=True)
        safe = url.replace("://", "_").replace("/", "_")[:60]
        path = shots_dir / f"{safe}_{int(time.time())}.png"
        await page.screenshot(path=str(path))
        log.info("Screenshot saved: %s", path)
    except Exception as e:
        log.warning("Screenshot failed: %s", e)


def run_playwright_apply(
    url: str,
    applicant: Applicant,
    cv: str,
    cover_letter: str,
    ats: str = "unknown",
) -> tuple[bool, str]:
    """Sync wrapper around async Playwright apply."""
    return asyncio.run(apply_with_playwright(url, applicant, cv, cover_letter, ats))
