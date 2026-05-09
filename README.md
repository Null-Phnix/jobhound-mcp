# JobHound

**MCP server that lets Claude Code scan, score, and apply to jobs autonomously.**

JobHound connects directly to Ashby, Greenhouse, and Lever job board APIs — no browser required for discovery. It scores every listing with a keyword heuristic, queues high-scoring roles, and uses Claude Code as the tailor to write per-role CVs and cover letters.

Includes a **TUI dashboard** for tracking your pipeline in real time.

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
