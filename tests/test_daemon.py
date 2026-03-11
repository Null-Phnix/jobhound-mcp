from unittest.mock import MagicMock
from jobhound.daemon import run_cycle
from jobhound.models import Job, Status
from jobhound.apply import ApplyResult


def make_job(url, score=50):
    return Job(url=url, source="ashby", company="Co", title="Eng", score=score)


def test_run_cycle_applies_new_jobs():
    tracker = MagicMock()
    tracker.seen.return_value = False

    scorer = MagicMock()
    scorer.score.return_value = 60

    tailor = MagicMock()
    tailor.generate.return_value = ("cv text", "cover letter text")

    applier = MagicMock()
    applier.submit.return_value = ApplyResult(success=True, method="direct_post")

    jobs = [make_job("https://x.com/1"), make_job("https://x.com/2")]
    sources = [MagicMock()]
    sources[0].fetch.return_value = jobs

    run_cycle(sources=sources, scorer=scorer, tailor=tailor,
              applier=applier, tracker=tracker, threshold=30)

    assert applier.submit.call_count == 2
    assert tracker.update_status.call_count == 2


def test_run_cycle_skips_seen_jobs():
    tracker = MagicMock()
    tracker.seen.return_value = True  # all already seen

    scorer = MagicMock()
    tailor = MagicMock()
    applier = MagicMock()

    sources = [MagicMock()]
    sources[0].fetch.return_value = [make_job("https://x.com/1")]

    run_cycle(sources=sources, scorer=scorer, tailor=tailor,
              applier=applier, tracker=tracker, threshold=30)

    applier.submit.assert_not_called()


def test_run_cycle_skips_below_threshold():
    tracker = MagicMock()
    tracker.seen.return_value = False
    scorer = MagicMock()
    scorer.score.return_value = 10  # below threshold
    tailor = MagicMock()
    applier = MagicMock()
    sources = [MagicMock()]
    sources[0].fetch.return_value = [make_job("https://x.com/1")]

    run_cycle(sources=sources, scorer=scorer, tailor=tailor,
              applier=applier, tracker=tracker, threshold=30)

    applier.submit.assert_not_called()
    # Still records below-threshold job
    tracker.record.assert_called_once()


def test_run_cycle_records_failed_apply():
    tracker = MagicMock()
    tracker.seen.return_value = False
    scorer = MagicMock()
    scorer.score.return_value = 50
    tailor = MagicMock()
    tailor.generate.return_value = ("cv", "letter")
    applier = MagicMock()
    applier.submit.return_value = ApplyResult(success=False, error="All strategies failed")
    sources = [MagicMock()]
    sources[0].fetch.return_value = [make_job("https://x.com/1")]

    run_cycle(sources=sources, scorer=scorer, tailor=tailor,
              applier=applier, tracker=tracker, threshold=30)

    tracker.update_status.assert_called_once()
    call_args = tracker.update_status.call_args
    assert call_args[0][1] == Status.FAILED


def test_run_cycle_handles_source_error():
    tracker = MagicMock()
    scorer = MagicMock()
    tailor = MagicMock()
    applier = MagicMock()

    bad_source = MagicMock()
    bad_source.fetch.side_effect = Exception("network error")

    run_cycle(sources=[bad_source], scorer=scorer, tailor=tailor,
              applier=applier, tracker=tracker, threshold=30)

    # Should not crash, just skip the broken source
    applier.submit.assert_not_called()
