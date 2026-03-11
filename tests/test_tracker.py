import pytest
from jobhound.tracker import Tracker
from jobhound.models import Job, Status


@pytest.fixture
def tracker(tmp_path):
    db = tmp_path / "test.db"
    t = Tracker(db)
    t.init()
    return t


def test_init_creates_table(tracker):
    assert tracker is not None


def test_seen_false_for_new_url(tracker):
    assert tracker.seen("https://example.com/job/1") is False


def test_record_and_seen(tracker):
    job = Job(url="https://x.com/1", source="ashby", company="Acme", title="Eng")
    tracker.record(job)
    assert tracker.seen("https://x.com/1") is True


def test_get_by_status(tracker):
    j1 = Job(url="https://x.com/1", source="ashby", company="A", title="E1", status=Status.APPLIED)
    j2 = Job(url="https://x.com/2", source="ashby", company="B", title="E2", status=Status.NEW)
    tracker.record(j1)
    tracker.record(j2)
    applied = tracker.list_by_status(Status.APPLIED)
    assert len(applied) == 1
    assert applied[0].url == "https://x.com/1"


def test_update_status(tracker):
    job = Job(url="https://x.com/1", source="ashby", company="A", title="E")
    tracker.record(job)
    tracker.update_status("https://x.com/1", Status.APPLIED, method="direct_post")
    jobs = tracker.list_by_status(Status.APPLIED)
    assert jobs[0].method == "direct_post"
    assert jobs[0].applied_at is not None


def test_stats(tracker):
    for i, status in enumerate([Status.APPLIED, Status.APPLIED, Status.FAILED, Status.NEW]):
        tracker.record(Job(url=f"https://x.com/{i}", source="s", company="C", title="T", status=status))
    stats = tracker.stats()
    assert stats["applied"] == 2
    assert stats["failed"] == 1
    assert stats["new"] == 1


def test_get_by_id(tracker):
    job = Job(url="https://x.com/99", source="ashby", company="Acme", title="Senior Eng")
    tracker.record(job)
    # get all to find the id
    jobs = tracker.get_all()
    assert len(jobs) == 1
    found = tracker.get_by_id(1)
    assert found is not None
    assert found.title == "Senior Eng"


def test_record_is_idempotent(tracker):
    job = Job(url="https://x.com/1", source="ashby", company="A", title="E")
    tracker.record(job)
    tracker.record(job)  # second insert should be ignored
    jobs = tracker.get_all()
    assert len(jobs) == 1
