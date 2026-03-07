"""CodeQuest TUI Application - Built with Textual."""

import subprocess
import threading
import webbrowser
from datetime import datetime
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Markdown,
    ProgressBar,
    Static,
)

from codequest.assets.pixel_art import BADGES, ICONS, LOGO, NO_README, WELCOME_ART
from codequest.config import get_config, save_config
from codequest.models import ModelSelector
from codequest.scanner import ProjectInfo, get_projects, save_index, scan_all


class WelcomeScreen(Screen):
    """First-run welcome screen with tutorial and auto-scan."""

    BINDINGS = [
        Binding("enter", "start_scan", "Start Scanning"),
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="welcome-container"):
            yield Static(WELCOME_ART, id="welcome-art")
            yield Static(
                "Arrow keys to navigate | Enter to select | q to quit | ? for help | w for web",
                id="welcome-instructions",
            )
            yield ProgressBar(total=100, show_eta=False, id="scan-progress")
            with Horizontal(classes="welcome-buttons"):
                yield Button("[ START SCAN ]", variant="success", classes="welcome-button", id="btn-scan")
                yield Button("[ QUIT ]", variant="error", classes="welcome-button", id="btn-quit")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-scan":
            self.action_start_scan()
        elif event.button.id == "btn-quit":
            self.app.exit()

    def action_start_scan(self) -> None:
        progress = self.query_one("#scan-progress", ProgressBar)
        progress.update(progress=30)
        self.run_worker(self._do_scan())

    async def _do_scan(self) -> None:
        progress = self.query_one("#scan-progress", ProgressBar)
        progress.update(progress=50)

        projects = scan_all()
        save_index(projects)

        progress.update(progress=90)

        config = get_config()
        config["first_run_complete"] = True
        save_config(config)

        progress.update(progress=100)

        self.app.pop_screen()
        dashboard = self.app.query_one(DashboardScreen) if self.app.screen.name == "dashboard" else None
        if dashboard is None:
            self.app.push_screen(DashboardScreen())


