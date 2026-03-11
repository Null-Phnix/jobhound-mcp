# JobHound TUI, GitHub Publishing, and phnix.dev Update — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix and extend the JobHound TUI, publish two public GitHub repos as Null-Phnix, and update phnix.dev with project cards, detail pages, and a blog post.

**Architecture:** Three independent deliverables executed in order: (1) patch `tui/app.py` in-place with targeted edits, (2) add secrets handling then push the existing codebase as two separate GitHub repos, (3) add HTML content to the existing static phnix.dev site.

**Tech Stack:** Python / Textual (TUI), GitHub CLI `gh` (repo creation), plain HTML/CSS matching existing phnix.dev patterns.

---

## Chunk 1: TUI Fixes

### Task 1: Add `queued` color, stats, and filter

**Files:**
- Modify: `tui/app.py`

The `STATUS_COLORS` dict is missing `"queued"`. The stats bar has no queued count. The filter cycle list is missing `"queued"`.

- [ ] **Step 1: Edit STATUS_COLORS**

In `tui/app.py` line 16–21, change:
```python
STATUS_COLORS = {
    "new": "cyan",
    "applied": "green",
    "failed": "red",
    "interviewing": "yellow",
    "rejected": "dim",
}
```
to:
```python
STATUS_COLORS = {
    "new": "cyan",
    "queued": "blue",
    "applied": "green",
    "failed": "red",
    "interviewing": "yellow",
    "rejected": "dim",
}
```

- [ ] **Step 2: Add queued count to stats bar**

In `refresh_jobs` (lines 84–118), add `queued` to the stats variables and the label:

```python
queued = stats.get("queued", 0)
```

Change the label update to:
```python
self.query_one("#stats", Label).update(
    f"[bold]JobHound[/bold]  {total} tracked · "
    f"[blue]{queued} queued[/blue] · "
    f"[green]{applied} applied[/green] · "
    f"[yellow]{interviewing} interviewing[/yellow] · "
    f"[red]{failed} failed[/red]"
    + (" [red][PAUSED][/red]" if self._paused else " [green][LIVE][/green]")
    + filter_label
)
```

- [ ] **Step 3: Add `queued` to filter cycle**

In `action_filter_cycle` (line 153), change:
```python
filters = [None, "new", "applied", "failed", "interviewing", "rejected"]
```
to:
```python
filters = [None, "new", "queued", "applied", "failed", "interviewing", "rejected"]
```

- [ ] **Step 4: Verify by reading the modified file**

Read `tui/app.py` and confirm:
- `STATUS_COLORS` has `"queued": "blue"`
- stats bar line includes `queued`
- `filters` list includes `"queued"`

---

### Task 2: Fix config path

**Files:**
- Modify: `tui/app.py`

Currently `__init__` hardcodes `Path("config.yaml")` which resolves relative to cwd. It should resolve relative to the JobHound project root (same pattern as `mcp_server.py`).

- [ ] **Step 1: Add project root constant at top of file**

After the existing imports, add:
```python
import os
_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
_CONFIG_PATH = Path(os.environ.get("JOBHOUND_ROOT", str(_PROJECT_ROOT))) / "config.yaml"
```

- [ ] **Step 2: Update `__init__` to use the constant**

Change:
```python
cfg = load_config(Path("config.yaml"))
```
to:
```python
cfg = load_config(_CONFIG_PATH)
```

---

### Task 3: Replace `action_scan` with fetch+score only

**Files:**
- Modify: `tui/app.py`

Current `action_scan` calls the full `run_cycle` which invokes Claude API for tailoring and submits applications. The TUI scan should only fetch and score — queue jobs for the human to review, not auto-apply.

- [ ] **Step 1: Replace `action_scan` entirely**

Remove lines 125–144 (current `action_scan`) and replace with:

```python
def action_scan(self):
    def _run():
        from jobhound.daemon import _build_sources
        from jobhound.scorer import Scorer
        from jobhound.models import Status
        cfg = self._cfg
        scorer = Scorer(cfg.skills_path)
        for source in _build_sources(cfg):
            try:
                for job in source.fetch():
                    if self.tracker.seen(job.url):
                        continue
                    job.score = scorer.score(job)
                    if job.score >= cfg.score_threshold:
                        job.status = Status.QUEUED
                    else:
                        job.status = Status.NEW
                    self.tracker.record(job)
            except Exception as e:
                pass  # don't crash TUI on source error
        self.call_from_thread(self.refresh_jobs)
    threading.Thread(target=_run, daemon=True).start()
```

---

### Task 4: Add `o` keybind — open URL in browser

**Files:**
- Modify: `tui/app.py`

- [ ] **Step 1: Add `webbrowser` import**

At the top of `tui/app.py` with the other stdlib imports, add:
```python
import webbrowser
```

- [ ] **Step 2: Add binding**

In `BINDINGS`, add:
```python
Binding("o", "open_url", "Open URL"),
```

- [ ] **Step 3: Add action method**

After `action_filter_cycle`, add:
```python
def action_open_url(self):
    if self._jobs:
        table = self.query_one("#table", DataTable)
        row = table.cursor_row
        if 0 <= row < len(self._jobs):
            webbrowser.open(self._jobs[row].url)
```

