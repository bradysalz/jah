import asyncio
import io
from pathlib import Path

from rich.console import Console

from jah.app import TicketTui


def write_ticket(
    directory: Path,
    ticket_id: str,
    title: str,
    parent=None,
    ticket_type="task",
    priority="normal",
    status="todo",
) -> None:
    (directory / f"{ticket_id}.md").write_text(
        "\n".join(
            [
                "---",
                f"id: {ticket_id}",
                f"title: {title}",
                f"status: {status}",
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
    assert ">> v [epic] [P0] [T] Root" in rendered
    assert "[child]" not in rendered


def test_ticket_type_labels_use_short_forms(tmp_path: Path) -> None:
    write_ticket(tmp_path, "mile", "Milestone", ticket_type="milestone")
    write_ticket(tmp_path, "feat", "Feature", ticket_type="feature")

    app = TicketTui(tmp_path)
    rendered = render_plain(app._render_tree())

    assert "[mile]" in rendered
    assert "[feat]" in rendered
    assert "[milestone]" not in rendered
    assert "[feature]" not in rendered


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


def test_status_modal_filters_tree_rows(tmp_path: Path) -> None:
    write_ticket(tmp_path, "root", "Root", ticket_type="epic")
    write_ticket(tmp_path, "active", "Active", parent="root", status="in-progress")
    write_ticket(tmp_path, "done", "Done", parent="root", status="completed")

    async def run() -> None:
        app = TicketTui(tmp_path)
        async with app.run_test() as pilot:
            await pilot.press("s")
            await pilot.press("2")
            await pilot.press("4")
            await pilot.press("5")
            rendered = render_plain(app._render_tree())
            assert "Active" in rendered
            assert "Done" not in rendered

    asyncio.run(run())


def test_narrow_layout_requires_enter_for_detail(tmp_path: Path) -> None:
    write_ticket(tmp_path, "one", "One")

    async def run() -> None:
        app = TicketTui(tmp_path)
        async with app.run_test(size=(100, 24)) as pilot:
            assert "press enter to show" in render_plain(pilot.app.query_one("#detail").renderable)
            await pilot.press("enter")
            assert "Title: One" in render_plain(pilot.app.screen.query_one("#detail-modal").renderable)

    asyncio.run(run())


def test_wide_layout_opens_scrollable_detail_modal(tmp_path: Path) -> None:
    write_ticket(tmp_path, "one", "One")

    async def run() -> None:
        app = TicketTui(tmp_path)
        async with app.run_test(size=(140, 24)) as pilot:
            assert "Open with Enter for scrollable detail." in render_plain(pilot.app.query_one("#detail").renderable)
            await pilot.press("enter")
            assert "Title: One" in render_plain(pilot.app.screen.query_one("#detail-modal").renderable)

    asyncio.run(run())


def test_kanban_shows_no_side_preview(tmp_path: Path) -> None:
    write_ticket(tmp_path, "one", "One")

    async def run() -> None:
        app = TicketTui(tmp_path)
        async with app.run_test(size=(140, 24)) as pilot:
            await pilot.press("tab")
            detail = pilot.app.query_one("#detail")
            assert render_plain(detail.renderable).strip() == ""
            assert str(detail.styles.display) == "none"

    asyncio.run(run())


def test_selection_scrolls_main_pane_for_long_tree(tmp_path: Path) -> None:
    for index in range(40):
        write_ticket(tmp_path, f"ticket-{index:02d}", f"Ticket {index:02d}")

    async def run() -> None:
        app = TicketTui(tmp_path)
        async with app.run_test(size=(120, 12)) as pilot:
            for _ in range(20):
                await pilot.press("down")
            assert pilot.app.query_one("#main").scroll_y > 0

    asyncio.run(run())


def test_kanban_selection_skips_empty_columns(tmp_path: Path) -> None:
    write_ticket(tmp_path, "todo", "Todo", status="todo")
    write_ticket(tmp_path, "done", "Done", status="completed")

    async def run() -> None:
        app = TicketTui(tmp_path)
        async with app.run_test(size=(140, 24)) as pilot:
            await pilot.press("down")
            await pilot.press("tab")
            assert app.selected_ticket_id() == "todo"
            await pilot.press("right")
            assert app.selected_ticket_id() == "done"
            await pilot.press("left")
            assert app.selected_ticket_id() == "todo"

    asyncio.run(run())


def render_plain(renderable) -> str:
    console = Console(width=120, color_system=None, record=True, file=io.StringIO())
    console.print(renderable)
    return console.export_text()
