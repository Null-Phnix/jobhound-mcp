from jobhound.models import Job, Status


def test_job_defaults():
    job = Job(url="https://example.com", source="ashby", company="Acme", title="AI Engineer")
    assert job.status == Status.NEW
    assert job.score == 0
    assert job.remote is False


def test_job_url_is_dedup_key():
    j1 = Job(url="https://x.com/job/1", source="ashby", company="A", title="Eng")
    j2 = Job(url="https://x.com/job/1", source="ashby", company="A", title="Eng")
    assert j1.url == j2.url


def test_status_enum_values():
    assert Status.NEW == "new"
    assert Status.APPLIED == "applied"
    assert Status.FAILED == "failed"
    assert Status.INTERVIEWING == "interviewing"
    assert Status.REJECTED == "rejected"


def test_job_to_dict():
    job = Job(url="https://x.com", source="remoteok", company="Co", title="Dev")
    d = job.to_dict()
    assert d["url"] == "https://x.com"
    assert d["status"] == "new"
