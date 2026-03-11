import pytest
import yaml
from jobhound.scorer import Scorer
from jobhound.models import Job


@pytest.fixture
def scorer(tmp_path):
    skills = {
        "positive": {
            "title_keywords": ["engineer", "developer"],
            "body_keywords": ["Python", "agents", "LLM"],
            "remote": 20,
            "canada_or_global": 10,
            "salary_gte_100k": 5,
        },
        "negative": {
            "required_keywords": ["Java", ".NET"],
            "dealbreakers": ["casino", "gambling"],
            "internship": -99,
        },
        "weights": {
            "title_keyword": 20,
            "body_keyword": 15,
            "negative_keyword": -30,
            "dealbreaker": -50,
        }
    }
    f = tmp_path / "skills.yaml"
    f.write_text(yaml.dump(skills))
    return Scorer(f)


def test_score_strong_match(scorer):
    job = Job(url="x", source="ashby", company="Modal", title="Python Engineer",
              description="Build LLM agents in Python.", remote=True)
    score = scorer.score(job)
    assert score >= 50  # title(20) + body LLM(15) + body agents(15) + body Python(15) + remote(20)


def test_score_java_penalty(scorer):
    job = Job(url="x", source="ashby", company="Corp", title="Java Engineer",
              description="Must know Java and .NET.")
    score = scorer.score(job)
    assert score < 0


def test_score_dealbreaker(scorer):
    # Use a title that doesn't match any positive keywords to isolate dealbreaker logic
    job = Job(url="x", source="ashby", company="Casino", title="Slot Machine Designer",
              description="Build casino games.")
    score = scorer.score(job)
    assert score <= -50


def test_score_internship(scorer):
    # Use a title that doesn't match positive keywords to isolate internship penalty
    job = Job(url="x", source="ashby", company="Co", title="Marketing Intern",
              description="Summer internship program.")
    score = scorer.score(job)
    assert score <= -99


def test_score_remote_bonus(scorer):
    j_remote = Job(url="x", source="s", company="C", title="Engineer", remote=True)
    j_onsite = Job(url="y", source="s", company="C", title="Engineer", remote=False,
                   location="Chicago, IL")
    assert scorer.score(j_remote) > scorer.score(j_onsite)


def test_score_no_body_keywords(scorer):
    job = Job(url="x", source="s", company="C", title="Engineer", description="")
    score = scorer.score(job)
    # Should still get title keyword bonus
    assert score >= 20
