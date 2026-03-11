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
