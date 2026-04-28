from pathlib import Path

from jah.models import kanban_columns, tree_rows
from jah.parser import load_graph


def write_ticket(
    directory: Path,
    ticket_id: str,
    title: str,
    status: str = "todo",
    parent=None,
    priority=None,
    tags=None,
    created_at=None,
    body="",
) -> None:
    lines = ["---", f"id: {ticket_id}", f"title: {title}", f"status: {status}"]
    if parent is None:
        lines.append("parent:")
    else:
        lines.append(f"parent: {parent}")
    if priority:
        lines.append(f"priority: {priority}")
    if tags:
        lines.append("tags: [" + ", ".join(tags) + "]")
    if created_at:
        lines.append(f"created_at: {created_at}")
    lines.extend(["---", body])
    (directory / f"{ticket_id}.md").write_text("\n".join(lines), encoding="utf-8")


def test_loads_tree_and_treats_missing_parent_as_root(tmp_path: Path) -> None:
    write_ticket(tmp_path, "root", "Root")
    write_ticket(tmp_path, "child", "Child", parent="root")
    write_ticket(tmp_path, "orphan", "Orphan", parent="missing")

    graph = load_graph(tmp_path)

    assert graph.roots == ("orphan", "root")
    assert graph.children["root"] == ("child",)


def test_loads_beans_comment_id_and_matches_parent_references(tmp_path: Path) -> None:
    (tmp_path / "project-root--root-ticket.md").write_text(
        "\n".join(
            [
                "---",
                "# project-root",
                "title: Root",
                "status: todo",
                "type: milestone",
                "---",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "project-child--child-ticket.md").write_text(
        "\n".join(
            [
                "---",
                "# project-child",
                "title: Child",
                "status: todo",
                "type: task",
                "parent: project-root",
                "---",
                "",
            ]
        ),
        encoding="utf-8",
    )

    graph = load_graph(tmp_path)

    assert graph.roots == ("project-root",)
    assert graph.children["project-root"] == ("project-child",)


def test_filename_id_fallback_strips_slug(tmp_path: Path) -> None:
    (tmp_path / "project-root--root-ticket.md").write_text(
        "\n".join(["---", "title: Root", "status: todo", "---", ""]),
        encoding="utf-8",
    )

    graph = load_graph(tmp_path)

    assert set(graph.tickets) == {"project-root"}


def test_unknown_status_is_dropped(tmp_path: Path) -> None:
    write_ticket(tmp_path, "good", "Good")
    write_ticket(tmp_path, "bad", "Bad", status="blocked")

    graph = load_graph(tmp_path)

    assert set(graph.tickets) == {"good"}


def test_cycles_are_omitted(tmp_path: Path) -> None:
    write_ticket(tmp_path, "a", "A", parent="b")
    write_ticket(tmp_path, "b", "B", parent="a")
    write_ticket(tmp_path, "c", "C")

    graph = load_graph(tmp_path)

    assert set(graph.tickets) == {"c"}
    assert graph.roots == ("c",)


def test_kanban_includes_only_leaf_nodes_and_maps_statuses(tmp_path: Path) -> None:
    write_ticket(tmp_path, "root", "Root", status="in-progress")
    write_ticket(tmp_path, "todo", "Todo", status="draft", parent="root")
    write_ticket(tmp_path, "done", "Done", status="scrapped")

    graph = load_graph(tmp_path)
    columns = kanban_columns(graph)

    assert columns["DRAFT"] == ["todo"]
    assert columns["TODO"] == []
    assert columns["WIP"] == []
    assert columns["DONE"] == ["done"]


def test_kanban_sorts_by_priority_then_created_at(tmp_path: Path) -> None:
    write_ticket(tmp_path, "normal", "Normal", priority="normal", created_at="2024-01-01T00:00:00Z")
    write_ticket(tmp_path, "new_high", "New High", priority="high", created_at="2024-02-01T00:00:00Z")
    write_ticket(tmp_path, "old_high", "Old High", priority="high", created_at="2024-01-01T00:00:00Z")

    graph = load_graph(tmp_path)
    columns = kanban_columns(graph)

    assert columns["TODO"] == ["old_high", "new_high", "normal"]


def test_search_matches_title_tags_and_body(tmp_path: Path) -> None:
    write_ticket(tmp_path, "title", "Deploy docs")
    write_ticket(tmp_path, "tag", "Other", tags=["release"])
    write_ticket(tmp_path, "body", "Other", body="contains migrations")

    graph = load_graph(tmp_path)

    assert kanban_columns(graph, query="deploy")["TODO"] == ["title"]
    assert kanban_columns(graph, query="release")["TODO"] == ["tag"]
    assert kanban_columns(graph, query="migrations")["TODO"] == ["body"]


def test_tree_search_includes_ancestors(tmp_path: Path) -> None:
    write_ticket(tmp_path, "root", "Root")
    write_ticket(tmp_path, "child", "Needle", parent="root")

    graph = load_graph(tmp_path)
    rows = tree_rows(graph, query="needle")

    assert [row[0] for row in rows] == ["root", "child"]


def test_tree_hide_done_keeps_done_connectors_with_active_children(tmp_path: Path) -> None:
    write_ticket(tmp_path, "root", "Root", status="completed")
    write_ticket(tmp_path, "active", "Active", status="in-progress", parent="root")
    write_ticket(tmp_path, "done_leaf", "Done Leaf", status="completed", parent="root")

    graph = load_graph(tmp_path)
    rows = tree_rows(graph, hide_done=True)

    assert [row[0] for row in rows] == ["root", "active"]


def test_hide_done_filters_done_kanban_cards(tmp_path: Path) -> None:
    write_ticket(tmp_path, "todo", "Todo")
    write_ticket(tmp_path, "done", "Done", status="completed")

    graph = load_graph(tmp_path)
    columns = kanban_columns(graph, hide_done=True)

    assert columns["TODO"] == ["todo"]
    assert columns["DONE"] == []


def test_tree_status_filter_keeps_matching_nodes_and_ancestors(tmp_path: Path) -> None:
    write_ticket(tmp_path, "root", "Root", status="todo")
    write_ticket(tmp_path, "active", "Active", status="in-progress", parent="root")
    write_ticket(tmp_path, "done", "Done", status="completed", parent="root")

    graph = load_graph(tmp_path)
    rows = tree_rows(graph, visible_statuses={"in-progress"})

    assert [row[0] for row in rows] == ["root", "active"]


def test_kanban_status_filter_limits_visible_cards(tmp_path: Path) -> None:
    write_ticket(tmp_path, "todo", "Todo", status="todo")
    write_ticket(tmp_path, "wip", "Wip", status="in-progress")
    write_ticket(tmp_path, "done", "Done", status="completed")

    graph = load_graph(tmp_path)
    columns = kanban_columns(graph, visible_statuses={"in-progress", "completed"})

    assert columns["TODO"] == []
    assert columns["WIP"] == ["wip"]
    assert columns["DONE"] == ["done"]
