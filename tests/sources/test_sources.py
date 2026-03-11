import respx
import httpx
from jobhound.sources.greenhouse import GreenhouseSource
from jobhound.sources.lever import LeverSource
from jobhound.sources.remoteok import RemoteOKSource
from jobhound.sources.hn_hiring import HNHiringSource


# --- Greenhouse ---
@respx.mock
def test_greenhouse_fetch():
    respx.get("https://boards-api.greenhouse.io/v1/boards/anthropic/jobs").mock(
        return_value=httpx.Response(200, json={"jobs": [
            {"title": "AI Engineer", "location": {"name": "Remote"},
             "absolute_url": "https://boards.greenhouse.io/anthropic/jobs/1",
             "content": "Build AI systems."}
        ]})
    )
    jobs = GreenhouseSource(["anthropic"]).fetch()
    assert len(jobs) == 1
    assert jobs[0].company == "anthropic"
    assert jobs[0].source == "greenhouse"
    assert jobs[0].remote is True


@respx.mock
def test_greenhouse_handles_404():
    respx.get("https://boards-api.greenhouse.io/v1/boards/badco/jobs").mock(
        return_value=httpx.Response(404)
    )
    jobs = GreenhouseSource(["badco"]).fetch()
    assert jobs == []


# --- Lever ---
@respx.mock
def test_lever_fetch():
    respx.get("https://api.lever.co/v0/postings/cursor?mode=json").mock(
        return_value=httpx.Response(200, json=[
            {"text": "Backend Engineer", "hostedUrl": "https://jobs.lever.co/cursor/1",
             "categories": {"location": "Remote"},
             "descriptionPlain": "Build cursor backend."}
        ])
    )
    jobs = LeverSource(["cursor"]).fetch()
    assert len(jobs) == 1
    assert jobs[0].source == "lever"
    assert jobs[0].remote is True


# --- RemoteOK ---
@respx.mock
def test_remoteok_fetch():
    respx.get("https://remoteok.com/api").mock(
        return_value=httpx.Response(200, json=[
            {"legal": "RemoteOK API"},  # first item is always metadata
            {"position": "AI Engineer", "company": "Acme",
             "url": "https://remoteok.com/jobs/1",
             "description": "Build AI stuff.", "tags": ["python", "ai"]}
        ])
    )
    jobs = RemoteOKSource().fetch()
    assert len(jobs) == 1
    assert jobs[0].remote is True
    assert jobs[0].source == "remoteok"
    assert jobs[0].company == "Acme"


@respx.mock
def test_remoteok_skips_metadata():
    respx.get("https://remoteok.com/api").mock(
        return_value=httpx.Response(200, json=[
            {"legal": "metadata"},
        ])
    )
    jobs = RemoteOKSource().fetch()
    assert jobs == []


# --- HN Hiring ---
@respx.mock
def test_hn_hiring_fetch():
    respx.get(
        "https://hn.algolia.com/api/v1/search?query=Ask+HN+Who+is+Hiring&tags=story&hitsPerPage=1"
    ).mock(return_value=httpx.Response(200, json={
        "hits": [{"objectID": "12345", "title": "Ask HN: Who is Hiring? (March 2026)"}]
    }))
    respx.get("https://hacker-news.firebaseio.com/v0/item/12345.json").mock(
        return_value=httpx.Response(200, json={"kids": [111, 222]})
    )
    respx.get("https://hacker-news.firebaseio.com/v0/item/111.json").mock(
        return_value=httpx.Response(200, json={
            "text": "Acme | AI Engineer | Remote | $150k | https://acme.com/jobs"
        })
    )
    respx.get("https://hacker-news.firebaseio.com/v0/item/222.json").mock(
        return_value=httpx.Response(200, json={
            "text": "BigCorp | Marketing | NYC | $80k"
        })
    )
    jobs = HNHiringSource().fetch()
    assert len(jobs) >= 1
    assert any("acme" in j.company.lower() or "AI Engineer" in j.title for j in jobs)


@respx.mock
def test_hn_hiring_no_hits():
    respx.get(
        "https://hn.algolia.com/api/v1/search?query=Ask+HN+Who+is+Hiring&tags=story&hitsPerPage=1"
    ).mock(return_value=httpx.Response(200, json={"hits": []}))
    jobs = HNHiringSource().fetch()
    assert jobs == []
