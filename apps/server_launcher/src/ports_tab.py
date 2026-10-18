"""The Ports tab's detail pane: edit one range and choose which servers reserve which of its ports."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, ttk

from .models import ServerTemplate
from .port_plan import PortBusy, PortPlan, PortPlanError, PortRange
from .theme import (
    _ACCENT, _ACCENT_CONTRAST, _BG, _BORDER, _DANGER, _DANGER_BORDER, _DIM_FG, _FG, _FIELD_BG, _ROW_BG,
)
from .widgets import RoundedButton, RoundedPanel, ScrollableFrame


class RangeDetail:
    """Draws one range into `main`. Every edit goes through the PortPlan, which
    refuses overlaps and double reservations; `changed` is called after each
    accepted edit so the window can save the plan and redraw."""

    def __init__(
        self, main: tk.Frame, plan: PortPlan, port_range: PortRange, templates: list[ServerTemplate],
        busy: PortBusy, changed: Callable[[str | None], None], say: Callable[[str], None],
    ) -> None:
        self._plan = plan
        self._range = port_range
        self._templates = templates
        self._busy = busy
        self._changed = changed
        self._say = say
        self._names = {t.key: t.display_name for t in templates}
        self._build(main)

    # ---- layout ---------------------------------------------------------------

    def _build(self, main: tk.Frame) -> None:
        header = tk.Frame(main, bg=_BG)
        header.pack(fill="x", padx=16, pady=(16, 8))
        tk.Label(header, text=self._range.name, bg=_BG, fg=_FG, font=("Segoe UI", 14, "bold")).pack(side="left")
        tk.Label(
            header, text=f"{self._range.start}-{self._range.end}  ·  {self._range.size} ports",
            bg=_BG, fg=_DIM_FG,
        ).pack(side="left", padx=(12, 0))

        scroll = ScrollableFrame(main, bg=_BG)
        scroll.pack(fill="both", expand=True, pady=(0, 16))
        content = scroll.body

        self._section(content, "Range")
        panel = RoundedPanel(content, bg=_BG, fill=_ROW_BG, outline=_BORDER)
        panel.pack(fill="x", padx=16)
        name_var = tk.StringVar(value=self._range.name)
        start_var = tk.StringVar(value=str(self._range.start))
        end_var = tk.StringVar(value=str(self._range.end))
        for label, var in (("Name", name_var), ("First port", start_var), ("Last port", end_var)):
            self._field(panel.body, label, var)
        buttons = tk.Frame(panel.body, bg=_ROW_BG)
        buttons.pack(fill="x", pady=(8, 0))
        RoundedButton(
            buttons, "Save range", command=lambda: self._save_range(name_var, start_var, end_var),
            bg=_ROW_BG, fill=_ACCENT, outline=_ACCENT, fg=_ACCENT_CONTRAST, font=("Segoe UI", 10, "bold"),
        ).pack(side="left")

        self._section(content, "Reserved here")
        reserved = RoundedPanel(content, bg=_BG, fill=_ROW_BG, outline=_BORDER)
        reserved.pack(fill="x", padx=16)
        keys = self._plan.keys_in(self._range)
        if not keys:
            tk.Label(reserved.body, text="No server reserves a port in this range.", bg=_ROW_BG, fg=_DIM_FG).pack(anchor="w")
        for key in keys:
            self._reserved_row(reserved.body, key)

        self._section(content, "Reserve a port")
        reserve = RoundedPanel(content, bg=_BG, fill=_ROW_BG, outline=_BORDER)
        reserve.pack(fill="x", padx=16)
        self._reserve_row(reserve.body)

    def _section(self, parent: tk.Frame, text: str) -> None:
        tk.Label(parent, text=text, bg=_BG, fg=_DIM_FG, font=("Segoe UI", 9)).pack(anchor="w", padx=16, pady=(14, 4))

    def _field(self, parent: tk.Frame, label: str, var: tk.StringVar, width: int | None = None) -> tk.Entry:
        row = tk.Frame(parent, bg=_ROW_BG)
        row.pack(fill="x", pady=4)
        tk.Label(row, text=label, bg=_ROW_BG, fg=_DIM_FG, width=14, anchor="w").pack(side="left")
        entry = self._entry(row, var, width)
        entry.pack(side="left", fill="x", expand=width is None, ipady=4)
        return entry

    def _entry(self, parent: tk.Frame, var: tk.StringVar, width: int | None = None) -> tk.Entry:
        options = {"width": width} if width else {}
        return tk.Entry(
            parent, textvariable=var, bg=_FIELD_BG, fg=_FG, insertbackground=_FG, relief="flat",
            highlightthickness=1, highlightbackground=_BORDER, highlightcolor=_ACCENT, **options,
        )

    def _reserved_row(self, parent: tk.Frame, key: str) -> None:
        row = tk.Frame(parent, bg=_ROW_BG)
        row.pack(fill="x", pady=4)
        tk.Label(row, text=self._names.get(key, key), bg=_ROW_BG, fg=_FG, width=22, anchor="w").pack(side="left")
        var = tk.StringVar(value=str(self._plan.port_for(key)))
        self._entry(row, var, 8).pack(side="left", ipady=4)
        RoundedButton(
            row, "Move", command=lambda: self._reserve(key, var.get()),
            bg=_ROW_BG, fill=_ROW_BG, outline=_BORDER, fg=_FG,
        ).pack(side="left", padx=(8, 0))
        RoundedButton(
            row, "Release", command=lambda: self._release(key),
            bg=_ROW_BG, fill=_ROW_BG, outline=_DANGER_BORDER, fg=_DANGER,
        ).pack(side="left", padx=(6, 0))

    def _reserve_row(self, parent: tk.Frame) -> None:
        row = tk.Frame(parent, bg=_ROW_BG)
        row.pack(fill="x", pady=4)
        tk.Label(row, text="Server", bg=_ROW_BG, fg=_DIM_FG, width=14, anchor="w").pack(side="left")
        labels = {f"{t.display_name}  ({t.key})": t.key for t in self._templates}
        choice = tk.StringVar()
        box = ttk.Combobox(row, textvariable=choice, values=list(labels), state="readonly", width=28)
        box.pack(side="left")
        row2 = tk.Frame(parent, bg=_ROW_BG)
        row2.pack(fill="x", pady=4)
        tk.Label(row2, text="Port", bg=_ROW_BG, fg=_DIM_FG, width=14, anchor="w").pack(side="left")
        port_var = tk.StringVar(value=str(self._suggest_port()))
        self._entry(row2, port_var, 8).pack(side="left", ipady=4)
        RoundedButton(
            row2, "Reserve", command=lambda: self._reserve(labels.get(choice.get()), port_var.get()),
            bg=_ROW_BG, fill=_ACCENT, outline=_ACCENT, fg=_ACCENT_CONTRAST, font=("Segoe UI", 10, "bold"),
        ).pack(side="left", padx=(8, 0))
        tk.Label(
            parent, text="A server that already has a port moves here.", bg=_ROW_BG, fg=_DIM_FG, font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(6, 0))

    def _suggest_port(self) -> int:
        """The first port of the range nobody has reserved and nothing is listening on."""
        for port in range(self._range.start, self._range.end + 1):
            if self._plan.owner_of(port) is None and not self._busy(port):
                return port
        return self._range.start

    # ---- actions --------------------------------------------------------------

    def _refuse(self, error: PortPlanError) -> None:
        self._say(str(error))
        messagebox.showerror("Ports", str(error))

    def _save_range(self, name: tk.StringVar, start: tk.StringVar, end: tk.StringVar) -> None:
        try:
            first, last = int(start.get()), int(end.get())
        except ValueError:
            self._refuse(PortPlanError("The first and last port must be numbers."))
            return
        try:
            saved = self._plan.update_range(self._range.name, name.get(), first, last)
        except PortPlanError as error:
            self._refuse(error)
            return
        self._say(f"Saved range {saved.name}.")
        self._changed(saved.name)

    def _reserve(self, key: str | None, text: str) -> None:
        if key is None:
            self._refuse(PortPlanError("Choose a server first."))
            return
        try:
            port = int(text)
        except ValueError:
            self._refuse(PortPlanError("The port must be a number."))
            return
        try:
            self._plan.reserve(key, port)
        except PortPlanError as error:
            self._refuse(error)
            return
        template = next((t for t in self._templates if t.key == key), None)
        if template is not None:
            template.default_port = port
        self._say(f"Reserved port {port} for {self._names.get(key, key)}.")
        self._changed(self._range.name)

    def _release(self, key: str) -> None:
        self._plan.release(key)
        self._say(f"Released {self._names.get(key, key)}; it moved to a free port in the fallback range.")
        self._changed(self._range.name)