---

### Task 5: Add `x` keybind — export to MD and CSV

**Files:**
- Modify: `tui/app.py`

Exports `self._jobs` (current filtered view) as both `.md` and `.csv` to `~/jobhound_export_YYYYMMDD.{md,csv}`.

- [ ] **Step 1: Add `csv` and `datetime` imports**

At the top of `tui/app.py`:
```python
import csv
from datetime import date
```

- [ ] **Step 2: Add binding**

In `BINDINGS`, add:
```python
Binding("x", "export", "Export"),
```

- [ ] **Step 3: Add action method**

```python
def action_export(self):
    if not self._jobs:
        return
    today = date.today().strftime("%Y%m%d")
    base = Path.home() / f"jobhound_export_{today}"

    # Markdown
    lines = [f"# JobHound Export — {date.today()}\n"]
    lines.append("| Company | Title | Status | Score | Applied |")
    lines.append("|---------|-------|--------|-------|---------|")
    for j in self._jobs:
        lines.append(
            f"| {j.company} | {j.title} | {j.status.value} | {j.score} | {j.applied_at or ''} |"
        )
    (base.with_suffix(".md")).write_text("\n".join(lines))

    # CSV
    with open(base.with_suffix(".csv"), "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["company", "title", "status", "score", "applied_at", "url"])
        for j in self._jobs:
            writer.writerow([j.company, j.title, j.status.value, j.score, j.applied_at or "", j.url])

    # Show export confirmation. The 30s auto-refresh may overwrite it early
    # if it fires within 3s — acceptable as a known limitation.
    self.query_one("#stats", Label).update(
        f"[green]Exported {len(self._jobs)} jobs to ~/jobhound_export_{today}.md / .csv[/green]"
    )
    self.set_timer(3, self.refresh_jobs)
```

---

### Task 6: Commit TUI changes

- [ ] **Step 1: Verify the file reads correctly**

Run: `python3 -c "import ast; ast.parse(open('/mnt/GameDrive/AI_Projects/JobHound/tui/app.py').read()); print('OK')" `

Expected: `OK`

- [ ] **Step 2: Commit**

```bash
cd /mnt/GameDrive/AI_Projects/JobHound
git -c user.name="Null-Phnix" -c user.email="contact@phnix.dev" add tui/app.py
git -c user.name="Null-Phnix" -c user.email="contact@phnix.dev" commit -m "feat(tui): queued status, fetch-only scan, export x, open URL o, fix config path"
```

---

## Chunk 2: GitHub Publishing

### Task 7: Secrets handling and config.example.yaml

**Files:**
- Modify: `.gitignore`
- Create: `config.example.yaml`

- [ ] **Step 1: Add `config.yaml` to .gitignore**

The existing `.gitignore` already has `*.db` and `.env`. Add `config.yaml` to it:

```
config.yaml
profile/resume.md
profile/skills.yaml
```

(Resume and skills also contain personal content and should stay local.)

- [ ] **Step 2: Create `config.example.yaml`**

```yaml
# JobHound configuration — copy to config.yaml and fill in your values

profile:
  resume: ./profile/resume.md
  skills: ./profile/skills.yaml
  name: "Your Name"
  email: "you@example.com"
  phone: "+1-555-000-0000"

daemon:
  interval_hours: 6
  db_path: ./jobhound.db

score:
  threshold: 30
  sonnet_threshold: 70

sources:
  ashby:
    - modal
    - langchain
    - cohere
    # Add more Ashby company slugs here

  greenhouse:
    - openai
    # Add more Greenhouse slugs here

  lever:
    - mistral
    # Add more Lever slugs here

  remoteok: false
  hn_hiring: false
  wellfound:
    query: "AI engineer autonomous agents Python"
    remote_only: true

apply:
  linkedin_server: "http://localhost:7433"
  blackreach_server: "http://localhost:7432"

mcp:
  port: 7434
```

- [ ] **Step 3: Create `profile/` placeholder files**

```bash
mkdir -p /mnt/GameDrive/AI_Projects/JobHound/profile
touch /mnt/GameDrive/AI_Projects/JobHound/profile/.gitkeep
```

Add `profile/*.md` and `profile/*.yaml` to `.gitignore` but keep the `.gitkeep`:
```
profile/*.md
profile/*.yaml
```

- [ ] **Step 4: Commit**

```bash
cd /mnt/GameDrive/AI_Projects/JobHound
git -c user.name="Null-Phnix" -c user.email="contact@phnix.dev" add .gitignore config.example.yaml profile/.gitkeep
git -c user.name="Null-Phnix" -c user.email="contact@phnix.dev" commit -m "chore: add config.example.yaml, protect secrets in .gitignore"
```

---

### Task 8: Write README for `jobhound-mcp`

**Files:**
- Create: `README-mcp.md` (will be renamed per-repo on push)

The MCP-focused README leads with the server and its 8 tools. Target audience: developers who want to add JobHound as a Claude Code MCP server.

- [ ] **Step 1: Create `README-mcp.md`**

