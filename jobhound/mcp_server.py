"""
JobHound MCP Server — exposes JobHound as Claude Code tools.
No separate Anthropic API key needed. Claude Code IS the tailor.

Workflow:
  1. jobhound_scan()                          — fetch, score, queue high-scoring jobs
  2. jobhound_list("queued")                  — see what needs tailoring (with IDs)
  3. jobhound_get_for_tailoring(id)           — get job + resume for a specific job
  4. [Claude generates tailored CV + letter]
  5. jobhound_apply_tailored(id, cv, letter)  — submit and record

Other tools:
  jobhound_status()       — summary stats
  jobhound_get(id)        — full job details
  jobhound_update(id, s)  — manually update status (interviewing, rejected, etc.)
  jobhound_pause/resume() — daemon control
"""
import os
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from jobhound.config import load_config
from jobhound.tracker import Tracker
from jobhound.models import Status
import jobhound.daemon as daemon_module

# Always resolve config relative to the installed package root, never cwd
_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
_CONFIG_PATH = Path(os.environ.get("JOBHOUND_ROOT", _PROJECT_ROOT)) / "config.yaml"

mcp = FastMCP("jobhound")

_tracker: Tracker = None
_cfg = None


def _get_tracker() -> Tracker:
    global _tracker, _cfg
    if _tracker is None:
        _cfg = load_config(_CONFIG_PATH)
        _tracker = Tracker(_cfg.db_path)
        _tracker.init()
    return _tracker


def _get_cfg():
    _get_tracker()
    return _cfg


@mcp.tool()
def jobhound_scan() -> str:
    """
    Fetch jobs from all configured sources, score them, and queue high-scoring ones.
    Jobs above score threshold are saved with status 'queued'.
    Returns a summary + list of queued job IDs ready for tailoring.
    Next step: call jobhound_list('queued') then jobhound_get_for_tailoring(id).
    """
    cfg = _get_cfg()
    t = _get_tracker()

    from jobhound.scorer import Scorer
    from jobhound.daemon import _build_sources
    scorer = Scorer(cfg.skills_path)
    sources = _build_sources(cfg)

    all_jobs = []
    source_errors = []
    for source in sources:
        try:
            fetched = source.fetch()
            all_jobs.extend(fetched)
        except Exception as e:
            source_errors.append(f"{source.__class__.__name__}: {e}")

    queued_count = 0
    skipped_seen = 0
    skipped_score = 0

    for job in all_jobs:
        if t.seen(job.url):
            skipped_seen += 1
            continue
        job.score = scorer.score(job)
        if job.score < cfg.score_threshold:
            job.status = Status.NEW
            t.record(job)
            skipped_score += 1
        else:
            job.status = Status.QUEUED
            t.record(job)
            queued_count += 1

    lines = [
        f"Scan complete.",
        f"  Fetched: {len(all_jobs)} | Already seen: {skipped_seen} | Below threshold: {skipped_score} | Queued: {queued_count}",
    ]
    if source_errors:
        lines.append(f"  Source errors: {', '.join(source_errors)}")

    if queued_count == 0:
        lines.append("\nNothing new to apply to.")
        return "\n".join(lines)

    # Show what was queued
    queued_jobs = t.list_by_status(Status.QUEUED)
    lines.append(f"\nQueued jobs ready for tailoring:")
    for job in queued_jobs:
        lines.append(f"  ID {job.db_id}: {job.company} — {job.title} (score={job.score})")

    lines.append(f"\nNext: call jobhound_get_for_tailoring(id) for each, then jobhound_apply_tailored().")
    return "\n".join(lines)


@mcp.tool()
def jobhound_list(status: str = "queued") -> str:
    """
    List jobs by status with their database IDs.
    Args:
        status: one of new, queued, applied, failed, interviewing, rejected
    """
    t = _get_tracker()
    try:
        s = Status(status)
    except ValueError:
        return f"Invalid status '{status}'. Use: new, queued, applied, failed, interviewing, rejected"

    jobs = t.list_by_status(s)
    if not jobs:
        return f"No jobs with status '{status}'."

    lines = [f"Jobs with status '{status}' ({len(jobs)} total):\n"]
    for job in jobs[:30]:
        lines.append(f"ID {job.db_id}: {job.company} — {job.title}")
        lines.append(f"  Score: {job.score} | Source: {job.source}")
        if job.applied_at:
            lines.append(f"  Applied: {job.applied_at} via {job.method}")
        else:
            lines.append(f"  URL: {job.url}")
    return "\n".join(lines)


