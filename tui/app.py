"""
JobHound TUI — live two-pane view of application status.
Usage: jobhound-tui  (run from JobHound project root)
"""
import csv
import os
import threading
import webbrowser
from datetime import date
from pathlib import Path
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Static, Label, Input
from textual.containers import Horizontal, Vertical
from textual.binding import Binding
from jobhound.config import load_config
from jobhound.tracker import Tracker
from jobhound.models import Job, Status

_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
_CONFIG_PATH = Path(os.environ.get("JOBHOUND_ROOT", str(_PROJECT_ROOT))) / "config.yaml"

STATUS_COLORS = {
    "new": "cyan",
    "queued": "blue",
    "applied": "green",
    "failed": "red",
    "interviewing": "yellow",
    "rejected": "dim",
}


def _score_markup(score: int) -> str:
    if score >= 70:
        return f"[green]{score}[/green]"
    if score >= 50:
        return f"[yellow]{score}[/yellow]"
    return f"[dim]{score}[/dim]"


class JobDetail(Static):
    def show(self, job: Job):
        status_color = STATUS_COLORS.get(job.status.value, "white")
        score_color = "green" if job.score >= 70 else ("yellow" if job.score >= 50 else "dim")
        text = (
            f"[bold]{job.company}[/bold] — {job.title}\n"
            f"[{status_color}]Status: {job.status.value}[/{status_color}]"
            f"  |  [{score_color}]Score: {job.score}[/{score_color}]  |  Source: {job.source}\n"
            f"Location: {job.location or 'N/A'}  |  Remote: {'Yes' if job.remote else 'No'}\n"
            f"Applied: {job.applied_at or 'N/A'}  |  Method: {job.method or 'N/A'}\n"
            f"URL: {job.url}\n"
        )
        if job.notes:
            text += f"\n[bold]Notes:[/bold]\n{job.notes}\n"
        if job.cover_letter:
            text += f"\n[dim]Cover Letter:[/dim]\n{job.cover_letter[:800]}"
            if len(job.cover_letter) > 800:
                text += "..."
        self.update(text)


