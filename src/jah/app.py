from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Set

from rich.console import Group
from rich.table import Table
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.css.query import NoMatches
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Input, Static

from jah.models import KANBAN_COLUMNS, Ticket, TicketGraph, all_expanded_ids, kanban_columns, tree_rows
from jah.parser import load_graph


TYPE_STYLES = {
    "bug": "bold red",
    "feature": "bold green",
    "task": "bold cyan",
    "chore": "bold blue",
    "epic": "bold magenta",
    "story": "bold green",
}
PRIORITY_STYLES = {
    "high": "bold red",
    "normal": "yellow",
    "low": "dim green",
}
STATUS_STYLES = {
    "todo": "bright_blue",
    "draft": "dim bright_blue",
    "in-progress": "bold yellow",
    "completed": "bold green",
    "scrapped": "dim red",
}
STATUS_SHORT = {
    "todo": "T",
    "draft": "D",
    "in-progress": "W",
    "completed": "C",
    "scrapped": "S",
}
PRIORITY_SHORT = {
    "high": "P0",
    "normal": "P1",
    "low": "P2",
}


class HelpModal(ModalScreen[None]):
    CSS = """
    HelpModal {
        align: center middle;
    }

    #help {
        width: 72;
        height: auto;
        max-height: 90%;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close", show=False),
        Binding("question_mark", "dismiss", "Close", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield Static(_help_text(), id="help")

    def action_dismiss(self) -> None:
        self.dismiss()


class ColumnsModal(ModalScreen[None]):
    CSS = """
    ColumnsModal {
        align: center middle;
    }

    #columns {
        width: 56;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    """

    BINDINGS = [
        Binding("1", "toggle_column('DRAFT')", "Draft", show=False),
        Binding("2", "toggle_column('TODO')", "Todo", show=False),
        Binding("3", "toggle_column('WIP')", "Wip", show=False),
        Binding("4", "toggle_column('DONE')", "Done", show=False),
        Binding("escape", "dismiss", "Close", show=False),
        Binding("c", "dismiss", "Close", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield Static(self._render_columns(), id="columns")

    def action_toggle_column(self, column: str) -> None:
        app = self.app
        if column in app.visible_kanban_columns and len(app.visible_kanban_columns) > 1:
            app.visible_kanban_columns.remove(column)
        else:
            app.visible_kanban_columns.add(column)
        app._clamp_selection()
        app.render_all()
        self.query_one("#columns", Static).update(self._render_columns())

    def action_dismiss(self) -> None:
        self.dismiss()

    def _render_columns(self) -> Text:
        text = Text()
        text.append("Kanban Columns\n\n", style="bold")
        text.append("Toggle columns with 1-4. Esc closes.\n\n", style="dim")
        for index, column in enumerate(KANBAN_COLUMNS, start=1):
            enabled = column in self.app.visible_kanban_columns
            text.append(f"{index} ", style="bold cyan")
            text.append("[x] " if enabled else "[ ] ", style="green" if enabled else "dim")
            text.append(column + "\n", style="bold" if enabled else "dim")
        return text


class TicketTui(App):
    CSS = """
    Screen {
        layout: vertical;
    }

    #search {
        dock: top;
        height: 3;
    }

    #body {
        height: 1fr;
    }

    #main {
        width: 62%;
        border: solid $primary;
        padding: 0 1;
    }

    #detail {
        width: 38%;
        border: solid $secondary;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("tab", "toggle_view", "View", show=True, priority=True),
        Binding("/", "focus_search", "Search", show=True),
        Binding("escape", "clear_search", "Clear", show=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("d", "toggle_done", "Done", show=True),
        Binding("y", "copy_id", "Copy ID", show=True),
        Binding("e", "edit_ticket", "Edit", show=True),
        Binding("c", "columns", "Columns", show=True),
        Binding("question_mark", "help", "Help", show=True, priority=True),
        Binding("enter", "open_detail", "Detail", show=True),
        Binding("up", "move_up", "Up", show=False),
        Binding("down", "move_down", "Down", show=False),
        Binding("left", "move_left", "Left", show=False),
        Binding("right", "move_right", "Right", show=False),
        Binding("space", "toggle_tree_node", "Toggle", show=False),
    ]

    def __init__(self, ticket_dir: Path) -> None:
        super().__init__()
        self.ticket_dir = ticket_dir
        self.graph: TicketGraph = load_graph(ticket_dir)
        self.mode = "tree"
        self.hide_done = False
        self.query = ""
        self.expanded_ids: Set[str] = all_expanded_ids(self.graph)
        self.tree_index = 0
        self.kanban_column = 0
        self.kanban_index = 0
        self.visible_kanban_columns: Set[str] = set(KANBAN_COLUMNS)
        self.detail_id: Optional[str] = None
        self.status_message = ""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Input(placeholder="Search", id="search")
        with Horizontal(id="body"):
            main = Static(id="main")
            main.can_focus = True
            yield main
            yield Static(id="detail")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#search", Input).value = self.query
        self.query_one("#main", Static).focus()
        self.render_all()

    def on_key(self, event: Key) -> None:
        if event.key == "question_mark":
            event.prevent_default()
            event.stop()
            self.action_help()

    def on_input_changed(self, event: Input.Changed) -> None:
        self.query = event.value
        self._clamp_selection()
        self.render_all()

    def action_toggle_view(self) -> None:
        selected = self.selected_ticket_id()
        self.mode = "kanban" if self.mode == "tree" else "tree"
        if selected:
            self._select_ticket(selected)
        else:
            self._clamp_selection()
        self.render_all()

    def action_focus_search(self) -> None:
        self.query_one("#search", Input).focus()

    def action_clear_search(self) -> None:
        self.query = ""
        search = self.query_one("#search", Input)
        search.value = ""
        self.screen.set_focus(None)
        self._clamp_selection()
        self.render_all()

    def action_refresh(self) -> None:
        selected = self.selected_ticket_id()
        self.graph = load_graph(self.ticket_dir)
        self.expanded_ids = all_expanded_ids(self.graph)
        if selected in self.graph.tickets:
            self._select_ticket(selected)
        else:
            self._clamp_selection()
        self.status_message = "Reloaded"
        self.render_all()

    def action_toggle_done(self) -> None:
        self.hide_done = not self.hide_done
        self._clamp_selection()
        self.render_all()

    def action_copy_id(self) -> None:
        ticket_id = self.selected_ticket_id()
        if not ticket_id:
            return
        try:
            import pyperclip

            pyperclip.copy(ticket_id)
            self.status_message = "Copied " + ticket_id
        except Exception:
            self.status_message = "Clipboard unavailable"
        self.render_all()

    def action_edit_ticket(self) -> None:
        ticket_id = self.selected_ticket_id()
        if not ticket_id:
            return
        editor = os.environ.get("EDITOR")
        if not editor:
            self.status_message = "$EDITOR is not set"
            self.render_all()
            return

        command = shlex.split(editor) + [str(self.graph.ticket(ticket_id).path)]
        try:
            with self.suspend():
                subprocess.run(command, check=False)
            self.status_message = "Returned from editor; press r to refresh"
        except Exception as exc:
            self.status_message = "Editor failed: " + str(exc)
        self.render_all()

    def action_help(self) -> None:
        self.push_screen(HelpModal())

    def action_columns(self) -> None:
        self.push_screen(ColumnsModal())

    def action_open_detail(self) -> None:
        self.detail_id = self.selected_ticket_id()
        self.render_all()

    def action_move_up(self) -> None:
        if self.mode == "tree":
            self.tree_index = max(0, self.tree_index - 1)
        else:
            self.kanban_index = max(0, self.kanban_index - 1)
        self.render_all()

    def action_move_down(self) -> None:
        if self.mode == "tree":
            self.tree_index = min(max(0, len(self._tree_rows()) - 1), self.tree_index + 1)
        else:
            count = len(self._current_kanban_column())
            self.kanban_index = min(max(0, count - 1), self.kanban_index + 1)
        self.render_all()

    def action_move_left(self) -> None:
        if self.mode == "tree":
            ticket_id = self.selected_ticket_id()
            if ticket_id and ticket_id in self.expanded_ids:
                self.expanded_ids.remove(ticket_id)
        else:
            self.kanban_column = max(0, self.kanban_column - 1)
            self._clamp_selection()
        self.render_all()

    def action_move_right(self) -> None:
        if self.mode == "tree":
            ticket_id = self.selected_ticket_id()
            if ticket_id and self.graph.children.get(ticket_id):
                self.expanded_ids.add(ticket_id)
        else:
            self.kanban_column = min(len(self._visible_kanban_columns()) - 1, self.kanban_column + 1)
            self._clamp_selection()
        self.render_all()

    def action_toggle_tree_node(self) -> None:
        if self.mode != "tree":
            return
        ticket_id = self.selected_ticket_id()
        if not ticket_id or not self.graph.children.get(ticket_id):
            return
        if ticket_id in self.expanded_ids:
            self.expanded_ids.remove(ticket_id)
        else:
            self.expanded_ids.add(ticket_id)
        self.render_all()

    def selected_ticket_id(self) -> Optional[str]:
        if self.mode == "tree":
            rows = self._tree_rows()
            if not rows:
                return None
            return rows[self.tree_index][0]

        column = self._current_kanban_column()
        if not column:
            return None
        return column[self.kanban_index]

    def render_all(self) -> None:
        main, detail = self._content_widgets()
        main.update(self._render_main())
        detail.update(self._render_detail())

    def _content_widgets(self):
        try:
            return self.query_one("#main", Static), self.query_one("#detail", Static)
        except NoMatches:
            pass

        for screen in reversed(self.screen_stack):
            try:
                return screen.query_one("#main", Static), screen.query_one("#detail", Static)
            except NoMatches:
                continue
        raise NoMatches("No ticket content widgets are mounted")

    def _render_main(self):
        self._clamp_selection()
        heading = Text(self.mode.upper(), style="bold")
        if self.hide_done:
            heading.append(" | hide done", style="yellow")
        if self.query:
            heading.append(" | search: ", style="dim")
            heading.append(self.query, style="bold cyan")
        if self.status_message:
            heading.append(" | ", style="dim")
            heading.append(self.status_message, style="green")

        if self.mode == "tree":
            body = self._render_tree()
        else:
            body = self._render_kanban()
        return Group(heading, Text(""), body)

    def _render_tree(self):
        rows = self._tree_rows()
        if not rows:
            return "No results"

        lines: List[Text] = []
        for index, (ticket_id, depth, has_children, expanded) in enumerate(rows):
            ticket = self.graph.ticket(ticket_id)
            line = Text()
            selected = ">" if index == self.tree_index else " "
            line.append(selected + " ", style="reverse" if index == self.tree_index else "")
            line.append(self._tree_prefix(rows, index), style="dim")
            if has_children:
                marker = "v" if expanded else ">"
            else:
                marker = "-"
            line.append(marker + " ", style="bold")
            line.append(_ticket_label(ticket))
            lines.append(line)
        return Group(*lines)

    def _render_kanban(self):
        columns = self._kanban_columns()
        visible_columns = self._visible_kanban_columns()
        visible_max_rows = max((len(columns[column]) for column in visible_columns), default=0)
        if visible_max_rows == 0:
            return "No results"

        table = Table.grid(expand=True)
        for _column in visible_columns:
            table.add_column(ratio=1)
        table.add_row(
            *[Text(column, style="bold underline", justify="center") for column in visible_columns]
        )

        for row_index in range(visible_max_rows):
            cells: List[Text] = []
            for column_index, column in enumerate(visible_columns):
                ids = columns[column]
                if row_index >= len(ids):
                    cells.append(Text(""))
                    continue
                ticket = self.graph.ticket(ids[row_index])
                cell = Text("> " if column_index == self.kanban_column and row_index == self.kanban_index else "  ")
                cell.append(_ticket_label(ticket))
                cells.append(cell)
            table.add_row(*cells)
        return table

    def _render_detail(self):
        ticket_id = self.detail_id or self.selected_ticket_id()
        if not ticket_id or ticket_id not in self.graph.tickets:
            return "DETAIL\n\nNo ticket selected"

        ticket = self.graph.ticket(ticket_id)
        lines: List[Text] = [Text("DETAIL", style="bold"), Text("")]
        lines.append(_metadata_line("ID", ticket.id, "bold cyan"))
        lines.append(_metadata_line("Title", ticket.title, "bold"))
        lines.append(_metadata_line("Status", ticket.status, STATUS_STYLES.get(ticket.status, "")))
        if ticket.parent:
            lines.append(_metadata_line("Parent", ticket.parent, "cyan"))
        if ticket.type:
            lines.append(_metadata_line("Type", ticket.type, _type_style(ticket)))
        if ticket.priority:
            lines.append(_metadata_line("Priority", ticket.priority, _priority_style(ticket)))
        if ticket.tags:
            lines.append(_metadata_line("Tags", ", ".join(ticket.tags), "magenta"))
        if ticket.created_at:
            lines.append(_metadata_line("Created", ticket.created_at, "dim"))
        if ticket.updated_at:
            lines.append(_metadata_line("Updated", ticket.updated_at, "dim"))
        lines.extend([Text(""), Text(ticket.body or "(no body)")])
        return Group(*lines)

    def _tree_rows(self):
        return tree_rows(self.graph, self.query, self.hide_done, self.expanded_ids)

    def _kanban_columns(self) -> Dict[str, List[str]]:
        return kanban_columns(self.graph, self.query, self.hide_done)

    def _current_kanban_column(self) -> List[str]:
        return self._kanban_columns()[self._visible_kanban_columns()[self.kanban_column]]

    def _visible_kanban_columns(self) -> List[str]:
        columns = [column for column in KANBAN_COLUMNS if column in self.visible_kanban_columns]
        return columns or [KANBAN_COLUMNS[0]]

    def _clamp_selection(self) -> None:
        rows = self._tree_rows()
        self.tree_index = min(self.tree_index, max(0, len(rows) - 1))

        self.kanban_column = min(max(0, self.kanban_column), len(self._visible_kanban_columns()) - 1)
        current = self._current_kanban_column()
        self.kanban_index = min(self.kanban_index, max(0, len(current) - 1))

    def _select_ticket(self, ticket_id: str) -> None:
        rows = self._tree_rows()
        for index, row in enumerate(rows):
            if row[0] == ticket_id:
                self.tree_index = index
                break

        columns = self._kanban_columns()
        for column_index, column in enumerate(self._visible_kanban_columns()):
            if ticket_id in columns[column]:
                self.kanban_column = column_index
                self.kanban_index = columns[column].index(ticket_id)
                break

    def _tree_prefix(self, rows, index: int) -> str:
        _ticket_id, depth, _has_children, _expanded = rows[index]
        if depth <= 0:
            return ""

        parts: List[str] = []
        for ancestor_depth in range(depth):
            if ancestor_depth == depth - 1:
                parts.append("└────" if self._is_last_at_depth(rows, index, depth) else "├────")
            else:
                parts.append("     " if self._ancestor_is_last(rows, index, ancestor_depth) else "│    ")
        return "".join(parts)

    def _is_last_at_depth(self, rows, index: int, depth: int) -> bool:
        for later_id, later_depth, _has_children, _expanded in rows[index + 1 :]:
            if later_depth < depth:
                return True
            if later_depth == depth:
                return False
        return True

    def _ancestor_is_last(self, rows, index: int, ancestor_depth: int) -> bool:
        for prior_index in range(index - 1, -1, -1):
            if rows[prior_index][1] == ancestor_depth:
                return self._is_last_at_depth(rows, prior_index, ancestor_depth)
        return True


