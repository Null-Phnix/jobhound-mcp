# JobHound — Design Spec
**Date:** 2026-03-11
**Status:** Approved

---

## Overview

JobHound is an autonomous job application agent. Set it up once with your resume and preferences, and it handles the entire pipeline: finding jobs, scoring them, tailoring your CV and cover letter per role via Claude, and submitting applications automatically. A Textual TUI shows live status. An MCP server lets Claude Code query and control it as tool calls.

---

## Architecture

```
/mnt/GameDrive/AI_Projects/JobHound/
├── jobhound/
│   ├── sources/
│   │   ├── base.py         # BaseSource ABC: fetch() -> list[Job]
│   │   ├── ashby.py        # Ashby API
│   │   ├── greenhouse.py   # Greenhouse API
│   │   ├── lever.py        # Lever API
│   │   ├── remoteok.py     # RemoteOK open JSON API
│   │   ├── hn_hiring.py    # HN Who's Hiring via Algolia
│   │   └── wellfound.py    # Wellfound via Blackreach HTTP server
│   ├── scorer.py           # Keyword + heuristic scoring, no LLM
│   ├── tailor.py           # Claude generates tailored CV + cover letter
│   ├── apply.py            # Submit via LinkedIn MCP, Ashby/GH/Lever POST, or Blackreach
│   ├── tracker.py          # SQLite interface — all state
│   ├── daemon.py           # Scheduler loop, orchestrates pipeline
│   └── mcp_server.py       # FastMCP server exposing 6 tools
├── tui/
│   └── app.py              # Textual TUI — live read from SQLite
├── config.yaml             # Companies, score thresholds, schedule interval
├── profile/
│   ├── resume.md           # Your resume (symlink to existing file)
│   └── skills.yaml         # Skill weights for scorer
└── pyproject.toml
```

---

## Data Flow

```
daemon (every 6h, configurable)
  → sources/*.fetch()      → raw Job objects
  → scorer.score()         → filtered (score >= threshold, default 30)
  → tracker.seen(url)?     → dedup, skip already-processed URLs
  → tailor.generate()      → tailored CV + cover letter via Claude API
  → apply.submit()         → LinkedIn MCP / direct POST / Blackreach fallback
  → tracker.record()       → write to SQLite with full status
```

---

## SQLite Schema

Single `jobs` table:

```sql
CREATE TABLE jobs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL,          -- ashby, greenhouse, remoteok, etc.
    company     TEXT NOT NULL,
    title       TEXT NOT NULL,
    url         TEXT UNIQUE NOT NULL,   -- dedup key
    location    TEXT,
    remote      BOOLEAN,
    score       INTEGER,
    status      TEXT DEFAULT 'new',     -- new/queued/applied/failed/interviewing/rejected
    applied_at  TIMESTAMP,
    method      TEXT,                   -- linkedin_mcp / direct_post / blackreach
    cover_letter TEXT,
    cv_used     TEXT,                   -- tailored CV text
    notes       TEXT,
    raw_json    TEXT                    -- full source payload
);
```

---

## Sources

Each source implements `BaseSource`:

```python
class BaseSource(ABC):
    @abstractmethod
    def fetch(self) -> list[Job]:
        ...
```

| Source | Method | Notes |
|--------|--------|-------|
| Ashby | `httpx` GET | `api.ashbyhq.com/posting-api/job-board/{slug}` — configure slugs in config.yaml |
| Greenhouse | `httpx` GET | `boards-api.greenhouse.io/v1/boards/{slug}/jobs` |
| Lever | `httpx` GET | `api.lever.co/v0/postings/{slug}` |
| RemoteOK | `httpx` GET | `remoteok.com/api` — full feed, scorer filters |
| HN Hiring | `httpx` GET | Algolia API, finds current month's thread, parses comments |
| Wellfound | Blackreach | JS-rendered, needs browser agent |

---

## Scoring

Pure Python, no LLM, runs on every job before Claude is called.

```yaml
# skills.yaml
positive:
  title_keywords:     [engineer, developer, backend, infrastructure, platform]  # +20 each
  body_keywords:      [Python, agents, RAG, LLM, MCP, autonomous, Playwright]   # +15 each
  remote: 20
  canada_or_global: 10
  salary_gte_100k: 5

negative:
  required_keywords:  [TypeScript-only, frontend-only, Java, ".NET", PHP]       # -30 each
  dealbreakers:       [casino, gambling, iGaming, "no experience required"]      # -50 each
  internship:         -99

threshold: 30
sonnet_threshold: 70   # use claude-sonnet above this, haiku below
```

