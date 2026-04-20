import asyncio
import io
from pathlib import Path

from rich.console import Console

from jah.app import TicketTui


def write_ticket(directory: Path, ticket_id: str, title: str, parent=None, ticket_type="task", priority="normal") -> None:
    (directory / f"{ticket_id}.md").write_text(
        "\n".join(
            [
                "---",
                f"id: {ticket_id}",
                f"title: {title}",
                "status: todo",
                f"parent: {parent}" if parent else "parent:",
                f"type: {ticket_type}",
                f"priority: {priority}",
                "---",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_textual_app_mounts(tmp_path: Path) -> None:
    write_ticket(tmp_path, "one", "One")

    async def run() -> None:
        app = TicketTui(tmp_path)
        async with app.run_test() as pilot:
            assert "TREE" in render_plain(pilot.app.query_one("#main").renderable)

    asyncio.run(run())


def test_tree_render_uses_branch_indentation_and_task_chips(tmp_path: Path) -> None:
    write_ticket(tmp_path, "root", "Root", ticket_type="epic", priority="high")
    write_ticket(tmp_path, "child", "Child", parent="root", ticket_type="bug", priority="low")

    app = TicketTui(tmp_path)
    rendered = render_plain(app._render_tree())

    assert "└────- [bug] [P2] [T] Child" in rendered
    assert "[epic] [P0] [T] Root" in rendered
    assert "[child]" not in rendered


def test_help_modal_opens(tmp_path: Path) -> None:
    write_ticket(tmp_path, "one", "One")

    async def run() -> None:
        app = TicketTui(tmp_path)
        async with app.run_test() as pilot:
            await pilot.press("?")
            assert "Keyboard Shortcuts" in render_plain(pilot.app.screen.query_one("#help").renderable)

    asyncio.run(run())


def test_columns_modal_toggles_kanban_columns(tmp_path: Path) -> None:
    write_ticket(tmp_path, "one", "One")

    async def run() -> None:
        app = TicketTui(tmp_path)
        async with app.run_test() as pilot:
            await pilot.press("c")
            assert "Kanban Columns" in render_plain(pilot.app.screen.query_one("#columns").renderable)
            await pilot.press("4")
            assert "DONE" not in app.visible_kanban_columns

    asyncio.run(run())


def render_plain(renderable) -> str:
    console = Console(width=120, color_system=None, record=True, file=io.StringIO())
    console.print(renderable)
    return console.export_text()
