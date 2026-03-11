from pathlib import Path
from jobhound.config import load_config, Config


def test_load_config(tmp_path):
    cfg_text = """
profile:
  resume: ./profile/resume.md
  skills: ./profile/skills.yaml
daemon:
  interval_hours: 6
  db_path: ./jobhound.db
score:
  threshold: 30
  sonnet_threshold: 70
sources:
  ashby: [modal, langchain]
  remoteok: true
  hn_hiring: false
  wellfound:
    query: "AI engineer"
    remote_only: true
apply:
  linkedin_server: "http://localhost:7433"
  blackreach_server: "http://localhost:7432"
mcp:
  port: 7434
"""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(cfg_text)
    cfg = load_config(cfg_file)
    assert isinstance(cfg, Config)
    assert cfg.interval_hours == 6
    assert cfg.score_threshold == 30
    assert cfg.ashby_slugs == ["modal", "langchain"]
    assert cfg.remoteok is True
    assert cfg.hn_hiring is False
    assert cfg.mcp_port == 7434
    assert cfg.wellfound_query == "AI engineer"
    assert cfg.linkedin_server == "http://localhost:7433"


def test_empty_slugs_defaults_to_list(tmp_path):
    cfg_text = """
profile:
  resume: ./profile/resume.md
  skills: ./profile/skills.yaml
daemon:
  interval_hours: 6
  db_path: ./jobhound.db
score:
  threshold: 30
  sonnet_threshold: 70
sources:
  ashby: []
  greenhouse: []
  lever: []
  remoteok: false
  hn_hiring: false
apply:
  linkedin_server: "http://localhost:7433"
  blackreach_server: "http://localhost:7432"
mcp:
  port: 7434
"""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(cfg_text)
    cfg = load_config(cfg_file)
    assert cfg.ashby_slugs == []
    assert cfg.greenhouse_slugs == []
    assert cfg.lever_slugs == []
