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
