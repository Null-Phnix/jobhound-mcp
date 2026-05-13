# JobHound 🜏

**MCP server that lets Claude Code scan, score, and apply to jobs autonomously.**

JobHound connects directly to Ashby, Greenhouse, and Lever job board APIs — no browser required for discovery. It scores every listing with a keyword heuristic, queues high-scoring roles, and uses Claude Code as the tailor to write per-role CVs and cover letters.

Includes a **TUI dashboard** for tracking your pipeline in real time.

---

## Table of Contents

- [Why I Built This](#why-i-built-this)
- [What It Does](#what-it-does)
- [Current Pain Points](#current-pain-points)
- [End Goals](#end-goals--where-this-is-headed)
- [Install](#install)
- [Connect to Claude Code](#connect-to-claude-code)
- [MCP Tools](#mcp-tools)
- [Workflow](#workflow)
- [TUI Dashboard](#tui-dashboard)
- [Config](#config)
- [Stack](#stack)
- [License](#license)

---

## Why I Built This

Job searching is miserable. LinkedIn Easy Apply is a black hole — you click apply, it goes nowhere, you never hear back. Premium job alerts cost money and send you garbage. Manually browsing 5 job boards daily is a part-time job in itself.

The APIs are free. Ashby, Greenhouse, Lever — they all have public APIs that list every open role. Why am I manually scrolling?

JobHound exists because my agent should handle job discovery, not me. It scans APIs, scores listings against my skills and preferences, queues the good ones, and hands the tailoring work to Claude Code. I review the generated CV and cover letter, say yes or no, and it submits.

The TUI exists because I want to see my pipeline at a glance — 47 tracked, 3 queued, 12 applied, 2 interviewing — without opening a browser tab.

---

## What It Does

| Feature | What It Does |
|---------|-------------|
| **Scan** | Fetches from Ashby, Greenhouse, Lever, RemoteOK, HN Hiring, Wellfound |
| **Score** | Keyword heuristic matches job description against your skills and preferences |
| **Queue** | High-scoring roles enter a queue for review |
| **Tailor** | Exposes job + your resume to Claude Code for per-role CV and cover letter generation |
| **Apply** | Submits tailored applications via API where supported |
| **Track** | SQLite-backed pipeline tracking with status (new → queued → applied → interviewing → rejected) |
| **Dashboard** | Real-time TUI with live updates every 30 seconds |
| **Daemon** | Background scan loop runs on a schedule |

---

## Current Pain Points

These are the battles I'm actively fighting:

1. **Keyword scoring is crude** — It's a heuristic: count keyword matches between job description and your config. It doesn't understand that "React" and "frontend" are related, or that "5 years experience" in a job description is flexible. A real scoring model would learn from what you actually applied to and got interviews for.

2. **Not every board has an API** — RemoteOK and HN Hiring require scraping. Scraping breaks when they change their HTML. The browser automation layer (`playwright-stealth`) is overkill for simple HTML scraping but necessary because some sites block basic requests.

3. **Auto-apply is limited** — Ashby and some Greenhouse instances support direct API application. Most don't. For those, JobHound generates the tailored docs and you apply manually. The "autonomous" part stops at "here's your CV and cover letter, go submit it."

4. **The TUI is Textual-dependent** — Textual is great but heavy. On a slow terminal or over SSH it can lag. The dashboard is pretty but not essential — the core value is the MCP server and scan queue.

5. **Config management is manual** — `config.yaml` needs your skills, preferences, API keys for each source. Updating it is editing YAML. I want the agent to infer my skills from my GitHub repos and update the config automatically.

6. **No integration with Grayson** — Grayson is my outreach automation tool (cold emails, networking). JobHound finds the jobs, Grayson finds the people. They don't talk to each other. A warm referral beats a cold application.

---

## End Goals — Where This Is Headed

### Short Term (now → 3 months)
- **Better scoring** — move from keyword heuristic to embedding-based semantic similarity
- **Auto-config from GitHub** — read my repos, infer my stack, auto-populate config.yaml
- **Per-source rate limit handling** — respect Ashby/Greenhouse rate limits, back off gracefully

### Medium Term (3–6 months)
- **Grayson integration** — for every queued job, Grayson finds a mutual connection or relevant person to reach out to
- **Unified agent pipeline** — Blackreach researches the company, Huginn scrapes their blog/docs, JobHound scores the role, Grayson finds the contact, all in one workflow
- **Auto-apply expansion** — support more application flows (Lever API, custom forms)

### Long Term (6–12 months)
- **Fully autonomous job search** — "Find me senior backend roles at AI startups in Toronto, apply to the top 10, network with hiring managers, track everything"
- **Interview prep integration** — after an application, auto-research the company, generate likely interview questions, prepare answers
- **Salary negotiation assistant** — track market data, suggest negotiation strategies based on role/company/location

---

## Install

```bash
git clone https://github.com/Null-Phnix/jobhound
cd jobhound
pip install -e .
cp config.example.yaml config.yaml  # fill in your details
```

---

## Connect to Claude Code

Add to your `~/.claude/settings.json` (or `.claude/settings.json` in the project):

```json
{
  "mcpServers": {
    "jobhound": {
      "type": "stdio",
      "command": "jobhound-server"
    }
  }
}
```

---

## MCP Tools

| Tool | Description |
|------|-------------|
| `jobhound_scan()` | Fetch all sources, score jobs, queue high-scoring ones |
| `jobhound_list(status)` | List jobs by status (queued, applied, failed, etc.) |
| `jobhound_get(id)` | Full job details + generated docs |
| `jobhound_get_for_tailoring(id)` | Job description + your resume for Claude to tailor |
| `jobhound_apply_tailored(id, cv, letter)` | Submit a tailored application |
| `jobhound_update(id, status)` | Manually set status (interviewing, rejected) |
| `jobhound_pause()` | Pause the daemon scan loop |
| `jobhound_resume()` | Resume the daemon scan loop |

## Workflow

```
jobhound_scan()                          # find what's new
jobhound_list("queued")                  # see what's waiting
jobhound_get_for_tailoring(42)           # get job + resume
[Claude writes tailored CV + letter]
jobhound_apply_tailored(42, cv, letter)  # submit + record
```

---

## TUI Dashboard

```bash
jobhound-tui
```

Live two-pane view of your entire job pipeline. Polls SQLite every 30 seconds, shows status by color.

```
┌─ JobHound ──────────────────────────────────────────────────────┐
│ [LIVE] 47 tracked · 3 queued · 12 applied · 2 interviewing      │
├──────────────────────────┬──────────────────────────────────────┤
│ ▶ Bree          applied  │  Bree — Software Engineer, Backend    │
│   Modal         applied  │  Applied: 2026-03-11 via Ashby        │
│   LangChain     applied  │  Score: 87/100                        │
│   Cohere        queued   │  Method: direct POST                  │
│   Anthropic     new      │                                       │
│   Cursor        failed   │  Cover Letter:                        │
│                          │  > The line that stood out in your... │
├──────────────────────────┴──────────────────────────────────────┤
│ [s]can  [p]ause  [f]ilter  [o]pen URL  [x]export  [q]uit        │
└─────────────────────────────────────────────────────────────────┘
```

### TUI Keybinds

| Key | Action |
|-----|--------|
| `s` | Scan sources (fetch + score, no auto-apply) |
| `p` | Pause / resume daemon |
| `f` | Cycle filter: all → new → queued → applied → failed → interviewing |
| `o` | Open highlighted job URL in browser |
| `x` | Export current view to `~/jobhound_export_YYYYMMDD.md` + `.csv` |
| `q` | Quit |

---

## Config

See `config.example.yaml`. Supports Ashby, Greenhouse, Lever, RemoteOK, HN Hiring, and Wellfound.

---

## Stack

- Python 3.11+
- `fastmcp` — MCP server
- `httpx` — source API calls
- `sqlite3` — job tracking
- `textual` — TUI dashboard
- `rich` — terminal output

---

## License

MIT
