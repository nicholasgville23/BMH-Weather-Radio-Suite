#!/usr/bin/env python3
"""Live, read-only NWS alert monitor for the BMH Weather Radio Suite.

This module displays genuine active NWS alerts from api.weather.gov. Optional
speech is emitted only through this computer's local audio device. It does not
encode SAME/EAS, create attention signals, connect to transmitters, or dispatch
alerts to the public.
"""
from __future__ import annotations

import queue
import re
import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk
from urllib.parse import urlencode

from bmh_live_nws import API_ROOT, NWSClient, USER_AGENT, normalize_alert

STATE_CODES = frozenset(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN "
    "MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA "
    "WA WV WI WY DC".split()
)
SEVERITY_RANK = {"Extreme": 0, "Severe": 1, "Moderate": 2, "Minor": 3, "Unknown": 4}
EMERGENCY_EVENTS = (
    "National Emergency Message",
    "Emergency Action Notification",
    "Civil Danger Warning",
    "Evacuation Immediate",
    "Nuclear Power Plant Warning",
    "Radiological Hazard Warning",
    "Shelter in Place Warning",
    "Law Enforcement Warning",
)


def parse_areas(value: str) -> list[str | None]:
    """Parse comma-separated US state abbreviations; None means nationwide."""
    normalized = (value or "").strip().upper()
    if normalized in {"", "US", "USA", "ALL", "ALL US", "ALL STATES", "NATIONWIDE"}:
        return [None]
    values = [part.strip() for part in re.split(r"[,; ]+", normalized) if part.strip()]
    areas: list[str | None] = []
    for area in values:
        if area in {"US", "USA", "ALL", "NATIONWIDE"}:
            if len(values) != 1:
                raise ValueError("Use US/ALL by itself, or list state codes such as IL,IN.")
            return [None]
        if not re.fullmatch(r"[A-Z]{2}", area) or area not in STATE_CODES:
            raise ValueError(f"Unsupported state/area code: {area!r}. Example: IL,IN.")
        if area not in areas:
            areas.append(area)
    return areas or [None]


def alert_priority(event: str) -> int:
    """Return the suite's requested display priority: emergency to statement."""
    name = (event or "").strip().casefold()
    if any(token.casefold() in name for token in EMERGENCY_EVENTS):
        return 0
    if name.endswith("warning"):
        return 1
    if name.endswith("watch"):
        return 2
    if name.endswith("advisory"):
        return 3
    return 4


def sort_alerts(alerts: list[dict]) -> list[dict]:
    """Sort real active alerts using event priority, then CAP severity."""
    return sorted(
        alerts,
        key=lambda item: (
            alert_priority(item.get("event", "")),
            SEVERITY_RANK.get(item.get("severity", "Unknown"), 4),
            (item.get("event") or "").casefold(),
            (item.get("area") or "").casefold(),
        ),
    )


def alert_key(alert: dict) -> str:
    """Use the product ID plus its sent time to detect new/updated products."""
    return "|".join(
        str(alert.get(key) or "")
        for key in ("id", "sent", "event", "area")
    )


def fetch_active_alerts(areas: list[str | None]) -> list[dict]:
    """Fetch current alert products from the official NWS API."""
    found: dict[str, dict] = {}
    for area in areas:
        query = urlencode({"area": area}) if area else ""
        url = f"{API_ROOT}/alerts/active"
        if query:
            url = f"{url}?{query}"
        payload = NWSClient._get_json(url)
        for feature in payload.get("features", []) or []:
            alert = normalize_alert(feature)
            key = alert_key(alert) or alert.get("url") or repr(alert)
            found[key] = alert
    return sort_alerts(list(found.values()))