class HelpPanel(Screen):
    """Help overlay."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
        Binding("question_mark", "dismiss", "Close"),
    ]

    def compose(self) -> ComposeResult:
        with Container(id="help-panel"):
            yield Static(
                "[bold cyan]CodeQuest Help[/]\n\n"
                "[green]Navigation:[/]\n"
                "  Up/Down     Navigate projects\n"
                "  Enter       Open project detail\n"
                "  Escape      Go back\n"
                "  /           Search projects\n\n"
                "[green]Actions:[/]\n"
                "  r           Run selected project\n"
                "  w           Open web dashboard\n"
                "  s           Settings\n"
                "  F5          Rescan projects\n"
                "  ?           This help screen\n"
                "  q           Quit\n\n"
                "[dim]Press Escape to close[/]"
            )


class ProjectDetailScreen(Screen):
    """Detail view for a single project."""

    BINDINGS = [
        Binding("escape", "go_back", "Back"),
        Binding("q", "go_back", "Back"),
    ]

    def __init__(self, project: ProjectInfo) -> None:
        super().__init__()
        self.project = project
        self.model_selector = ModelSelector()

    def compose(self) -> ComposeResult:
        p = self.project
        # Build badge string
        badges = []
        if p.is_git_repo:
            badges.append("[bold blue]\\[GIT][/]")
        if p.has_github:
            badges.append("[bold white]\\[GITHUB][/]")
        if p.is_claude_made:
            badges.append("[bold #cc85ff]\\[CLAUDE][/]")
        if not p.is_git_repo:
            badges.append("[dim]\\[LOCAL][/]")
        badge_str = " ".join(badges)

        type_icon = ICONS.get(p.project_type, ICONS["Unknown"])

        yield Header(show_clock=True)

        yield Static(
            f"  {type_icon} [bold]{p.name}[/] [{p.project_type}] {badge_str}   [dim]{p.path}[/]",
            id="detail-header",
        )

        with Horizontal(id="detail-container"):
            # Left: README
            with VerticalScroll(id="readme-view"):
                if p.readme_content:
                    yield Markdown(p.readme_content)
                else:
                    yield Static(NO_README.format(project_type=p.project_type))

            # Right: Sidebar
            with Vertical(id="sidebar"):
                yield Label("[bold cyan]Run Commands[/]")
                from codequest.runner import get_run_commands

                commands = get_run_commands(p.path, get_config().get("overrides"))
                if commands:
                    for i, cmd in enumerate(commands):
                        yield Button(
                            f"> {cmd.label}",
                            classes="run-button",
                            id=f"run-{i}",
                            name=cmd.command,
                        )
                else:
                    yield Static("[dim]No run commands detected[/]")

                yield Static("", id="run-output")

                yield Label("\n[bold #ff00ff]Ask AI[/]", id="ai-section")
                yield Input(
                    placeholder="Ask about this project...",
                    id="ai-input",
                )
                yield Button("[ ASK ]", id="ai-send")
                yield Static("", id="ai-response")

        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id and event.button.id.startswith("run-"):
            command_str = event.button.name
            if command_str:
                self._run_command(command_str)
        elif event.button.id == "ai-send":
            self._ask_ai()

    def _run_command(self, command: str) -> None:
        output_widget = self.query_one("#run-output", Static)
        output_widget.update(f"[yellow]Running: {command}...[/]")
        self.run_worker(self._execute(command))

    async def _execute(self, command: str) -> None:
        from codequest.runner import RunCommand, execute_command

        cmd = RunCommand(label=command, command=command, cwd=str(self.project.path))
        result = execute_command(cmd, timeout=60)
        output = result.stdout or result.stderr or "(no output)"
        color = "green" if result.returncode == 0 else "red"
        output_widget = self.query_one("#run-output", Static)
        # Truncate long output for TUI
        lines = output.strip().split("\n")
        if len(lines) > 30:
            output = "\n".join(lines[:30]) + f"\n... ({len(lines) - 30} more lines)"
        output_widget.update(f"[{color}]{output}[/]")

    def _ask_ai(self) -> None:
        input_widget = self.query_one("#ai-input", Input)
        question = input_widget.value.strip()
        if not question:
            return
        input_widget.value = ""
        response_widget = self.query_one("#ai-response", Static)
        response_widget.update("[dim]Thinking...[/]")
        self.run_worker(self._do_ask(question))

    async def _do_ask(self, question: str) -> None:
        p = self.project
        context = f"Project: {p.name}\nType: {p.project_type}\nPath: {p.path}\n\n"
        if p.readme_content:
            context += f"README:\n{p.readme_content[:3000]}\n"

        answer = self.model_selector.ask(question, context)
        response_widget = self.query_one("#ai-response", Static)
        model_name = self.model_selector.active_name
        response_widget.update(f"[dim]{model_name}:[/]\n[#ff00ff]{answer}[/]")

    def action_go_back(self) -> None:
        self.app.pop_screen()


class SettingsScreen(Screen):
    """Settings panel."""

    BINDINGS = [
        Binding("escape", "go_back", "Back"),
    ]

    def compose(self) -> ComposeResult:
        config = get_config()
        yield Header(show_clock=True)
        with VerticalScroll(id="settings-container"):
            yield Label("[bold cyan]Settings[/]\n")

            yield Static("[bold green]Scan Paths:[/]", classes="setting-label")
            for sp in config.get("scan_paths", []):
                yield Static(f"  {sp}", classes="setting-value")

            yield Static(f"[bold green]Auto Discover:[/] {config.get('auto_discover')}", classes="setting-label")
            yield Static(f"[bold green]Theme:[/] {config.get('theme')}", classes="setting-label")

            llm = config.get("llm", {})
            yield Static(f"\n[bold #ff00ff]LLM Settings:[/]", classes="setting-label")
            yield Static(f"  Primary: {llm.get('primary')}", classes="setting-value")
            yield Static(f"  Claude Model: {llm.get('claude_model')}", classes="setting-value")
            yield Static(f"  Offline Model: {llm.get('offline_model')}", classes="setting-value")
            yield Static(f"  Fallback Model: {llm.get('fallback_model')}", classes="setting-value")

            ms = ModelSelector()
            yield Static(f"\n[bold yellow]Active Model:[/] {ms.active_name}", classes="setting-label")
            for status in ms.status():
                avail = "[green]OK[/]" if status["available"] else "[red]unavailable[/]"
                yield Static(f"  {status['name']}: {avail}", classes="setting-value")

            yield Static(f"\n[bold green]Web Port:[/] {config.get('web', {}).get('port', 8080)}", classes="setting-label")

            yield Button("[ RESCAN PROJECTS ]", id="rescan-button")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "rescan-button":
            self.run_worker(self._rescan())

    async def _rescan(self) -> None:
        projects = scan_all()
        save_index(projects)
        self.notify(f"Rescan complete: {len(projects)} projects found", title="CodeQuest")

    def action_go_back(self) -> None:
        self.app.pop_screen()


class DashboardScreen(Screen):
    """Main project dashboard with data table."""

    BINDINGS = [
        Binding("slash", "focus_search", "Search", show=True),
        Binding("r", "run_project", "Run", show=True),
        Binding("w", "open_web", "Web", show=True),
        Binding("s", "open_settings", "Settings", show=True),
        Binding("f5", "rescan", "Rescan", show=True),
        Binding("question_mark", "show_help", "Help", show=True),
        Binding("q", "quit", "Quit", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._projects: list[ProjectInfo] = []
        self._filter: str = "All"
        self._web_process = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Container(id="dashboard"):
            with Container(id="search-bar"):
                yield Input(placeholder="/ Search projects...", id="search-input")

            with Horizontal(id="filter-bar"):
                for t in ["All", "Python", "Node", "Bash", "Rust", "Go", "Static"]:
                    cls = "filter-btn active" if t == "All" else "filter-btn"
                    yield Button(t, classes=cls, id=f"filter-{t.lower()}")

            yield DataTable(id="project-table")

        yield Footer()

    def on_mount(self) -> None:
        self._load_projects()

    def _load_projects(self) -> None:
        self._projects = get_projects()
        self._refresh_table()

    def _refresh_table(self) -> None:
        table = self.query_one("#project-table", DataTable)
        table.clear(columns=True)
        table.cursor_type = "row"

        table.add_columns("", "Name", "Type", "Last Edited", "Badges")

        filtered = self._projects
        if self._filter != "All":
            filtered = [p for p in self._projects if p.project_type == self._filter]

        search_val = self.query_one("#search-input", Input).value.strip().lower()
        if search_val:
            filtered = [
                p for p in filtered
                if search_val in p.name.lower() or search_val in p.readme_content.lower()
            ]

        for p in filtered:
            icon = ICONS.get(p.project_type, ICONS["Unknown"])
            badges = []
            if p.is_git_repo:
                badges.append("GIT")
            if p.has_github:
                badges.append("GITHUB")
            if p.is_claude_made:
                badges.append("CLAUDE")
            if not p.is_git_repo:
                badges.append("LOCAL")

            last_edit = datetime.fromtimestamp(p.last_modified).strftime("%b %d, %Y") if p.last_modified else "Unknown"

            table.add_row(
                icon,
                p.name,
                p.project_type,
                last_edit,
                " ".join(f"[{b}]" for b in badges),
                key=p.name,
            )

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search-input":
            self._refresh_table()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id and event.button.id.startswith("filter-"):
            filter_type = event.button.id.replace("filter-", "").capitalize()
            if filter_type == "All":
                self._filter = "All"
            else:
                # Match exact type name
                type_map = {"Python": "Python", "Node": "Node", "Bash": "Bash", "Rust": "Rust", "Go": "Go", "Static": "Static"}
                self._filter = type_map.get(filter_type, "All")

            # Update button styles
            for btn in self.query(".filter-btn"):
                btn.remove_class("active")
            event.button.add_class("active")

            self._refresh_table()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        key = event.row_key
        if key is not None:
            project = next((p for p in self._projects if p.name == key.value), None)
            if project:
                self.app.push_screen(ProjectDetailScreen(project))

    def action_focus_search(self) -> None:
        self.query_one("#search-input", Input).focus()

    def action_run_project(self) -> None:
        table = self.query_one("#project-table", DataTable)
        row_key = table.cursor_row
        if row_key is not None and row_key < len(self._projects):
            project = self._get_selected_project()
            if project:
                self.app.push_screen(ProjectDetailScreen(project))

    def _get_selected_project(self) -> ProjectInfo | None:
        table = self.query_one("#project-table", DataTable)
        if table.cursor_row is not None:
            try:
                row_key = table.get_row_at(table.cursor_row)
                name = row_key[1]  # Name is second column
                return next((p for p in self._projects if p.name == name), None)
            except Exception:
                return None
        return None

    def action_open_web(self) -> None:
        config = get_config()
        port = config.get("web", {}).get("port", 8080)
        self.notify(f"Starting web dashboard on port {port}...", title="CodeQuest")

        def start_web():
            from codequest.web.server import run_server
            run_server(port=port)

        thread = threading.Thread(target=start_web, daemon=True)
        thread.start()

        if config.get("web", {}).get("auto_open_browser", True):
            webbrowser.open(f"http://localhost:{port}")

    def action_open_settings(self) -> None:
        self.app.push_screen(SettingsScreen())

    def action_rescan(self) -> None:
        self.notify("Rescanning projects...", title="CodeQuest")
        self.run_worker(self._do_rescan())

    async def _do_rescan(self) -> None:
        projects = scan_all()
        save_index(projects)
        self._projects = projects
        self._refresh_table()
        self.notify(f"Found {len(projects)} projects", title="CodeQuest")

    def action_show_help(self) -> None:
        self.app.push_screen(HelpPanel())

    def action_quit(self) -> None:
        self.app.exit()


class CodeQuestApp(App):
    """CodeQuest - Your Project Command Center."""

    TITLE = "CodeQuest"
    SUB_TITLE = "Project Command Center"
    CSS_PATH = "themes/retro.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True, priority=True),
    ]

    def on_mount(self) -> None:
        config = get_config()
        if not config.get("first_run_complete", False):
            self.push_screen(WelcomeScreen())
        else:
            self.push_screen(DashboardScreen())


def run_tui() -> None:
    """Launch the CodeQuest TUI application."""
    app = CodeQuestApp()
    app.run()
