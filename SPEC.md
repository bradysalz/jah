
## PRD: TUI App for Markdown Ticket Visualization (Kanban + Tree)

---

## 1) Overview

A terminal-based application built with Textualize to visualize a collection of markdown ticket files (with frontmatter) in two views:

* **Tree view** (hierarchical via `parent`)
* **Kanban view** (flat, leaf-only)

The app is **read + navigate + inspect + edit (via `$EDITOR`)**, not a full task manager.

Target scale: **< 1,000 tickets**

---

## 2) Goals

* Fast navigation of a markdown-based task system
* Clear visualization of hierarchy (tree) and execution state (kanban)
* Minimal friction editing via external editor
* Keyboard-first interaction

---

## 3) Non-Goals

* Task creation or deletion
* Drag-and-drop or mouse-first UX
* Reordering or reparenting
* File watching / live sync
* Multi-user or collaboration
* Custom workflows or arbitrary columns
* Full markdown rendering

---

## 4) Data Model

### File Structure

* Flat directory of markdown files
* One ticket per file
* Filename = `<id>.md`

### Frontmatter Schema (Beans-compatible)

Required:

```yaml
id: string
title: string
status: todo|draft|in-progress|completed|scrapped
parent: string|null
```

Optional:

```yaml
type: string
priority: low|normal|high
tags: [string]
created_at: ISO8601
updated_at: ISO8601
```

---

## 5) Parsing Rules

* Files are parsed via YAML frontmatter
* Input is assumed clean, but:

Handling:

* Unknown `status` → **ticket dropped**
* Missing `parent` → treated as root
* Missing parent reference → treated as root
* Cycles → affected nodes omitted
* Duplicate IDs → undefined behavior (not supported)

---

## 6) Derived Structures

### Tree

* Built from `parent` field
* Multiple roots allowed

### Kanban

* Includes **leaf nodes only**
* Leaf = no children

---

## 7) Status Mapping

| Schema Status | Kanban Column |
| ------------- | ------------- |
| todo          | TODO          |
| draft         | TODO          |
| in-progress   | WIP           |
| completed     | DONE          |
| scrapped      | DONE          |

All other statuses are ignored (ticket excluded).

---

## 8) Views

### 8.1 Tree View

Displays full hierarchy.

#### Behavior

* Default: **fully expanded**
* `space`: toggle subtree (collapse/expand)
* Arrow keys:

  * ↑ / ↓ → move selection
  * → expand node
  * ← collapse node

#### Done Filter

When “hide done” is enabled:

* Hide done leaf nodes
* Hide done subtrees with no active descendants
* Show done nodes **if required to connect visible children to root**

---

### 8.2 Kanban View

Displays tickets in 3 columns:

* TODO
* WIP
* DONE

#### Inclusion

* Leaf nodes only

#### Sorting (within column)

1. `priority` (high → low)
2. `created_at` (oldest first)

#### Navigation

* ↑ / ↓ → move within column
* ← / → → move across columns

---

### 8.3 Detail Pane

Persistent right-hand panel.

#### Trigger

* `Enter` on selected ticket

#### Displays:

* ID
* Title
* Key metadata (status, tags, etc.)
* Body (raw or minimally formatted markdown)

---

## 9) Search

### Scope

* title
* tags
* body

### Behavior

* Case-insensitive substring match
* Live filtering

### Interaction

* `/` → enter search
* typing updates results live
* `Esc` → clear search

### View Behavior

**Tree:**

* Show matching nodes
* Include ancestors to preserve structure

**Kanban:**

* Show only matching leaf tickets

---

## 10) Keyboard Controls

### Global

* `tab` → toggle Tree / Kanban
* `/` → search
* `Esc` → clear search
* `r` → refresh
* `d` → toggle show/hide done
* `y` → copy ticket ID
* `e` → edit ticket in `$EDITOR`
* `Enter` → open in detail pane

### Tree

* ↑ / ↓ → navigate
* → → expand
* ← → collapse
* `space` → toggle subtree

### Kanban

* ↑ / ↓ → navigate within column
* ← / → → move across columns

---

## 11) Editing

* `e` opens selected ticket in system `$EDITOR`
* File is edited externally
* On return:

  * user must manually refresh (`r`)
* No inline editing

---

## 12) Refresh

Triggered via `r`.

### Behavior:

* Reload all files
* Re-parse frontmatter
* Rebuild tree + kanban structures

### State Preservation:

* search query preserved
* done filter preserved
* selection preserved if ID still exists
* expansion state **not preserved**

---

## 13) Empty States

* No tickets → display `"No results"`
* Search yields no matches → `"No results"`
* Empty kanban column → column shown empty

---

## 14) Performance Constraints

* Optimized for ≤ 1,000 tickets
* No virtualization required in v1
* Full reload on refresh acceptable

---

## 15) Clipboard

* `y` copies ticket ID to system clipboard
* If clipboard unavailable → no-op or status message

---

## 16) UI Layout

Two-pane layout:

```
+----------------------+----------------------+
|                      |                      |
|   Tree / Kanban      |   Detail Pane        |
|                      |                      |
|                      |                      |
+----------------------+----------------------+
```

---

## 17) Acceptance Criteria

* Loads a directory of markdown tickets
* Correctly builds tree via `parent`
* Kanban shows only leaf nodes
* Status mapping applied correctly
* Search filters across title/tags/body
* Done filter behaves per spec
* `$EDITOR` integration works
* Refresh reloads state correctly
* Navigation is fully keyboard-driven
* App remains responsive with ~1k tickets

---

## 18) Future Extensions (Out of Scope)

* File watching / auto-refresh
* Inline editing
* Task creation
* Reparenting
* Drag-and-drop kanban
* Persistent UI state
* Git integration
* Custom columns / workflows