def format_monitor_detail(alert: dict) -> str:
    """Render alert metadata and its official source for human review."""
    lines = [
        alert.get("headline") or alert.get("event") or "NWS alert",
        "",
        f"Event: {alert.get('event') or 'Not provided'}",
        f"Priority class: {('Emergency', 'Warning', 'Watch', 'Advisory', 'Statement / Other')[alert_priority(alert.get('event', ''))]}",
        f"Severity / urgency / certainty: {alert.get('severity', 'Unknown')} / "
        f"{alert.get('urgency', 'Unknown')} / {alert.get('certainty', 'Unknown')}",
        f"Area: {alert.get('area') or 'Not provided'}",
        f"Effective: {alert.get('effective') or 'Not provided'}",
        f"Expires: {alert.get('expires') or 'Not provided'}",
        f"Sent: {alert.get('sent') or 'Not provided'}",
        f"Source: {alert.get('sender') or 'National Weather Service'}",
        f"Official source URL: {alert.get('url') or 'Not provided'}",
        "",
        "DESCRIPTION",
        (alert.get("description") or "").strip() or "(No description provided.)",
    ]
    instruction = (alert.get("instruction") or "").strip()
    if instruction:
        lines.extend(["", "INSTRUCTIONS", instruction])
    lines.extend([
        "",
        "LIVE DATA NOTICE",
        "This is a read-only display of official NWS data. It is not a transmitter, "
        "EAS encoder, or public alert-distribution endpoint.",
    ])
    return "\n".join(lines)


