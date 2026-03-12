import random
import signal
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from jobhound.apply import Applier, ApplicantInfo
from jobhound.config import load_config
from jobhound.log import get_logger
from jobhound.models import Status
from jobhound.scorer import Scorer
from jobhound.sources.ashby import AshbySource
from jobhound.sources.greenhouse import GreenhouseSource
from jobhound.sources.hn_hiring import HNHiringSource
from jobhound.sources.lever import LeverSource
from jobhound.sources.remoteok import RemoteOKSource
from jobhound.sources.wellfound import WellfoundSource
from jobhound.tailor import Tailor
from jobhound.tracker import Tracker

log = get_logger("jobhound.daemon")

_paused = False
_shutdown = False


def _handle_sigterm(signum, frame):
    global _shutdown
    log.info("Daemon: received SIGTERM — shutting down after current cycle")
    _shutdown = True


signal.signal(signal.SIGTERM, _handle_sigterm)
signal.signal(signal.SIGINT, _handle_sigterm)


def run_cycle(sources, scorer, tailor, applier, tracker, threshold: int):
    """Single scan + apply cycle. Separated from daemon loop for testability."""
    all_jobs = []
    for source in sources:
        try:
            fetched = source.fetch()
            all_jobs.extend(fetched)
        except Exception as e:
            log.exception("Source %s error: %s", source.__class__.__name__, e)

    log.info("Daemon: fetched %d jobs across all sources", len(all_jobs))
    applied = 0

    for job in all_jobs:
        if _shutdown:
            log.info("Daemon: shutdown requested, stopping mid-cycle")
            return

        if tracker.seen(job.url):
            continue

        job.score = scorer.score(job)
        if job.score < threshold:
            tracker.record(job)
            continue

        log.info("Daemon: tailoring %s — %s (score=%d)", job.company, job.title, job.score)
        try:
            cv, letter = tailor.generate(job)
        except Exception as e:
            log.exception("Daemon: tailor error for %s — %s: %s", job.company, job.title, e)
            tracker.record(job)
            continue

        result = applier.submit(job, cv=cv, cover_letter=letter)
        status = Status.APPLIED if result.success else Status.FAILED
        tracker.record(job)
        tracker.update_status(
            job.url, status,
            method=result.method,
            cover_letter=letter,
            cv_used=cv,
            notes=result.error,
        )
        applied += 1
        log.info(
            "Daemon: %s %s — %s (method=%s)",
            "applied to" if result.success else "failed",
            job.company, job.title, result.method or result.error,
        )

    log.info("Daemon: cycle complete — applied to %d jobs", applied)


def _build_sources(cfg) -> list:
    sources = []
    if cfg.ashby_slugs:
        sources.append(AshbySource(cfg.ashby_slugs))
    if cfg.greenhouse_slugs:
        sources.append(GreenhouseSource(cfg.greenhouse_slugs))
    if cfg.lever_slugs:
        sources.append(LeverSource(cfg.lever_slugs))
    if cfg.remoteok:
        sources.append(RemoteOKSource())
    if cfg.hn_hiring:
        sources.append(HNHiringSource())
    if cfg.wellfound_query:
        sources.append(WellfoundSource(cfg.blackreach_server, cfg.wellfound_query, cfg.wellfound_remote_only))
    return sources


def main():
    global _paused
    config_path = Path("config.yaml")
    if not config_path.exists():
        log.error("config.yaml not found — run from JobHound project root")
        sys.exit(1)

    cfg = load_config(config_path)
    tracker = Tracker(cfg.db_path)
    tracker.init()
    scorer = Scorer(cfg.skills_path)
    tailor = Tailor(cfg.resume_path, cfg.sonnet_threshold)
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
    sources = _build_sources(cfg)

    log.info(
        "Daemon starting — %d sources, interval=%dh, threshold=%d",
        len(sources), cfg.interval_hours, cfg.score_threshold,
    )

    while not _shutdown:
        if not _paused:
            run_cycle(sources, scorer, tailor, applier, tracker, cfg.score_threshold)

        if _shutdown:
            break

        # Sleep in small increments so SIGTERM is handled promptly
        sleep_secs = cfg.interval_hours * 3600
        # Add ±5 min jitter so parallel daemons don't hammer sources simultaneously
        sleep_secs += random.randint(-300, 300)
        log.info("Daemon: sleeping %.0f seconds until next cycle", sleep_secs)
        deadline = time.time() + sleep_secs
        while time.time() < deadline and not _shutdown:
            time.sleep(5)

    log.info("Daemon: shut down cleanly")


if __name__ == "__main__":
    main()