```markdown
# JobHound MCP

**MCP server that lets Claude Code scan, score, and apply to jobs autonomously.**

JobHound connects directly to Ashby, Greenhouse, and Lever job board APIs — no browser required for discovery. It scores every listing with a keyword heuristic, queues high-scoring roles, and uses Claude Code as the tailor to write per-role CVs and cover letters.

## Install

```bash
git clone https://github.com/Null-Phnix/jobhound-mcp
cd jobhound-mcp
pip install -e .
cp config.example.yaml config.yaml  # fill in your details
```

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

## Tools

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

## Config

See `config.example.yaml`. Supports Ashby, Greenhouse, Lever, RemoteOK, HN Hiring, and Wellfound.

## Stack

- Python 3.11+
- `fastmcp` — MCP server
- `httpx` — source API calls
- `sqlite3` — job tracking
- `textual` — TUI (optional, see jobhound-tui)

## License

MIT
```

---

### Task 9: Write README for `jobhound-tui`

**Files:**
- Create: `README-tui.md`

The TUI-focused README leads with the terminal dashboard. Target audience: developers who want to monitor their job pipeline visually.

- [ ] **Step 1: Create `README-tui.md`**

```markdown
# JobHound TUI

**Terminal dashboard for tracking job applications in real time.**

Live two-pane view of your entire job pipeline. Polls SQLite every 30 seconds, shows status by color, lets you scan for new jobs, open listings in a browser, and export your pipeline to Markdown or CSV.

## Screenshot

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

## Install

```bash
git clone https://github.com/Null-Phnix/jobhound-tui
cd jobhound-tui
pip install -e .
cp config.example.yaml config.yaml  # fill in your details
jobhound-tui
```

## Keybinds

| Key | Action |
|-----|--------|
| `s` | Scan sources (fetch + score, no auto-apply) |
| `p` | Pause / resume daemon |
| `f` | Cycle filter: all → new → queued → applied → failed → interviewing |
| `o` | Open highlighted job URL in browser |
| `x` | Export current view to `~/jobhound_export_YYYYMMDD.md` + `.csv` |
| `q` | Quit |

## Status Colors

| Color | Status |
|-------|--------|
| Cyan | new |
| Blue | queued (scored above threshold, awaiting tailoring) |
| Green | applied |
| Yellow | interviewing |
| Red | failed |
| Dim | rejected |

## Stack

- Python 3.11+
- `textual>=0.52` — TUI framework
- `sqlite3` — reads from jobhound.db (also used by MCP server and daemon)

## License

MIT
```

---

### Task 10: Create GitHub repos and push

**Files:** No file changes. Uses `gh` CLI.

Both repos use the same codebase. Each gets its own README. We'll push to each remote separately using the same local git repo but different remotes.

- [ ] **Step 1: Verify `gh` is authenticated**

```bash
gh auth status
```

Expected: `Logged in to github.com as Null-Phnix`

- [ ] **Step 2: Create `jobhound-mcp` repo**

```bash
gh repo create Null-Phnix/jobhound-mcp \
  --public \
  --description "MCP server that lets Claude Code scan, score, and apply to jobs autonomously"
```

- [ ] **Step 3: Create `jobhound-tui` repo**

```bash
gh repo create Null-Phnix/jobhound-tui \
  --public \
  --description "Terminal dashboard for tracking job applications in real time"
```

- [ ] **Step 4: Push as `jobhound-mcp`**

```bash
cd /mnt/GameDrive/AI_Projects/JobHound

# Copy MCP readme as README.md, commit, push, then restore
cp README-mcp.md README.md
git -c user.name="Null-Phnix" -c user.email="contact@phnix.dev" add README.md
git -c user.name="Null-Phnix" -c user.email="contact@phnix.dev" commit -m "docs: JobHound MCP README"

git remote add mcp https://github.com/Null-Phnix/jobhound-mcp.git
git -c user.name="Null-Phnix" -c user.email="contact@phnix.dev" push mcp main
```

- [ ] **Step 5: Swap README and push as `jobhound-tui`**

```bash
cd /mnt/GameDrive/AI_Projects/JobHound

cp README-tui.md README.md
git -c user.name="Null-Phnix" -c user.email="contact@phnix.dev" add README.md
git -c user.name="Null-Phnix" -c user.email="contact@phnix.dev" commit -m "docs: JobHound TUI README"

git remote add tui https://github.com/Null-Phnix/jobhound-tui.git
git -c user.name="Null-Phnix" -c user.email="contact@phnix.dev" push tui main
```

- [ ] **Step 6: Verify both repos are public with correct descriptions**

```bash
gh repo view Null-Phnix/jobhound-mcp
gh repo view Null-Phnix/jobhound-tui
```

---

## Chunk 3: phnix.dev Updates

> **Pattern corrections (override HTML in Tasks 12–14):**
> - `<script src="../js/main.js"></script>` does NOT exist. Use the inline `<script>` block from `ghboard.html` (lines 152–163).
> - `.proj-links` / `hr.proj-rule` / `.proj-table` / `.proj-code` are NOT defined in `project.css`. Use: `.proj-features`/`.feat`, `hr.end-rule`, plain `<table>`, plain `<pre>` respectively.
> - `.btn-primary` and `.btn-text` ARE defined in `style.css` — safe to use.
> - Every project page needs: `<div class="proj-footer-nav">`, `<footer>`, and the inline `<script>` before `</body>`.
> - Every blog post needs: `<div class="post-footer-nav">`, `<footer>`, and the inline `<script>` before `</body>`.

