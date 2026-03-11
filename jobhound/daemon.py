import time
import sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")
from jobhound.config import load_config
from jobhound.tracker import Tracker
from jobhound.scorer import Scorer
from jobhound.tailor import Tailor
from jobhound.apply import Applier
from jobhound.models import Status
from jobhound.sources.ashby import AshbySource
from jobhound.sources.greenhouse import GreenhouseSource
from jobhound.sources.lever import LeverSource
from jobhound.sources.remoteok import RemoteOKSource
from jobhound.sources.hn_hiring import HNHiringSource
from jobhound.sources.wellfound import WellfoundSource

_paused = False


def run_cycle(sources, scorer, tailor, applier, tracker, threshold: int):
    """Single scan + apply cycle. Separated from daemon loop for testability."""
    all_jobs = []
    for source in sources:
        try:
            all_jobs.extend(source.fetch())
        except Exception as e:
            print(f"[JobHound] Source error: {e}")

    print(f"[JobHound] Fetched {len(all_jobs)} jobs")
    applied = 0

    for job in all_jobs:
        if tracker.seen(job.url):
            continue

        job.score = scorer.score(job)
        if job.score < threshold:
            tracker.record(job)  # record below-threshold jobs for visibility
            continue

        print(f"[JobHound] Tailoring: {job.company} — {job.title} (score={job.score})")
        try:
            cv, letter = tailor.generate(job)
        except Exception as e:
            print(f"[JobHound] Tailor error: {e}")
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
        print(f"[JobHound] {'Applied' if result.success else 'Failed'}: {job.company} — {job.title}")

    print(f"[JobHound] Cycle complete. Applied to {applied} jobs.")


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
        print("config.yaml not found. Run from JobHound project root.")
        sys.exit(1)

    cfg = load_config(config_path)
    tracker = Tracker(cfg.db_path)
    tracker.init()
    scorer = Scorer(cfg.skills_path)
    tailor = Tailor(cfg.resume_path, cfg.sonnet_threshold)
    applier = Applier(cfg.linkedin_server, cfg.blackreach_server)
    sources = _build_sources(cfg)

    print(f"[JobHound] Starting daemon — scanning every {cfg.interval_hours}h with {len(sources)} sources")
    while True:
        if not _paused:
            run_cycle(sources, scorer, tailor, applier, tracker, cfg.score_threshold)
        time.sleep(cfg.interval_hours * 3600)


if __name__ == "__main__":
    main()
