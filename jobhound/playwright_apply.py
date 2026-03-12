"""
Stealth Playwright-based application submitter for Ashby, Greenhouse, and Lever.

Strategy per ATS:
  Ashby     — navigate to applyUrl, fill standard + custom fields, submit
  Greenhouse — navigate to absolute_url, fill form, submit
  Lever     — navigate to hostedUrl + /apply, fill form, submit
  Fallback  — Blackreach for anything else
"""
import asyncio
import random
import tempfile
import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from jobhound.log import get_logger

log = get_logger("jobhound.playwright")

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
]
_SUBMIT_SELECTORS = [
    'button[type="submit"]',
    'input[type="submit"]',
    'button:has-text("Submit")',
    'button:has-text("Apply")',
    'button:has-text("Send application")',
]


@dataclass
class Applicant:
    name: str
    email: str
    phone: str
    linkedin: str = ""


async def _jitter(min_ms: int = 400, max_ms: int = 1200) -> None:
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


async def _try_upload(page, cv_text: str) -> bool:
    """Write CV to a temp file and upload it."""
    with tempfile.NamedTemporaryFile(
        suffix=".txt", prefix="resume_", delete=False, mode="w", encoding="utf-8"
    ) as f:
        f.write(cv_text)
        tmp_path = f.name

    for sel in _RESUME_SELECTORS:
        try:
            el = page.locator(sel).first
            if await el.count() > 0:
                await el.set_input_files(tmp_path)
                await _jitter(300, 700)
                log.debug("Uploaded resume via: %s", sel)
                Path(tmp_path).unlink(missing_ok=True)
                return True
        except Exception:
            continue
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

    if applicant.linkedin and await _try_fill(page, _LINKEDIN_SELECTORS, applicant.linkedin, "linkedin"):
        filled["linkedin"] = True

    if await _try_upload(page, cv):
        filled["resume"] = True

    if await _try_fill(page, _COVER_SELECTORS, letter, "cover_letter"):
        filled["cover_letter"] = True

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


async def apply_with_playwright(
    url: str,
    applicant: Applicant,
    cv: str,
    cover_letter: str,
    ats: str = "unknown",
    screenshot_on_fail: bool = True,
) -> tuple[bool, str]:
    """
    Fill and submit a job application form using stealth Playwright.
    Returns (success, method_or_error).
    """
    try:
        from playwright.async_api import async_playwright
        from playwright_stealth import stealth_async
    except ImportError:
        return False, "playwright not installed"

    apply_url = _get_apply_url(url, ats)
    log.info("Playwright apply: %s -> %s", ats, apply_url)

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
        await stealth_async(page)

        try:
            await page.goto(apply_url, wait_until="networkidle", timeout=30000)
            await _jitter(1000, 2000)

            filled = await _fill_standard_fields(page, applicant, cv, cover_letter)
            log.info("Fields filled: %s", list(filled.keys()))

            if not filled.get("email"):
                log.warning("Email field not found — form may have loaded differently")
                if screenshot_on_fail:
                    await _screenshot(page, url)
                return False, "email field not found"

            submitted = await _submit(page)
            if not submitted:
                log.warning("Submit button not found")
                if screenshot_on_fail:
                    await _screenshot(page, url)
                return False, "submit button not found"

            # Check for success indicators
            await _jitter(1500, 3000)
            success = await _check_success(page)
            if success:
                log.info("Application submitted: %s", apply_url)
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
    ]
    try:
        content = (await page.content()).lower()
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