### Task 11: Add two project cards to index.html

**Files:**
- Modify: `/home/phnix/phnix.dev/index.html`

Two new cards are added to the `.projects-grid` div (lines 188–247). They follow the exact same pattern as the existing Orchestrator and ghboard cards.

- [ ] **Step 1: Insert two cards before the closing `</div>` of `.projects-grid`**

Find the closing `</div>` at line 247 (`    </div>`) after the ghboard card, and insert before it:

```html
      <div class="card reveal reveal-delay-2">
        <div class="project-badge badge-active">
          <span class="badge-dot"></span> Active
        </div>
        <div class="project-name">JobHound MCP</div>
        <p class="project-desc">
          MCP server that lets Claude Code scan, score, and apply to jobs
          autonomously. Connects directly to Ashby, Greenhouse, and Lever APIs.
          No browser required for discovery. Claude does the tailoring.
        </p>
        <div class="project-tags">
          <span class="tag">Python</span>
          <span class="tag">MCP</span>
          <span class="tag">FastMCP</span>
          <span class="tag">Automation</span>
        </div>
        <div style="display:flex;gap:16px;align-items:center;flex-wrap:wrap;">
          <a href="projects/jobhound-mcp.html" class="project-link">View project &rarr;</a>
          <a href="https://github.com/Null-Phnix/jobhound-mcp" target="_blank" class="project-link" style="color:var(--text-subtle);font-size:0.6rem;">github &nearr;</a>
        </div>
      </div>

      <div class="card reveal reveal-delay-3">
        <div class="project-badge badge-active">
          <span class="badge-dot"></span> Active
        </div>
        <div class="project-name">JobHound TUI</div>
        <p class="project-desc">
          Terminal dashboard for tracking 47 target companies in real time.
          Two-pane Textual layout, color-coded status, one-key export to
          Markdown and CSV. The control panel for the JobHound pipeline.
        </p>
        <div class="project-tags">
          <span class="tag">Python</span>
          <span class="tag">Textual</span>
          <span class="tag">TUI</span>
        </div>
        <div style="display:flex;gap:16px;align-items:center;flex-wrap:wrap;">
          <a href="projects/jobhound-tui.html" class="project-link">View project &rarr;</a>
          <a href="https://github.com/Null-Phnix/jobhound-tui" target="_blank" class="project-link" style="color:var(--text-subtle);font-size:0.6rem;">github &nearr;</a>
        </div>
      </div>
```

- [ ] **Step 2: Add blog post row to Writing section**

Find the existing post rows in the Writing section (starting around line 261). Insert a new row as post 05 (after the ghboard post at 04):

```html
      <a href="posts/why-i-built-jobhound.html" class="post-row">
        <span class="post-num">05</span>
        <div class="post-body-text">
          <span class="post-title">Why I built my own job application agent</span>
          <span class="post-sub">LazyApply, Simplify, Huntr — and why every existing tool failed a Canadian targeting Ashby-heavy AI companies.</span>
        </div>
        <div class="post-meta-col">
          <span class="post-date">Mar 2026</span>
          <span class="post-arrow">&rarr;</span>
        </div>
      </a>
```

---

### Task 12: Create `projects/jobhound-mcp.html`

**Files:**
- Create: `/home/phnix/phnix.dev/projects/jobhound-mcp.html`

Follows the exact structure of `projects/ghboard.html`: same nav, same CSS imports (`style.css` + `project.css`), same `.proj-wrap` layout.

- [ ] **Step 1: Create the file**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>JobHound MCP | phnix.dev</title>
  <link rel="icon" type="image/png" href="../favicon.png">
  <link rel="stylesheet" href="../style.css">
  <link rel="stylesheet" href="project.css">
  <meta name="description" content="MCP server that lets Claude Code scan, score, and apply to jobs autonomously via Ashby, Greenhouse, and Lever APIs.">
  <meta property="og:title" content="JobHound MCP | phnix.dev">
  <meta property="og:description" content="MCP server that lets Claude Code scan, score, and apply to jobs autonomously.">
  <meta property="og:url" content="https://phnix.dev/projects/jobhound-mcp.html">
  <meta property="og:type" content="website">
  <meta property="og:image" content="https://phnix.dev/favicon.png">
  <meta name="twitter:card" content="summary">
  <meta name="twitter:title" content="JobHound MCP | phnix.dev">
  <meta name="twitter:description" content="MCP server that lets Claude Code scan, score, and apply to jobs autonomously.">
</head>
<body>
<div class="cursor" id="cursor"></div>
<div class="cursor-ring" id="cursorRing"></div>
<div class="void"></div>
<div class="void-accent"></div>
<div class="post-progress" id="progress"></div>

<nav>
  <a href="/" class="nav-logo">phnix<span>.dev</span></a>
  <ul class="nav-links">
    <li><a href="/#projects">Projects</a></li>
    <li><a href="../blog/">Writing</a></li>
    <li><a href="https://gitlab.com/null.phnix" target="_blank">GitLab</a></li>
    <li><a href="https://github.com/Null-Phnix" target="_blank">GitHub</a></li>
    <li><a href="/#hire" class="nav-hire">Hire</a></li>
  </ul>
