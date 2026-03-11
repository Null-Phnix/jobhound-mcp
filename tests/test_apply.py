import respx
import httpx
from unittest.mock import patch
from jobhound.apply import Applier, ApplyResult
from jobhound.models import Job


def make_applier():
    return Applier(
        linkedin_server="http://localhost:7433",
        blackreach_server="http://localhost:7432",
    )


@respx.mock
def test_direct_post_ashby():
    applier = make_applier()
    job = Job(url="https://jobs.ashbyhq.com/modal/abc123",
              source="ashby", company="modal", title="Eng")
    respx.post("https://api.ashbyhq.com/posting-api/application/modal").mock(
        return_value=httpx.Response(200, json={"success": True})
    )
    result = applier.submit(job, cv="cv text", cover_letter="letter text")
    assert result.success is True
    assert result.method == "ashby_direct"


@respx.mock
def test_linkedin_apply():
    applier = make_applier()
    job = Job(url="https://www.linkedin.com/jobs/view/123",
              source="linkedin", company="Bree", title="Backend Eng")
    respx.post("http://localhost:7433/apply").mock(
        return_value=httpx.Response(200, json={"job_id": "abc"})
    )
    respx.get("http://localhost:7433/jobs/abc").mock(
        return_value=httpx.Response(200, json={"status": "done", "result": {"success": True}})
    )
    result = applier.submit(job, cv="cv", cover_letter="letter")
    assert result.method == "linkedin_mcp"
    assert result.success is True


def test_returns_failed_on_error():
    applier = make_applier()
    job = Job(url="https://unknownsite.com/job/1",
              source="other", company="X", title="Eng")
    with patch.object(applier, "_try_blackreach", return_value=None):
        result = applier.submit(job, cv="cv", cover_letter="letter")
    assert result.success is False
    assert result.error is not None


@respx.mock
def test_direct_post_lever():
    applier = make_applier()
    job = Job(url="https://jobs.lever.co/cursor/xyz456",
              source="lever", company="cursor", title="Backend Eng")
    respx.post("https://api.lever.co/v0/postings/cursor/xyz456/apply").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    result = applier.submit(job, cv="cv", cover_letter="letter")
    assert result.success is True
    assert result.method == "lever_direct"