@mcp.tool()
def jobhound_get_for_tailoring(job_id: int) -> str:
    """
    Get everything needed to write a tailored application for a job.
    Returns the job description and the full resume.
    After reading this, generate a tailored CV and cover letter, then call
    jobhound_apply_tailored(job_id, tailored_cv, cover_letter).

    Args:
        job_id: integer ID from jobhound_list('queued')
    """
    t = _get_tracker()
    cfg = _get_cfg()
    job = t.get_by_id(job_id)
    if not job:
        return f"Job {job_id} not found."
    if job.status not in (Status.QUEUED, Status.FAILED):
        return (
            f"Job {job_id} has status '{job.status.value}'. "
            f"Only queued or failed jobs need tailoring."
        )

    try:
        resume = cfg.resume_path.read_text()
    except Exception as e:
        resume = f"[Could not read resume: {e}]"

    return f"""JOB ID: {job_id}
Company: {job.company}
Title: {job.title}
Location: {job.location or 'Not specified'}
Remote: {job.remote}
Score: {job.score}
Source: {job.source}
URL: {job.url}

=== JOB DESCRIPTION ===
{job.description[:4000] or '[No description available — tailor based on title/company]'}

=== RESUME ===
{resume}

---
Now generate a tailored CV and cover letter, then call:
  jobhound_apply_tailored(job_id={job_id}, tailored_cv="...", cover_letter="...")

Cover letter: direct voice, no em dashes, no corporate speak, no filler.
Lead with the most relevant project. Own any gaps honestly. 3-5 short paragraphs max.
Tailored CV: same markdown format, reorder/emphasize for this role. Do not invent experience."""


@mcp.tool()
def jobhound_apply_tailored(job_id: int, tailored_cv: str, cover_letter: str) -> str:
    """
    Submit an application using the tailored CV and cover letter.
    Tries: LinkedIn MCP → direct POST (Ashby/Lever) → Blackreach fallback.
    Records the outcome in the database.

    Args:
        job_id: integer ID of the job
        tailored_cv: the tailored CV text (markdown)
        cover_letter: the cover letter text
    """
    t = _get_tracker()
    cfg = _get_cfg()
    job = t.get_by_id(job_id)
    if not job:
        return f"Job {job_id} not found."

    from jobhound.apply import Applier, ApplicantInfo
    applier = Applier(
        applicant=ApplicantInfo(
            name=cfg.applicant_name,
            email=cfg.applicant_email,
            phone=cfg.applicant_phone,
            linkedin=cfg.applicant_linkedin,
        ),
        blackreach_server=cfg.blackreach_server,
        linkedin_server=cfg.linkedin_server,
    )
    result = applier.submit(job, cv=tailored_cv, cover_letter=cover_letter)

    status = Status.APPLIED if result.success else Status.FAILED
    t.update_status(
        job.url, status,
        method=result.method,
        cover_letter=cover_letter,
        cv_used=tailored_cv,
        notes=result.error,
    )

    if result.success:
        return (
            f"Applied to {job.company} — {job.title} via {result.method}.\n"
            f"Status: applied. ID: {job_id}"
        )
    return (
        f"Application failed for {job.company} — {job.title}.\n"
        f"Error: {result.error}\n"
        f"Status: failed. Retry with jobhound_apply_tailored({job_id}, ...) after fixing the issue."
    )


@mcp.tool()
def jobhound_status() -> str:
    """Summary of JobHound activity: job counts by status."""
    t = _get_tracker()
    stats = t.stats()
    order = ["queued", "applied", "interviewing", "failed", "rejected", "new"]
    lines = ["JobHound Status:"]
    for s in order:
        count = stats.get(s, 0)
        if count:
            lines.append(f"  {s}: {count}")
    lines.append(f"\nTotal: {sum(stats.values())}")
    lines.append(f"Daemon: {'[PAUSED]' if daemon_module._paused else '[LIVE]'}")
    return "\n".join(lines)


@mcp.tool()
def jobhound_get(job_id: int) -> str:
    """
    Get full details for a job including cover letter if applied.
    Args:
        job_id: integer ID
    """
    t = _get_tracker()
    job = t.get_by_id(job_id)
    if not job:
        return f"Job {job_id} not found."
    lines = [
        f"ID: {job_id}",
        f"Company: {job.company}",
        f"Title: {job.title}",
        f"Status: {job.status.value}",
        f"Score: {job.score}",
        f"Source: {job.source}",
        f"URL: {job.url}",
        f"Applied: {job.applied_at or 'N/A'} via {job.method or 'N/A'}",
        "",
    ]
    if job.cover_letter:
        lines += ["Cover Letter:", "---", job.cover_letter, "---"]
    if job.notes:
        lines += [f"Notes: {job.notes}"]
    return "\n".join(lines)


@mcp.tool()
def jobhound_update(job_id: int, status: str) -> str:
    """
    Manually update a job's status.
    Use this when you get an interview invite or rejection.
    Args:
        job_id: integer ID
        status: interviewing, rejected, applied, failed, queued
    """
    t = _get_tracker()
    job = t.get_by_id(job_id)
    if not job:
        return f"Job {job_id} not found."
    try:
        s = Status(status)
    except ValueError:
        return f"Invalid status '{status}'."
    t.update_status(job.url, s)
    return f"Updated ID {job_id} ({job.company} — {job.title}) → '{status}'."


@mcp.tool()
def jobhound_pause() -> str:
    """Pause the JobHound daemon (scan loop stops applying)."""
    daemon_module._paused = True
    return "JobHound paused."


@mcp.tool()
def jobhound_resume() -> str:
    """Resume the JobHound daemon."""
    daemon_module._paused = False
    return "JobHound resumed."


def main():
    mcp.run()


if __name__ == "__main__":
    main()