</nav>

<div class="proj-wrap">
  <div class="proj-nav-row">
    <a href="/" class="back-link">&larr; All projects</a>
    <div class="project-badge badge-active">
      <span class="badge-dot"></span> Active
    </div>
  </div>

  <div class="proj-hero">
    <h1>JobHound MCP</h1>
    <p class="proj-tagline">
      MCP server that lets Claude Code scan, score, and apply to jobs autonomously.
      Connects directly to Ashby, Greenhouse, and Lever job board APIs.
      No browser. No resume upload portals. Claude does the tailoring.
    </p>
  </div>

  <div class="proj-stats">
    <div class="proj-stat">
      <div class="proj-stat-val">Python</div>
      <div class="proj-stat-lbl">language</div>
    </div>
    <div class="proj-stat">
      <div class="proj-stat-val">8</div>
      <div class="proj-stat-lbl">MCP tools</div>
    </div>
    <div class="proj-stat">
      <div class="proj-stat-val">3</div>
      <div class="proj-stat-lbl">ATS sources</div>
    </div>
    <div class="proj-stat">
      <div class="proj-stat-val">MIT</div>
      <div class="proj-stat-lbl">license</div>
    </div>
  </div>

  <div class="proj-links">
    <a href="https://github.com/Null-Phnix/jobhound-mcp" target="_blank" class="btn-primary">GitHub &nearr;</a>
    <a href="../posts/why-i-built-jobhound.html" class="btn-text">Why I built this &rarr;</a>
  </div>

  <hr class="proj-rule">

  <div class="proj-body">
    <h2>What it does</h2>
    <p>
      JobHound MCP exposes the entire job application pipeline as Claude Code tool calls.
      You tell it to scan, it fetches every open role from your configured companies,
      scores them against your skills profile, and queues the relevant ones.
      From there, Claude reads the job description alongside your resume and writes
      a tailored CV and cover letter. One more tool call submits it.
    </p>

    <h2>The 8 tools</h2>
    <table class="proj-table">
      <thead>
        <tr><th>Tool</th><th>Description</th></tr>
      </thead>
      <tbody>
        <tr><td><code>jobhound_scan()</code></td><td>Fetch all sources, score jobs, queue high-scoring ones</td></tr>
        <tr><td><code>jobhound_list(status)</code></td><td>List jobs by status — queued, applied, failed, etc.</td></tr>
        <tr><td><code>jobhound_get(id)</code></td><td>Full job details including generated cover letter</td></tr>
        <tr><td><code>jobhound_get_for_tailoring(id)</code></td><td>Job description + your resume, ready for Claude to tailor</td></tr>
        <tr><td><code>jobhound_apply_tailored(id, cv, letter)</code></td><td>Submit a tailored application and record the result</td></tr>
        <tr><td><code>jobhound_update(id, status)</code></td><td>Manually set status — interviewing, rejected, etc.</td></tr>
        <tr><td><code>jobhound_pause()</code></td><td>Pause the daemon scan loop</td></tr>
        <tr><td><code>jobhound_resume()</code></td><td>Resume the daemon scan loop</td></tr>
      </tbody>
    </table>

    <h2>Claude Code setup</h2>
    <pre class="proj-code">{
  "mcpServers": {
    "jobhound": {
      "type": "stdio",
      "command": "jobhound-server"
    }
  }
}</pre>
    <p>Add to <code>~/.claude/settings.json</code> or your project's <code>.claude/settings.json</code>.</p>

    <h2>Sources</h2>
    <p>
      Configure target companies in <code>config.yaml</code>.
      JobHound fetches directly from the ATS APIs — no scraping, no login required.
    </p>
    <ul>
      <li><strong>Ashby</strong> — <code>api.ashbyhq.com/posting-api/job-board/{slug}</code></li>
      <li><strong>Greenhouse</strong> — <code>boards-api.greenhouse.io/v1/boards/{slug}/jobs</code></li>
      <li><strong>Lever</strong> — <code>api.lever.co/v0/postings/{slug}</code></li>
      <li><strong>RemoteOK</strong> — full feed, scorer filters by keyword</li>
      <li><strong>HN Hiring</strong> — current month's thread via Algolia</li>
    </ul>

    <h2>Stack</h2>
    <div class="project-tags" style="margin-top:8px;">
      <span class="tag">Python 3.11+</span>
      <span class="tag">FastMCP</span>
      <span class="tag">httpx</span>
      <span class="tag">sqlite3</span>
      <span class="tag">Textual</span>
    </div>
  </div>
</div>