---

## Tailor

One Claude API call per job. Prompt includes:
- Full job description
- `resume.md` contents
- `skills.yaml` for emphasis hints

Outputs:
1. Tailored CV (same markdown format, adjusted skill emphasis and project ordering)
2. Cover letter in user's voice (direct, no em dashes, no corporate speak, no fluff)

Model selection:
- Score < 70: `claude-haiku-4-5` (~$0.002/call)
- Score >= 70: `claude-sonnet-4-6` (~$0.015/call)

Both outputs saved to SQLite.

---

## Apply

Three strategies tried in order:

1. **LinkedIn MCP** — if job has a LinkedIn apply URL, uses existing LinkedIn MCP server (localhost:7433)
2. **Direct POST** — Ashby, Greenhouse, Lever all have public application endpoints. POST resume PDF + cover letter text directly. No browser.
3. **Blackreach fallback** — for everything else, Blackreach handles form submission via autonomous browser agent (localhost:7432)

Each attempt records: `status`, `applied_at`, `method`, HTTP response code. Failures mark `status=failed` and log the error — never blocks the queue.

---

## Daemon

```python
# daemon.py — simplified
while True:
    new_jobs = fetch_all_sources()         # all sources in parallel
    for job in new_jobs:
        job.score = scorer.score(job)
        if job.score < config.threshold:
            continue
        if tracker.seen(job.url):
            continue
        cv, letter = tailor.generate(job)
        result = apply.submit(job, cv, letter)
        tracker.record(job, result)
    sleep(config.interval_seconds)         # default: 6 hours
```

Runs as a background process. Start with `jobhound daemon` or `jobhound-daemon` entrypoint.

---

## MCP Server

6 tools exposed via FastMCP on localhost:7434:

```python
jobhound_status()              # summary stats: applied today, pending, failed
jobhound_list(status: str)     # list jobs by status
jobhound_scan()                # trigger immediate scan
jobhound_get(job_id: int)      # full job details + generated docs
jobhound_update(job_id, status) # manually set status (interviewing, rejected)
jobhound_pause()               # pause daemon
jobhound_resume()              # resume daemon
```

---

## TUI

Built with [Textual](https://textual.textualize.io/). Two-pane layout, live-updating from SQLite (polls every 30s).

```
┌─ JobHound ──────────────────────────────────────────────────────┐
│ [LIVE] 47 tracked · 12 applied · 2 interviewing · 3 failed      │
├──────────────────────────┬──────────────────────────────────────┤
│ ▶ Bree          applied  │  Bree — Software Engineer, Backend    │
│   Modal         applied  │  Applied: 2026-03-11 via Ashby        │
│   LangChain     applied  │  Score: 87/100                        │
│   Cohere        applied  │  Method: direct POST                  │
│   Oscilar       applied  │                                       │
│   Anthropic     new      │  Cover Letter:                        │
│   OpenAI        new      │  > The line that stood out in your    │
│   Cursor        failed   │    job description was this...        │
├──────────────────────────┴──────────────────────────────────────┤
│ [s]can  [p]ause  [f]ilter  [enter] details  [q]uit              │
└─────────────────────────────────────────────────────────────────┘
```

Keybinds: `s` trigger scan, `p` pause/resume, `f` filter by status, `enter` expand job, `q` quit.

---

## Config

```yaml
# config.yaml
profile:
  resume: ./profile/resume.md
  skills: ./profile/skills.yaml

daemon:
  interval_hours: 6
  db_path: ./jobhound.db

sources:
  ashby:
    - modal
    - langchain
    - cohere
    - e2b
    - replit
    - anthropic
  greenhouse:
    - openai
  remoteok: true
  hn_hiring: true
  wellfound:
    query: "AI engineer autonomous agents Python"
    remote_only: true

apply:
  linkedin_server: http://localhost:7433
  blackreach_server: http://localhost:7432

mcp:
  port: 7434
```

---

## Stack

- Python 3.11+
- `httpx` — all API calls
- `anthropic` — Claude API for tailoring
- `textual` — TUI
- `fastmcp` — MCP server
- `sqlite3` — stdlib, no ORM
- Blackreach (existing) — JS-rendered job boards
- LinkedIn MCP (existing) — LinkedIn applications

---

## Out of Scope (v1)

- Email parsing for interview invites
- Calendar integration
- Multi-user support
- Web UI