def _ticket_label(ticket: Ticket) -> Text:
    text = Text()
    _chip(text, ticket.type or "task", _type_style(ticket))
    _chip(text, PRIORITY_SHORT.get((ticket.priority or "normal").lower(), "P1"), _priority_style(ticket))
    _chip(text, STATUS_SHORT.get(ticket.status, "?"), STATUS_STYLES.get(ticket.status, ""))
    text.append(ticket.title, style="white")
    return text


def _chip(text: Text, value: str, style: str) -> None:
    text.append("[", style="dim")
    text.append(value, style=style)
    text.append("] ", style="dim")


def _type_style(ticket: Ticket) -> str:
    ticket_type = (ticket.type or "task").lower()
    return TYPE_STYLES.get(ticket_type, "bold white")


def _priority_style(ticket: Ticket) -> str:
    priority = (ticket.priority or "normal").lower()
    return PRIORITY_STYLES.get(priority, "yellow")


def _metadata_line(label: str, value: str, value_style: str) -> Text:
    text = Text()
    text.append(label + ": ", style="bold")
    text.append(value, style=value_style)
    return text


def _help_text() -> Text:
    text = Text()
    text.append("Keyboard Shortcuts\n\n", style="bold")
    rows = [
        ("tab", "toggle Tree / Kanban"),
        ("/", "focus search"),
        ("Esc", "clear search or close help"),
        ("?", "open / close this help"),
        ("r", "refresh tickets"),
        ("d", "toggle hide done"),
        ("c", "choose visible kanban columns"),
        ("y", "copy selected ticket ID"),
        ("e", "edit selected ticket in $EDITOR"),
        ("Enter", "show selected ticket detail"),
        ("Up / Down", "move selection"),
        ("Left / Right", "collapse/expand tree or move kanban columns"),
        ("Space", "toggle selected tree subtree"),
    ]
    for key, description in rows:
        text.append(key.rjust(12), style="bold cyan")
        text.append("  ")
        text.append(description)
        text.append("\n")
    return text
