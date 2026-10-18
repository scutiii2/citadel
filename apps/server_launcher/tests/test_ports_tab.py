"""The Ports tab on real widgets, and how the window uses the plan to start servers."""

import tkinter as tk
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from src import port_plan, window
from src.models import ServerTemplate
from src.ports_tab import RangeDetail


def make_template(key: str, port: int) -> ServerTemplate:
    return ServerTemplate(
        key=key, display_name=key.upper(), description="", working_dir=Path.cwd(), venv_python=Path("python.exe"),
        module="src.run", port_env_var="PORT", default_port=port, extra_env_vars={}, supports_args=False,
    )


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


@pytest.fixture
def root():
    try:
        tk_root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available")
    try:
        yield tk_root
    finally:
        tk_root.destroy()




def test_the_detail_lists_what_the_range_holds_and_saves_an_edit(root) -> None:
    plan = port_plan.default_plan()
    templates = [make_template("chess", 8070), make_template("db_gateway", 8071)]
    changed, say = Mock(), Mock()
    main = tk.Frame(root)
    main.pack(fill="both", expand=True)

    RangeDetail(main, plan, plan.range_named("Apps"), templates, lambda port: False, changed, say)
    root.update()
    labels = [w.cget("text") for w in descendants(main) if isinstance(w, tk.Label)]

    assert "Apps" in labels and "CHESS" in labels and "DB_GATEWAY" in labels
    entries = [w for w in descendants(main) if isinstance(w, tk.Entry)]
    assert [e.get() for e in entries[:3]] == ["Apps", "8040", "8099"]  # name, first port, last port


def test_a_bad_edit_is_refused_and_leaves_the_plan_alone(root) -> None:
    plan = port_plan.default_plan()
    before = plan.to_dict()
    changed, say = Mock(), Mock()
    detail = RangeDetail(tk.Frame(root), plan, plan.range_named("Apps"), [make_template("chess", 8070)],
                         lambda port: False, changed, say)

    with patch("src.ports_tab.messagebox.showerror") as error:
        detail._reserve("chess", "5173")  # reserved for ember_web
        detail._reserve("chess", "not a number")
        detail._reserve(None, "8075")
        detail._save_range(tk.StringVar(value="Apps"), tk.StringVar(value="8000"), tk.StringVar(value="8099"))  # overlaps Tools

    assert error.call_count == 4
    assert plan.to_dict() == before
    changed.assert_not_called()


def test_moving_and_releasing_report_a_change(root) -> None:
    plan = port_plan.default_plan()
    chess = make_template("chess", 8070)
    changed, say = Mock(), Mock()
    detail = RangeDetail(tk.Frame(root), plan, plan.range_named("Apps"), [chess], lambda port: False, changed, say)

    detail._reserve("chess", "8075")
    assert plan.port_for("chess") == 8075 and chess.default_port == 8075
    changed.assert_called_once_with("Apps")

    detail._release("chess")
    assert plan.port_for("chess") is None


def make_launcher(plan, templates=()):
    launcher = object.__new__(window.LauncherWindow)
    launcher.plan = plan
    launcher.templates = list(templates)
    launcher.status = Mock()
    launcher.root = Mock()
    return launcher


def test_new_servers_get_a_reserved_port_and_the_plan_is_saved() -> None:
    plan = port_plan.default_plan()
    worker = make_template("ember_worker", 8000)
    launcher = make_launcher(plan)

    with patch.object(window, "_save_port_plan") as save, patch.object(window, "_port_in_use", return_value=False):
        launcher._assign_ports([worker, make_template("chess", 8070)])

    assert worker.default_port == 8100 and plan.port_for("ember_worker") == 8100
    save.assert_called_once_with(plan)


def test_a_group_member_on_another_servers_reserved_port_blocks_the_start() -> None:
    plan = port_plan.default_plan()
    chess, web = make_template("chess", 8070), make_template("ember_web", 5173)
    launcher = make_launcher(plan, [chess, web])
    group = SimpleNamespace(members=[SimpleNamespace(template_key="chess", port=5173, extra_env={}, extra_args="", preset_name=None)])

    with patch.object(window, "runtime_warning", return_value=None), patch.object(window, "_port_in_use", return_value=False):
        issues = launcher._group_start_issues(group)

    assert issues == ["CHESS: Port 5173 is reserved for ember_web."]


def test_the_ports_tab_opens_in_the_real_window(root, tmp_path) -> None:
    with patch.object(window, "_load_port_plan", port_plan.default_plan),             patch.object(window, "_save_port_plan"), patch.object(window, "_load_saved_specs", return_value=[]),             patch.object(window, "_load_groups", return_value={}), patch.object(window, "_load_presets", return_value={}),             patch.object(window.LauncherWindow, "_adopt_running_instances"):
        launcher = window.LauncherWindow(root)
        launcher._set_tab("ports")
        launcher._select_range("Web")
        root.update()
        shown = [w.cget("text") for w in descendants(launcher.main) if isinstance(w, tk.Label)]
        cards = len(launcher.sidebar_list.winfo_children())
        launcher._set_tab("servers")
        root.update()

    assert "Web" in shown
    assert cards == len(port_plan.default_plan().ranges)
