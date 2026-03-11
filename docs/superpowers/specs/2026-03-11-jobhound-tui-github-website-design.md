# JobHound — TUI Fixes, GitHub Publishing, Website Update
**Date:** 2026-03-11
**Status:** Approved

---

## Overview

Three discrete deliverables:
1. Fix and extend the existing Textual TUI (`tui/app.py`)
2. Publish two public GitHub repos under `Null-Phnix`: `jobhound-mcp` and `jobhound-tui`
3. Update `phnix.dev` with two project cards, two detail pages, and one blog post

---

## 1. TUI Fixes (`tui/app.py`)

### Changes

| Item | Current | Fix |
|------|---------|-----|
| `action_scan` | calls full `run_cycle` (fetch+score+tailor+apply) | call fetch+score only, insert `new`/`queued` rows, no Claude API call |
| `STATUS_COLORS["queued"]` | missing | add `"queued": "blue"` |
| Stats bar | no queued count | add `[blue]{queued} queued[/blue]` |
| Keybind `o` | missing | open highlighted job URL in browser via `webbrowser.open()` |
| Keybind `x` | missing | export `self._jobs` (current filtered view, respects active filter and 200-row cap) to `~/jobhound_export_YYYYMMDD.md` and `.csv` |
| Config path | hardcoded `Path("config.yaml")` | resolve relative to the JobHound project root, not cwd |
| Filter cycle | missing `queued` | add `"queued"` to the `filters` list in `action_filter_cycle` |

### Scan-only logic

```python
def action_scan(self):
    def _run():
        from jobhound.daemon import _build_sources
        from jobhound.scorer import Scorer
        from jobhound.models import Status
        cfg = self._cfg
        scorer = Scorer(cfg.skills_path)
        for source in _build_sources(cfg):
            for job in source.fetch():
                job.score = scorer.score(job)
                if job.score >= cfg.score_threshold and not self.tracker.seen(job.url):
                    job.status = Status.QUEUED
                    self.tracker.record(job)
        self.call_from_thread(self.refresh_jobs)
    threading.Thread(target=_run, daemon=True).start()
```

### Export format

**Markdown** (`~/jobhound_export_YYYYMMDD.md`):
```markdown
# JobHound Export — 2026-03-11

| Company | Title | Status | Score | Applied |
|---------|-------|--------|-------|---------|
| Modal   | Backend Engineer | applied | 87 | 2026-03-11 |
```

**CSV** (`~/jobhound_export_YYYYMMDD.csv`): same columns, standard CSV.

---

## 2. GitHub Publishing

### Two repos, same codebase

The full JobHound codebase lives in one directory. Both repos are initialized from that same source. Each gets a different README and description.

| Repo | URL | Description | Focus |
|------|-----|-------------|-------|
| `jobhound-mcp` | github.com/Null-Phnix/jobhound-mcp | MCP server for Claude Code | FastMCP tools, Claude Code integration |
| `jobhound-tui` | github.com/Null-Phnix/jobhound-tui | Terminal UI for job tracking | Textual TUI, live status |

### Git config

```
author.name  = Null-Phnix
author.email = contact@phnix.dev
```

Applied via `git -c user.name=... -c user.email=...` per commit — no global config change.

### Secrets handling

`config.yaml` contains personal data (name, email, phone, server addresses) and must NOT be committed. Both repos include:
- `.gitignore` entry for `config.yaml` and `*.db`
- `config.example.yaml` with all keys present but placeholder values (`your-name`, `your-email`, etc.)

### What goes in each repo

Both repos contain the full codebase. README differs:

- `jobhound-mcp` README: leads with MCP server, lists the 8 tools, shows Claude Code config snippet
- `jobhound-tui` README: leads with TUI, shows screenshot (ASCII), keybind table, install instructions

---

## 3. phnix.dev Updates

### Homepage cards (index.html)

Two new cards added to the existing projects grid:

**JobHound MCP**
- Tagline: "MCP server that lets Claude Code scan, score, and apply to jobs autonomously"
- Tag: `mcp` `python` `fastmcp`
- Link: `/projects/jobhound-mcp.html`

**JobHound TUI**
- Tagline: "Terminal dashboard for tracking 47 target companies in real time"
- Tag: `tui` `python` `textual`
- Link: `/projects/jobhound-tui.html`

### Detail pages

**`/projects/jobhound-mcp.html`**
- What it does, how to connect to Claude Code, the 8 tools with descriptions
- Tech stack, GitHub link

**`/projects/jobhound-tui.html`**
- What it does, ASCII screenshot, keybind reference
- Tech stack, GitHub link

### Blog post (`/posts/why-i-built-jobhound.html`)

Title: *"Why I built my own job application agent (and why every existing tool failed me)"*

Structure:
1. **The problem**: 47 target companies, all on Ashby/Greenhouse/Lever — no mainstream tool handles these
2. **What I tried and why it failed**:
   - LazyApply (1.9★ on Chrome Store): autofills LinkedIn Easy Apply only, no Ashby support, spam-flags resumes
   - Simplify: autofill overlay only, no autonomous submission, requires human click per application
   - Huntr / Teal: trackers, not applicators — no submission capability at all
   - Loopcv / Sonara: limited to Indeed/LinkedIn job boards, no niche ATS support
3. **Why these tools specifically don't work for me**: Canadian applicant targeting US AI companies → Ashby-heavy → none of the mainstream tools support Ashby form submission; I'm not applying to 500 jobs on Indeed, I'm applying to 47 specific companies
4. **What JobHound does instead**: fetch from source APIs directly, score with keyword heuristics, tailor with Claude, submit via Playwright smart form reader
5. **Results**: applied to 47 target companies in one session, 8 confirmed + more pending

Tone: direct, first-person, technical. No fluff. Links to both GitHub repos.

---

## Execution Order

1. Fix `tui/app.py`
2. Write READMEs for both repos
3. Create GitHub repos + push (git author = Null-Phnix)
4. Update `phnix.dev` (cards, detail pages, blog post)