<script src="../js/main.js"></script>
</body>
</html>
```

---

### Task 13: Create `projects/jobhound-tui.html`

**Files:**
- Create: `/home/phnix/phnix.dev/projects/jobhound-tui.html`

- [ ] **Step 1: Create the file**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>JobHound TUI | phnix.dev</title>
  <link rel="icon" type="image/png" href="../favicon.png">
  <link rel="stylesheet" href="../style.css">
  <link rel="stylesheet" href="project.css">
  <meta name="description" content="Terminal dashboard for tracking job applications in real time. Two-pane Textual layout, color-coded status, one-key CSV export.">
  <meta property="og:title" content="JobHound TUI | phnix.dev">
  <meta property="og:description" content="Terminal dashboard for tracking job applications in real time.">
  <meta property="og:url" content="https://phnix.dev/projects/jobhound-tui.html">
  <meta property="og:type" content="website">
  <meta property="og:image" content="https://phnix.dev/favicon.png">
  <meta name="twitter:card" content="summary">
  <meta name="twitter:title" content="JobHound TUI | phnix.dev">
  <meta name="twitter:description" content="Terminal dashboard for tracking job applications in real time.">
</head>
<body>
<div class="cursor" id="cursor"></div>
<div class="cursor-ring" id="cursorRing"></div>
<div class="void"></div>
<div class="void-accent"></div>
<div class="post-progress" id="progress"></div>

<nav>
  <a href="/" class="nav-logo">phnix<span>.dev</span></a>
  <ul class="nav-links">
    <li><a href="/#projects">Projects</a></li>
    <li><a href="../blog/">Writing</a></li>
    <li><a href="https://gitlab.com/null.phnix" target="_blank">GitLab</a></li>
    <li><a href="https://github.com/Null-Phnix" target="_blank">GitHub</a></li>
    <li><a href="/#hire" class="nav-hire">Hire</a></li>
  </ul>
</nav>

<div class="proj-wrap">
  <div class="proj-nav-row">
    <a href="/" class="back-link">&larr; All projects</a>
    <div class="project-badge badge-active">
      <span class="badge-dot"></span> Active
    </div>
  </div>

  <div class="proj-hero">
    <h1>JobHound TUI</h1>
    <p class="proj-tagline">
      Terminal dashboard for tracking job applications in real time.
      Two-pane Textual layout — job list on the left, full details on the right.
      Color-coded by status, one key to export, one key to open any listing.
    </p>
  </div>

  <div class="proj-stats">
    <div class="proj-stat">
      <div class="proj-stat-val">Python</div>
      <div class="proj-stat-lbl">language</div>
    </div>
    <div class="proj-stat">
      <div class="proj-stat-val">Textual</div>
      <div class="proj-stat-lbl">framework</div>
    </div>
    <div class="proj-stat">
      <div class="proj-stat-val">30s</div>
      <div class="proj-stat-lbl">poll interval</div>
    </div>
    <div class="proj-stat">
      <div class="proj-stat-val">MIT</div>
      <div class="proj-stat-lbl">license</div>
    </div>
  </div>

  <div class="proj-links">
    <a href="https://github.com/Null-Phnix/jobhound-tui" target="_blank" class="btn-primary">GitHub &nearr;</a>
    <a href="../posts/why-i-built-jobhound.html" class="btn-text">Why I built this &rarr;</a>
  </div>

  <hr class="proj-rule">

  <div class="proj-body">
    <h2>Screenshot</h2>
    <pre class="proj-code">┌─ JobHound ──────────────────────────────────────────────────────┐
│ [LIVE] 47 tracked · 3 queued · 12 applied · 2 interviewing      │
├──────────────────────────┬──────────────────────────────────────┤
│ ▶ Bree          applied  │  Bree — Software Engineer, Backend    │
│   Modal         applied  │  Applied: 2026-03-11 via Ashby        │
│   LangChain     applied  │  Score: 87/100                        │
│   Cohere        queued   │  Method: direct POST                  │
│   Anthropic     new      │                                       │
│   Cursor        failed   │  Cover Letter:                        │
│                          │  &gt; The line that stood out...        │
├──────────────────────────┴──────────────────────────────────────┤
│ [s]can  [p]ause  [f]ilter  [o]pen URL  [x]export  [q]uit        │
└─────────────────────────────────────────────────────────────────┘</pre>

    <h2>Keybinds</h2>
    <table class="proj-table">
      <thead>
        <tr><th>Key</th><th>Action</th></tr>
      </thead>
      <tbody>
        <tr><td><code>s</code></td><td>Scan sources — fetch and score new jobs, no auto-apply</td></tr>
        <tr><td><code>p</code></td><td>Pause / resume the daemon</td></tr>
        <tr><td><code>f</code></td><td>Cycle filter: all → new → queued → applied → failed → interviewing</td></tr>
        <tr><td><code>o</code></td><td>Open highlighted job URL in browser</td></tr>
        <tr><td><code>x</code></td><td>Export current view to <code>~/jobhound_export_YYYYMMDD.md</code> and <code>.csv</code></td></tr>
        <tr><td><code>q</code></td><td>Quit</td></tr>
      </tbody>
    </table>

    <h2>Status colors</h2>
    <table class="proj-table">
      <thead>
        <tr><th>Color</th><th>Status</th></tr>
      </thead>
      <tbody>
        <tr><td>Cyan</td><td>new — discovered, not yet scored above threshold</td></tr>
        <tr><td>Blue</td><td>queued — scored above threshold, waiting for tailoring</td></tr>
        <tr><td>Green</td><td>applied</td></tr>
        <tr><td>Yellow</td><td>interviewing</td></tr>
        <tr><td>Red</td><td>failed</td></tr>
        <tr><td>Dim</td><td>rejected</td></tr>
      </tbody>
    </table>

    <h2>Install</h2>
    <pre class="proj-code">git clone https://github.com/Null-Phnix/jobhound-tui
cd jobhound-tui
pip install -e .
cp config.example.yaml config.yaml
jobhound-tui</pre>

    <h2>Stack</h2>
    <div class="project-tags" style="margin-top:8px;">
      <span class="tag">Python 3.11+</span>
      <span class="tag">Textual ≥0.52</span>
      <span class="tag">sqlite3</span>
    </div>
  </div>
</div>

<script src="../js/main.js"></script>
</body>
</html>
```

