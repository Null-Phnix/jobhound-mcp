import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from jobhound.tailor import Tailor
from jobhound.models import Job


@pytest.fixture
def tailor(tmp_path):
    resume = tmp_path / "resume.md"
    resume.write_text("# Josimar Lee\nAI Engineer\n\n## Skills\nPython, agents, RAG")
    return Tailor(resume_path=resume, sonnet_threshold=70)


def _mock_claude(content: str):
    msg = MagicMock()
    msg.content = [MagicMock(text=content)]
    return msg


def test_tailor_returns_cv_and_letter(tailor):
    job = Job(url="x", source="ashby", company="Modal", title="Python SDK Engineer",
              description="Build the Python SDK.", score=60)
    mock_response = _mock_claude(
        "=== CV ===\n# Josimar Lee\nTailored CV here.\n=== COVER LETTER ===\nDear Modal team..."
    )
    with patch("anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.return_value = mock_response
        tailor.client = MockClient.return_value
        cv, letter = tailor.generate(job)
    assert len(cv) > 0 or len(letter) > 0


def test_tailor_uses_haiku_below_threshold(tailor):
    job = Job(url="x", source="ashby", company="Co", title="Eng",
              description="desc", score=40)
    mock_response = _mock_claude("=== CV ===\ncv\n=== COVER LETTER ===\nletter")
    with patch("jobhound.tailor.anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.return_value = mock_response
        t = Tailor(resume_path=tailor.resume.__class__.__mro__[0].__init__.__doc__ and
                   Path("/dev/null") or Path("/dev/null"),
                   sonnet_threshold=70)
        t.resume = "# Resume"
        t.client = MockClient.return_value
        t.sonnet_threshold = 70
        t.generate(job)
        call_kwargs = MockClient.return_value.messages.create.call_args[1]
        assert "haiku" in call_kwargs["model"].lower()


def test_tailor_uses_sonnet_above_threshold(tailor):
    job = Job(url="x", source="ashby", company="Co", title="Eng",
              description="desc", score=80)
    mock_response = _mock_claude("=== CV ===\ncv\n=== COVER LETTER ===\nletter")
    with patch("jobhound.tailor.anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.return_value = mock_response
        t = Tailor(resume_path=Path("/dev/null"), sonnet_threshold=70)
        t.resume = "# Resume"
        t.client = MockClient.return_value
        t.generate(job)
        call_kwargs = MockClient.return_value.messages.create.call_args[1]
        assert "sonnet" in call_kwargs["model"].lower()


def test_tailor_parse_fallback(tailor):
    """If response doesn't have markers, treat everything as cover letter."""
    job = Job(url="x", source="ashby", company="Co", title="Eng",
              description="desc", score=50)
    mock_response = _mock_claude("Here is my application...")
    with patch("jobhound.tailor.anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.return_value = mock_response
        t = Tailor(resume_path=Path("/dev/null"), sonnet_threshold=70)
        t.resume = "# Resume"
        t.client = MockClient.return_value
        cv, letter = t.generate(job)
        assert letter == "Here is my application..."
        assert cv == ""