class LiveMonitorWindow:
    """Tkinter monitor with manual refresh and user-controlled polling."""

    def __init__(self, parent, default_areas: str = "IL,IN"):
        self.parent = parent
        self.win = tk.Toplevel(parent)
        self.win.title("BMH Suite — Live NWS Operations Monitor")
        self.win.geometry("1180x780")
        self.win.minsize(900, 600)

        self._results: queue.Queue = queue.Queue()
        self._in_flight = False
        self._monitoring = False
        self._poll_after_id = None
        self._previous_snapshot: set[str] | None = None
        self._alerts_by_iid: dict[str, dict] = {}
        self._speech_var = tk.BooleanVar(value=False)
        self._areas_var = tk.StringVar(value=default_areas)
        self._interval_var = tk.StringVar(value="120")
        self._status_var = tk.StringVar(value="Ready to retrieve official NWS data.")
        self._count_var = tk.StringVar(value="No snapshot loaded")
        self._build_ui()
        self.win.after(100, self._drain_results)
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh_now()

    def _build_ui(self):
        banner = ttk.Frame(self.win, padding=(12, 10))
        banner.pack(fill="x")
        ttk.Label(
            banner, text="LIVE NWS OPERATIONS MONITOR",
            font=("Segoe UI", 15, "bold"),
        ).pack(side="left")
        ttk.Label(
            banner,
            text="READ-ONLY • NO RF / EAS / PUBLIC DISPATCH",
            foreground="#9b1c1c",
            font=("Segoe UI", 9, "bold"),
        ).pack(side="right")

        controls = ttk.Frame(self.win, padding=(12, 0, 12, 8))
        controls.pack(fill="x")
        ttk.Label(controls, text="Areas (state codes or US):").pack(side="left")
        ttk.Entry(controls, textvariable=self._areas_var, width=18).pack(side="left", padx=(5, 12))
        ttk.Label(controls, text="Poll every (seconds):").pack(side="left")
        ttk.Spinbox(
            controls, from_=60, to=900, increment=30,
            textvariable=self._interval_var, width=7,
        ).pack(side="left", padx=(5, 12))
        ttk.Button(controls, text="Refresh Now", command=self.refresh_now).pack(side="left", padx=(0, 5))
        self._monitor_button = ttk.Button(
            controls, text="Start Monitoring", command=self.start_monitoring
        )
        self._monitor_button.pack(side="left", padx=(0, 5))
        ttk.Button(controls, text="Open Official Source", command=self.open_selected_source).pack(side="left")
        ttk.Checkbutton(
            controls,
            text="Announce new warnings locally (computer speakers only)",
            variable=self._speech_var,
        ).pack(side="left", padx=(14, 0))

        status = ttk.Frame(self.win, padding=(12, 0, 12, 6))
        status.pack(fill="x")
        ttk.Label(status, textvariable=self._status_var).pack(side="left", fill="x", expand=True)
        ttk.Label(status, textvariable=self._count_var).pack(side="right")

        splitter = ttk.Panedwindow(self.win, orient="vertical")
        splitter.pack(fill="both", expand=True, padx=12, pady=(2, 12))
        table_frame = ttk.Frame(splitter)
        detail_frame = ttk.Frame(splitter)
        splitter.add(table_frame, weight=3)
        splitter.add(detail_frame, weight=2)

        columns = ("priority", "event", "area", "severity", "expires")
        self._tree = ttk.Treeview(
            table_frame, columns=columns, show="headings", selectmode="browse"
        )
        headings = {
            "priority": ("Priority", 110),
            "event": ("NWS Event", 245),
            "area": ("Affected Area", 330),
            "severity": ("Severity", 100),
            "expires": ("Expires (UTC)", 160),
        }
        for key, (label, width) in headings.items():
            self._tree.heading(key, text=label)
            self._tree.column(key, width=width, minwidth=80, stretch=key in {"event", "area"})
        self._tree.tag_configure("emergency", foreground="#8b0000")
        self._tree.tag_configure("warning", foreground="#b04b00")
        self._tree.tag_configure("watch", foreground="#775500")
        tree_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=tree_scroll.set)
        self._tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")
        self._tree.bind("<<TreeviewSelect>>", self._show_selected_detail)

        ttk.Label(
            detail_frame, text="Selected alert details", font=("Segoe UI", 10, "bold")
        ).pack(anchor="w", pady=(8, 4))
        self._detail = tk.Text(detail_frame, wrap="word", height=12, state="disabled")
        detail_scroll = ttk.Scrollbar(detail_frame, orient="vertical", command=self._detail.yview)
        self._detail.configure(yscrollcommand=detail_scroll.set)
        self._detail.pack(side="left", fill="both", expand=True)
        detail_scroll.pack(side="right", fill="y")

    def refresh_now(self):
        if self._in_flight:
            self._status_var.set("A refresh is already in progress.")
            return
        try:
            areas = parse_areas(self._areas_var.get())
        except ValueError as exc:
            self._status_var.set(str(exc))
            return
        self._in_flight = True
        self._status_var.set("Requesting live active alerts from api.weather.gov…")
        threading.Thread(target=self._fetch_worker, args=(areas,), daemon=True).start()

    def _fetch_worker(self, areas: list[str | None]):
        try:
            alerts = fetch_active_alerts(areas)
            self._results.put(("ok", alerts, None))
        except Exception as exc:
            self._results.put(("error", [], str(exc)))

    def start_monitoring(self):
        if self._monitoring:
            self.stop_monitoring()
            return
        try:
            interval = int(self._interval_var.get())
            if not 60 <= interval <= 900:
                raise ValueError
        except (TypeError, ValueError):
            self._status_var.set("Polling interval must be between 60 and 900 seconds.")
            return
        try:
            parse_areas(self._areas_var.get())
        except ValueError as exc:
            self._status_var.set(str(exc))
            return
        self._monitoring = True
        self._monitor_button.configure(text="Stop Monitoring")
        self._status_var.set(f"Continuous live monitoring enabled; refresh interval {interval} seconds.")
        self.refresh_now()
        self._schedule_next(interval)

    def _schedule_next(self, interval: int | None = None):
        if not self._monitoring:
            return
        try:
            delay = int(interval if interval is not None else self._interval_var.get())
            delay = max(60, min(900, delay))
        except (TypeError, ValueError):
            delay = 120
        self._poll_after_id = self.win.after(delay * 1000, self._scheduled_refresh)

    def _scheduled_refresh(self):
        self._poll_after_id = None
        if not self._monitoring:
            return
        self.refresh_now()
        self._schedule_next()

    def stop_monitoring(self):
        self._monitoring = False
        self._monitor_button.configure(text="Start Monitoring")
        if self._poll_after_id is not None:
            try:
                self.win.after_cancel(self._poll_after_id)
            except tk.TclError:
                pass
            self._poll_after_id = None
        self._status_var.set("Continuous monitoring stopped. Manual refresh remains available.")

    def _drain_results(self):
        try:
            while True:
                status, alerts, error = self._results.get_nowait()
                self._in_flight = False
                if status == "error":
                    self._status_var.set(f"NWS refresh failed: {error}")
                    self._count_var.set("Data unavailable")
                    continue
                old_snapshot = self._previous_snapshot
                new_snapshot = {alert_key(alert) for alert in alerts}
                self._previous_snapshot = new_snapshot
                if old_snapshot is not None and self._speech_var.get():
                    new_warnings = [
                        alert for alert in alerts
                        if alert_priority(alert.get("event", "")) <= 1
                        and alert_key(alert) not in old_snapshot
                    ]
                    if new_warnings:
                        threading.Thread(
                            target=self._announce_locally,
                            args=(new_warnings,),
                            daemon=True,
                        ).start()
                self._populate_alerts(alerts)
                self._status_var.set("Live data refreshed from the official NWS API.")
                self._count_var.set(f"{len(alerts)} active product(s) • updated from NWS")
        except queue.Empty:
            pass
        try:
            if self.win.winfo_exists():
                self.win.after(100, self._drain_results)
        except tk.TclError:
            return

    def _populate_alerts(self, alerts: list[dict]):
        selected = self._tree.selection()
        selected_alert_key = None
        if selected:
            current = self._alerts_by_iid.get(selected[0])
            if current:
                selected_alert_key = alert_key(current)
        self._tree.delete(*self._tree.get_children())
        self._alerts_by_iid.clear()
        for index, alert in enumerate(alerts):
            event = alert.get("event") or "Unknown event"
            priority = alert_priority(event)
            priority_label = ("EMERGENCY", "WARNING", "WATCH", "ADVISORY", "STATEMENT / OTHER")[priority]
            expires = alert.get("expires") or "—"
            iid = f"alert_{index}"
            tag = "emergency" if priority == 0 else "warning" if priority == 1 else "watch" if priority == 2 else ""
            self._tree.insert(
                "", "end", iid=iid,
                values=(
                    priority_label,
                    event,
                    alert.get("area") or "Area not provided",
                    alert.get("severity") or "Unknown",
                    expires.replace("T", " ").replace("Z", " UTC"),
                ),
                tags=(tag,) if tag else (),
            )
            self._alerts_by_iid[iid] = alert
            if selected_alert_key and alert_key(alert) == selected_alert_key:
                self._tree.selection_set(iid)
        children = self._tree.get_children()
        if children and not self._tree.selection():
            self._tree.selection_set(children[0])
            self._tree.focus(children[0])
        elif not children:
            self._set_detail("No active alerts were returned for the selected area(s).")

    def _show_selected_detail(self, _event=None):
        selected = self._tree.selection()
        if not selected:
            return
        alert = self._alerts_by_iid.get(selected[0])
        if alert:
            self._set_detail(format_monitor_detail(alert))

    def _set_detail(self, value: str):
        self._detail.configure(state="normal")
        self._detail.delete("1.0", "end")
        self._detail.insert("1.0", value)
        self._detail.configure(state="disabled")

    def open_selected_source(self):
        selected = self._tree.selection()
        if not selected:
            messagebox.showinfo("Official NWS Source", "Select an alert first.", parent=self.win)
            return
        alert = self._alerts_by_iid.get(selected[0], {})
        url = alert.get("url") or ""
        if not url.startswith("https://api.weather.gov/"):
            messagebox.showwarning(
                "Official NWS Source",
                "No verified api.weather.gov source URL is available for this alert.",
                parent=self.win,
            )
            return
        webbrowser.open(url)

    @staticmethod
    def _announce_locally(alerts: list[dict]):
        """Optional local computer speech; never routes audio to a transmitter."""
        try:
            import pyttsx3
            engine = pyttsx3.init()
            for alert in alerts:
                area = (alert.get("area") or "the affected area").replace(";", ",")
                event = alert.get("event") or "weather alert"
                headline = alert.get("headline") or ""
                engine.say(f"New National Weather Service {event} for {area}. {headline}")
            engine.runAndWait()
            engine.stop()
        except Exception:
            # Keep API monitoring available even when local speech is unavailable.
            return

    def close(self):
        self.stop_monitoring()
        try:
            self.win.destroy()
        except tk.TclError:
            pass


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    LiveMonitorWindow(root)
    root.mainloop()