---

### Task 14: Create blog post `posts/why-i-built-jobhound.html`

**Files:**
- Create: `/home/phnix/phnix.dev/posts/why-i-built-jobhound.html`

Follows the exact structure of `posts/how-blackreach-works.html`: same nav, same CSS imports (`style.css` + `post.css`), same `.post-wrap` layout.

- [ ] **Step 1: Create the file**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Why I built my own job application agent | phnix.dev</title>
  <link rel="icon" type="image/png" href="../favicon.png">
  <link rel="stylesheet" href="../style.css">
  <link rel="stylesheet" href="post.css">
  <meta name="description" content="LazyApply, Simplify, Huntr — and why every existing AI job tool failed a Canadian targeting Ashby-heavy AI companies.">
  <meta property="og:title" content="Why I built my own job application agent | phnix.dev">
  <meta property="og:description" content="LazyApply, Simplify, Huntr — and why every existing AI job tool failed a Canadian targeting Ashby-heavy AI companies.">
  <meta property="og:url" content="https://phnix.dev/posts/why-i-built-jobhound.html">
  <meta property="og:type" content="website">
  <meta property="og:image" content="https://phnix.dev/favicon.png">
  <meta name="twitter:card" content="summary">
  <meta name="twitter:title" content="Why I built my own job application agent | phnix.dev">
  <meta name="twitter:description" content="LazyApply, Simplify, Huntr — and why every existing AI job tool failed a Canadian targeting Ashby-heavy AI companies.">
</head>
<body>
<div class="cursor" id="cursor"></div>
<div class="cursor-ring" id="cursorRing"></div>
<div class="void"></div>
<div class="post-progress" id="progress"></div>

<nav>
  <a href="/" class="nav-logo">phnix<span>.dev</span></a>
  <ul class="nav-links">
    <li><a href="/#projects">Projects</a></li>
    <li><a href="../blog/">Writing</a></li>
    <li><a href="https://gitlab.com/null.phnix" target="_blank">GitLab</a></li>
    <li><a href="https://github.com/Null-Phnix" target="_blank">GitHub</a></li>
    <li><a href="/#hire" class="nav-hire">Hire</a></li>
  </ul>
</nav>

