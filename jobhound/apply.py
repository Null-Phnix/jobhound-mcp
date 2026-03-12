"""
Application submission pipeline.

Strategy cascade per job URL:
  1. Stealth Playwright — Ashby, Greenhouse, Lever (native ATS forms)
  2. Blackreach fallback — anything else or if Playwright fails
"""
import random
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import httpx

from jobhound.log import get_logger
from jobhound.models import Job

log = get_logger("jobhound.apply")

_UA_POOL = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0",
]


@dataclass
class ApplicantInfo:
    name: str
    email: str
    phone: str
    linkedin: str = ""


@dataclass
class ApplyResult:
    success: bool
    method: Optional[str] = None
    error: Optional[str] = None


def _detect_ats(url: str) -> str:
    if "ashbyhq.com" in url or "jobs.ashbyhq.com" in url:
        return "ashby"
    if "greenhouse.io" in url or "job-boards.greenhouse.io" in url:
        return "greenhouse"
    if "lever.co" in url or "jobs.lever.co" in url:
        return "lever"
    if "linkedin.com" in url:
        return "linkedin"
    return "unknown"


class Applier:
    def __init__(
        self,
        applicant: ApplicantInfo,
        blackreach_server: str = "http://localhost:7432",
        linkedin_server: str = "http://localhost:7433",
    ):
        self.applicant = applicant
        self.blackreach = blackreach_server
        self.linkedin = linkedin_server

    def submit(self, job: Job, cv: str, cover_letter: str) -> ApplyResult:
        """Try apply strategies in order. Returns first success."""
        ats = _detect_ats(job.url)
        log.info("Submitting: %s — %s (ats=%s)", job.company, job.title, ats)

        # 1. LinkedIn MCP
        if ats == "linkedin":
            result = self._try_linkedin(job, cover_letter)
            if result.success:
                return result

        # 2. Stealth Playwright for known ATSs
        if ats in ("ashby", "greenhouse", "lever"):
            result = self._try_playwright(job, cv, cover_letter, ats)
            if result.success:
                return result
            log.warning("Playwright failed (%s), falling back to Blackreach", result.error)

        # 3. Blackreach fallback
        result = self._try_blackreach(job, cv, cover_letter)
        if result.success:
            return result

        log.error("All strategies failed for: %s — %s", job.company, job.title)
        return ApplyResult(success=False, error="All apply strategies failed")

    def _try_playwright(self, job: Job, cv: str, cover_letter: str, ats: str) -> ApplyResult:
        try:
            from jobhound.playwright_apply import run_playwright_apply, Applicant
            applicant = Applicant(
                name=self.applicant.name,
                email=self.applicant.email,
                phone=self.applicant.phone,
                linkedin=self.applicant.linkedin,
            )
            success, method_or_err = run_playwright_apply(
                url=job.url,
                applicant=applicant,
                cv=cv,
                cover_letter=cover_letter,
                ats=ats,
            )
            if success:
                return ApplyResult(success=True, method=method_or_err)
            return ApplyResult(success=False, error=method_or_err)
        except Exception as e:
            log.exception("Playwright error: %s", e)
            return ApplyResult(success=False, error=f"playwright exception: {e}")

    def _try_linkedin(self, job: Job, cover_letter: str) -> ApplyResult:
        try:
            resp = httpx.post(
                f"{self.linkedin}/apply",
                json={"profile_url": job.url, "message": cover_letter[:300]},
                headers={"User-Agent": random.choice(_UA_POOL)},
                timeout=10,
            )
            if resp.status_code != 200:
                log.warning("LinkedIn MCP returned %d", resp.status_code)
                return ApplyResult(success=False, error=f"linkedin_mcp http {resp.status_code}")

            job_id = resp.json().get("job_id")
            if not job_id:
                return ApplyResult(success=False, error="linkedin_mcp no job_id")

            deadline = time.time() + 90
            while time.time() < deadline:
                time.sleep(random.uniform(3, 6))
                r = httpx.get(
                    f"{self.linkedin}/jobs/{job_id}",
                    headers={"User-Agent": random.choice(_UA_POOL)},
                    timeout=10,
                ).json()
                status = r.get("status")
                if status == "done":
                    if r.get("result", {}).get("success", False):
                        return ApplyResult(success=True, method="linkedin_mcp")
                    return ApplyResult(success=False, error="linkedin_mcp reported failure")
                if status == "failed":
                    return ApplyResult(success=False, error=f"linkedin_mcp: {r.get('error')}")

            return ApplyResult(success=False, error="linkedin_mcp timeout")
        except Exception as e:
            log.exception("LinkedIn error: %s", e)
            return ApplyResult(success=False, error=f"linkedin exception: {e}")

    def _try_blackreach(self, job: Job, cv: str, cover_letter: str) -> ApplyResult:
        try:
            goal = (
                f"Apply for the job posting at {job.url}. "
                f"Company: {job.company}. Title: {job.title}.\n\n"
                f"Applicant name: {self.applicant.name}\n"
                f"Email: {self.applicant.email}\n"
                f"Phone: {self.applicant.phone}\n\n"
                f"COVER LETTER (use verbatim in any cover letter or message field):\n"
                f"{cover_letter}\n\n"
                f"RESUME (use for any resume or CV text fields):\n"
                f"{cv[:3000]}"
            )
            resp = httpx.post(
                f"{self.blackreach}/browse",
                json={"goal": goal},
                headers={"User-Agent": random.choice(_UA_POOL)},
                timeout=15,
            )
            if resp.status_code not in (200, 202):
                log.warning("Blackreach returned %d", resp.status_code)
                return ApplyResult(success=False, error=f"blackreach http {resp.status_code}")

            job_id = resp.json().get("job_id")
            if not job_id:
                return ApplyResult(success=False, error="blackreach no job_id")

            deadline = time.time() + 300
            while time.time() < deadline:
                time.sleep(random.uniform(8, 14))
                try:
                    r = httpx.get(
                        f"{self.blackreach}/jobs/{job_id}",
                        headers={"User-Agent": random.choice(_UA_POOL)},
                        timeout=10,
                    ).json()
                    if r.get("status") == "done":
                        return ApplyResult(success=True, method="blackreach")
                    if r.get("status") == "failed":
                        err = r.get("error") or "blackreach task failed"
                        log.warning("Blackreach failed: %s", err)
                        return ApplyResult(success=False, error=err)
                except Exception as poll_err:
                    log.warning("Blackreach poll error: %s", poll_err)

            return ApplyResult(success=False, error="blackreach timeout 300s")
        except Exception as e:
            log.exception("Blackreach error: %s", e)
            return ApplyResult(success=False, error=f"blackreach exception: {e}")