class JobHoundApp(App):
    CSS = """
    Screen { layout: vertical; }
    #stats { height: 1; background: $panel; padding: 0 1; }
    #search-bar { height: 1; background: $panel; padding: 0 1; display: none; }
    #search-bar Input { width: 100%; }
    #main { layout: horizontal; height: 1fr; }
    #job-list { width: 40%; border-right: solid $panel; }
    #job-detail { width: 60%; padding: 1 2; overflow-y: auto; }
    Footer { height: 1; }
    """

    BINDINGS = [
        Binding("s", "scan", "Scan"),
        Binding("p", "pause", "Pause/Resume"),
        Binding("f", "filter_cycle", "Filter"),
        Binding("slash", "search", "Search"),
        Binding("escape", "clear_search", "Clear", show=False),
        Binding("o", "open_url", "Open URL"),
        Binding("i", "mark_interviewing", "Interviewing"),
        Binding("r", "mark_rejected", "Reject"),
        Binding("x", "export", "Export"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self):
        super().__init__()
        cfg = load_config(_CONFIG_PATH)
        self.tracker = Tracker(cfg.db_path)
        self.tracker.init()
        self._cfg = cfg
        self._filter: str | None = None
        self._search: str = ""
        self._paused = False
        self._jobs: list[Job] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Label("", id="stats")
        with Horizontal(id="search-bar"):
            yield Input(placeholder="Search by company name...", id="search-input")
        with Horizontal(id="main"):
            with Vertical(id="job-list"):
                yield DataTable(id="table", cursor_type="row")
            with Vertical(id="job-detail"):
                yield JobDetail("Select a job to view details.", id="detail")
        yield Footer()

    def on_mount(self):
        table = self.query_one("#table", DataTable)
        table.add_columns("Company", "Title", "Status", "Score")
        self.refresh_jobs()
        self.set_interval(30, self.refresh_jobs)

    def refresh_jobs(self):
        table = self.query_one("#table", DataTable)
        table.clear()
        jobs = self.tracker.get_all(limit=500)
        total_unfiltered = len(jobs)

        if self._filter:
            try:
                jobs = [j for j in jobs if j.status == Status(self._filter)]
            except ValueError:
                pass

        if self._search:
            query = self._search.lower()
            jobs = [j for j in jobs if query in j.company.lower() or query in j.title.lower()]

        self._jobs = jobs
        stats = self.tracker.stats()
        total = sum(stats.values())
        applied = stats.get("applied", 0)
        interviewing = stats.get("interviewing", 0)
        failed = stats.get("failed", 0)
        queued = stats.get("queued", 0)
        rejected = stats.get("rejected", 0)
        filter_label = f" [dim][filter: {self._filter}][/dim]" if self._filter else ""
        search_label = f" [dim][search: {self._search}][/dim]" if self._search else ""
        showing = f"[dim]showing {len(jobs)} of {total}[/dim]  " if len(jobs) != total else ""
        self.query_one("#stats", Label).update(
            f"[bold]JobHound[/bold]  {showing}{total} tracked · "
            f"[blue]{queued} queued[/blue] · "
            f"[green]{applied} applied[/green] · "
            f"[yellow]{interviewing} interviewing[/yellow] · "
            f"[red]{failed} failed[/red] · "
            f"[dim]{rejected} rejected[/dim]"
            + (" [red][PAUSED][/red]" if self._paused else " [green][LIVE][/green]")
            + filter_label
            + search_label
        )

        for job in jobs:
            color = STATUS_COLORS.get(job.status.value, "white")
            table.add_row(
                job.company[:25],
                job.title[:35],
                f"[{color}]{job.status.value}[/{color}]",
                _score_markup(job.score),
            )

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted):
        if self._jobs and event.cursor_row < len(self._jobs):
            job = self._jobs[event.cursor_row]
            self.query_one("#detail", JobDetail).show(job)

    def _get_selected_job(self) -> Job | None:
        if not self._jobs:
            return None
        table = self.query_one("#table", DataTable)
        row = table.cursor_row
        if 0 <= row < len(self._jobs):
            return self._jobs[row]
        return None

    def action_scan(self):
        self.query_one("#stats", Label).update("[bold]JobHound[/bold]  [yellow]Scanning...[/yellow]")

        def _run():
            from jobhound.daemon import _build_sources
            from jobhound.scorer import Scorer
            from jobhound.models import Status
            cfg = self._cfg
            scorer = Scorer(cfg.skills_path)
            count = 0
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
                        count += 1
                except Exception:
                    pass
            self.call_from_thread(self.refresh_jobs)
        threading.Thread(target=_run, daemon=True).start()

    def action_pause(self):
        import jobhound.daemon as d
        self._paused = not self._paused
        d._paused = self._paused
        self.refresh_jobs()

    def action_filter_cycle(self):
        filters = [None, "new", "queued", "applied", "failed", "interviewing", "rejected"]
        try:
            current = filters.index(self._filter)
        except ValueError:
            current = 0
        self._filter = filters[(current + 1) % len(filters)]
        self.refresh_jobs()

    def action_search(self):
        search_bar = self.query_one("#search-bar")
        search_input = self.query_one("#search-input", Input)
        search_bar.styles.display = "block"
        search_input.value = self._search
        search_input.focus()

    def on_input_submitted(self, event: Input.Submitted):
        if event.input.id == "search-input":
            self._search = event.value.strip()
            self.query_one("#search-bar").styles.display = "none"
            self.query_one("#table", DataTable).focus()
            self.refresh_jobs()

    def action_clear_search(self):
        search_bar = self.query_one("#search-bar")
        if search_bar.styles.display == "block":
            search_bar.styles.display = "none"
            self.query_one("#table", DataTable).focus()
            return
        if self._search:
            self._search = ""
            self.refresh_jobs()

    def action_mark_interviewing(self):
        job = self._get_selected_job()
        if job:
            self.tracker.update_status(job.url, Status.INTERVIEWING)
            self.refresh_jobs()

    def action_mark_rejected(self):
        job = self._get_selected_job()
        if job:
            self.tracker.update_status(job.url, Status.REJECTED)
            self.refresh_jobs()

    def action_open_url(self):
        job = self._get_selected_job()
        if job:
            webbrowser.open(job.url)

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

        self.query_one("#stats", Label).update(
            f"[green]Exported {len(self._jobs)} jobs to ~/jobhound_export_{today}.md / .csv[/green]"
        )
        self.set_timer(3, self.refresh_jobs)


def main():
    JobHoundApp().run()


if __name__ == "__main__":
    main()
