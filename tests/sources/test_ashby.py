import respx
import httpx
from jobhound.sources.ashby import AshbySource

MOCK_RESPONSE = {
    "jobs": [
        {
            "id": "abc123",
            "title": "Member of Technical Staff, Python SDK",
            "team": {"name": "Engineering"},
            "location": {"name": "New York"},
            "isRemote": True,
            "jobUrl": "https://jobs.ashbyhq.com/modal/abc123",
            "descriptionHtml": "<p>Build the Python SDK for Modal.</p>",
        }
    ]
}


@respx.mock
def test_ashby_fetch_returns_jobs():
    respx.get("https://api.ashbyhq.com/posting-api/job-board/modal").mock(
        return_value=httpx.Response(200, json=MOCK_RESPONSE)
    )
    source = AshbySource(["modal"])
    jobs = source.fetch()
    assert len(jobs) == 1
    assert jobs[0].company == "modal"
    assert jobs[0].title == "Member of Technical Staff, Python SDK"
    assert jobs[0].remote is True
    assert jobs[0].source == "ashby"
    assert "modal" in jobs[0].url


@respx.mock
def test_ashby_multiple_slugs():
    for slug in ["modal", "langchain"]:
        respx.get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}").mock(
            return_value=httpx.Response(200, json=MOCK_RESPONSE)
        )
    source = AshbySource(["modal", "langchain"])
    jobs = source.fetch()
    assert len(jobs) == 2


@respx.mock
def test_ashby_handles_404():
    respx.get("https://api.ashbyhq.com/posting-api/job-board/badslug").mock(
        return_value=httpx.Response(404)
    )
    source = AshbySource(["badslug"])
    jobs = source.fetch()
    assert jobs == []


@respx.mock
def test_ashby_strips_html():
    respx.get("https://api.ashbyhq.com/posting-api/job-board/co").mock(
        return_value=httpx.Response(200, json={"jobs": [{
            "title": "Eng",
            "location": {"name": "Remote"},
            "isRemote": True,
            "jobUrl": "https://jobs.ashbyhq.com/co/1",
            "descriptionHtml": "<h2>Role</h2><p>Build <strong>AI</strong> systems.</p>",
        }]})
    )
    jobs = AshbySource(["co"]).fetch()
    assert "<" not in jobs[0].description