<div class="post-wrap">
  <div class="post-nav-row">
    <a href="../blog/" class="back-link">&larr; All posts</a>
    <span class="post-num-label">Post 05</span>
  </div>

  <div class="post-header">
    <div class="post-category">Engineering</div>
    <h1>Why I built my own job application agent (and why every existing tool failed me)</h1>
    <div class="post-byline">
      <span>phnix</span>
      <span class="sep">/</span>
      <span>March 2026</span>
      <span class="sep">/</span>
      <span>6 min read</span>
    </div>
  </div>

  <hr class="post-rule">

  <div class="post-body">
    <div class="callout">
      JobHound is open source. The MCP server is at
      <a href="https://github.com/Null-Phnix/jobhound-mcp" target="_blank">jobhound-mcp</a>
      and the TUI is at
      <a href="https://github.com/Null-Phnix/jobhound-tui" target="_blank">jobhound-tui</a>.
    </div>

    <h2>The problem</h2>
    <p>
      I had a list of 47 companies I wanted to apply to. Not 500. Not "whatever's
      on Indeed." Forty-seven specific AI companies — Anthropic, Modal, LangChain,
      Cohere, Cursor, E2B, Replit, Perplexity, Supabase. The ones building the
      infrastructure I want to work on.
    </p>
    <p>
      Almost all of them use Ashby, Greenhouse, or Lever as their ATS.
      None of the mainstream "AI job tools" support any of these.
    </p>

    <h2>What I tried</h2>

    <h3>LazyApply — 1.9 stars on the Chrome Store</h3>
    <p>
      LazyApply's pitch is "apply to hundreds of jobs in one click."
      In practice it autofills LinkedIn Easy Apply forms and calls that an application.
      It has no support for Ashby. It has no support for Greenhouse.
      It has no support for Lever.
      That's the entire list of ATS platforms my 47 companies use.
    </p>
    <p>
      Even on LinkedIn it's unreliable. The 1.9-star rating is deserved —
      users consistently report it submitting blank or half-filled applications,
      triggering spam flags, and auto-applying to jobs they never approved.
      Not useful. Actually harmful.
    </p>

    <h3>Simplify — autofill overlay, not an applicator</h3>
    <p>
      Simplify is a browser extension that pre-fills application forms as you
      navigate to them. It doesn't submit anything. You still have to click Apply
      on every single form. For someone applying to 47 companies, that's 47
      manual sessions, 47 times you have to open a browser, find the form,
      verify the autofill is correct, and click.
    </p>
    <p>
      It also has no Ashby support. Simplify works on jobs.lever.co and
      boards.greenhouse.io, but not on the custom Ashby domains like
      jobs.ashbyhq.com or company-specific portals.
    </p>

    <h3>Huntr and Teal — trackers, not applicators</h3>
    <p>
      Huntr and Teal are Kanban-style job trackers. They let you move cards
      from "Applied" to "Interview" to "Offer." They don't submit applications.
      They don't connect to any ATS. They're spreadsheets with a better UI.
    </p>
    <p>
      Useful for tracking. Not what I needed.
    </p>

    <h3>Loopcv and Sonara — wrong job boards entirely</h3>
    <p>
      Loopcv and Sonara advertise "automated job applications." They work by
      scraping Indeed, LinkedIn Jobs, and a handful of general job boards,
      then submitting your resume wherever they can.
    </p>
    <p>
      The companies I'm targeting don't post on Indeed. They post on their
      own Ashby portals, their own Greenhouse boards, their careers pages.
      Loopcv doesn't know those exist. It can't reach them.
    </p>

    <h2>Why these tools specifically don't work for me</h2>
    <p>
      The failure isn't bad software — it's that these tools were built for a
      different use case. They're built for high-volume applications to jobs
      on mainstream aggregators. The strategy is: apply to 500 roles on Indeed,
      get 5 responses, take the best one.
    </p>
    <p>
      That strategy doesn't work for me for two reasons:
    </p>
    <ol>
      <li>
        I'm Canadian, applying to US companies. Most of those 500 Indeed jobs
        won't sponsor visas or hire internationally. The signal-to-noise ratio
        is terrible for my situation.
      </li>
      <li>
        I'm not interested in most companies. The 47 companies I'm targeting are
        the ones I actually want to work at — the ones building what I care about.
        Spraying applications at 500 random companies to hit 47 specific ones
        is backwards.
      </li>
    </ol>
    <p>
      The Ashby job board API is public. <code>api.ashbyhq.com/posting-api/job-board/{slug}</code>
      returns every open role in JSON. No authentication. No scraping.
      The data is just there, waiting to be fetched. Every tool in this space
      is doing browser automation on job aggregators and none of them are
      calling the APIs that the actual companies use.
    </p>

    <h2>What JobHound does instead</h2>
    <p>
      JobHound calls the source APIs directly. It fetches every open role from
      every company in my list, scores each one with a keyword heuristic
      (no Claude call, just Python), and queues the ones that match my profile.
      Claude Code then reads the job description alongside my resume and writes
      a tailored CV and cover letter for each role. Playwright submits the
      application form.
    </p>
    <p>
      The whole thing runs as an MCP server. From inside Claude Code:
    </p>
    <pre>jobhound_scan()                    # fetch and score
jobhound_list("queued")            # see what's waiting
jobhound_get_for_tailoring(42)     # read the job + resume
[Claude writes the tailored docs]
jobhound_apply_tailored(42, ...)   # submit</pre>

    <h2>Results</h2>
    <p>
      First run: 47 target companies, one session. 8 confirmed submissions
      (Cognition, LangChain, Bree, Oscilar, Modal, Supabase, and two others),
      with more pending once IP rate limits reset. Every application had a
      tailored cover letter and a re-ordered CV that emphasized the skills
      most relevant to that specific role.
    </p>
    <p>
      The tools that were supposed to automate this gave me 0.
      The tool I built in a weekend gave me 8.
    </p>
    <p>
      Both repos are on GitHub:
      <a href="https://github.com/Null-Phnix/jobhound-mcp" target="_blank">jobhound-mcp</a> (MCP server) and
      <a href="https://github.com/Null-Phnix/jobhound-tui" target="_blank">jobhound-tui</a> (terminal dashboard).
    </p>
  </div>
</div>

<script src="../js/main.js"></script>
</body>
</html>
```

---

### Task 15: Commit phnix.dev changes

- [ ] **Step 1: Commit all phnix.dev changes**

```bash
cd /home/phnix/phnix.dev
git add index.html projects/jobhound-mcp.html projects/jobhound-tui.html posts/why-i-built-jobhound.html
git -c user.name="Null-Phnix" -c user.email="contact@phnix.dev" commit -m "feat: add JobHound MCP + TUI project pages and blog post"
```

- [ ] **Step 2: Push if remote exists**

```bash
cd /home/phnix/phnix.dev
git remote -v
# If origin exists:
git -c user.name="Null-Phnix" -c user.email="contact@phnix.dev" push origin main
```

---

## Summary

| Chunk | Tasks | Deliverable |
|-------|-------|-------------|
| 1 — TUI | 1–6 | `tui/app.py` with queued status, fetch-only scan, export, open URL, fixed config |
| 2 — GitHub | 7–10 | Two public repos: `Null-Phnix/jobhound-mcp`, `Null-Phnix/jobhound-tui` |
| 3 — Website | 11–15 | Two project cards, two detail pages, one blog post on phnix.dev |
