#!/usr/bin/env python3
"""Read-only live NWS alerts and forecast viewer for the BMH Weather Radio Suite.

This module fetches public data from api.weather.gov. It never sends messages,
opens transmitter sockets, creates SAME/EAS headers, or controls RF equipment.
Local speech (if pyttsx3 is installed) is played only through this computer.
"""
from __future__ import annotations

import json
import queue
import re
import threading
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import tkinter as tk
from tkinter import ttk, messagebox

API_ROOT = "https://api.weather.gov"
USER_AGENT = "BMH-NOAA-Weather-Radio-Suite/1.0 (read-only desktop client)"
SEVERITY_ORDER = {"Extreme": 0, "Severe": 1, "Moderate": 2, "Minor": 3, "Unknown": 4}
_ZONE_RE = re.compile(r"^(IL|IN)Z\d{3}$", re.IGNORECASE)


def validate_zone_code(zone: str) -> str:
    """Return a normalized IL/IN forecast-zone code, or raise ValueError."""
    normalized = (zone or "").strip().upper()
    if not _ZONE_RE.fullmatch(normalized):
        raise ValueError("Enter an Illinois or Indiana zone like INZ011 or ILZ013.")
    return normalized


def normalize_alert(feature: dict) -> dict:
    """Normalize one NWS GeoJSON alert feature into display-friendly fields."""
    props = feature.get("properties") or {}
    identifier = props.get("id") or feature.get("id") or ""
    geocode = props.get("geocode") or {}
    same_values = geocode.get("SAME", []) or []
    if isinstance(same_values, str):
        same_values = [same_values]
    return {
        "id": str(identifier),
        "event": props.get("event") or "Unknown event",
        "severity": props.get("severity") or "Unknown",
        "urgency": props.get("urgency") or "Unknown",
        "certainty": props.get("certainty") or "Unknown",
        "headline": props.get("headline") or props.get("event") or "NWS alert",
        "area": props.get("areaDesc") or "Area not provided",
        "sender": props.get("senderName") or props.get("sender") or "NWS",
        "sent": props.get("sent") or "",
        "effective": props.get("effective") or "",
        "expires": props.get("expires") or "",
        "description": props.get("description") or "",
        "instruction": props.get("instruction") or "",
        "same_codes": ", ".join(same_values),
        "url": str(feature.get("id") or props.get("@id") or ""),
    }


def alert_sort_key(alert: dict) -> tuple:
    """Higher-severity active alerts sort first; event then area makes ties stable."""
    severity = SEVERITY_ORDER.get(alert.get("severity", "Unknown"), SEVERITY_ORDER["Unknown"])
    return severity, str(alert.get("event", "")).casefold(), str(alert.get("area", "")).casefold()


def format_alert_reference(alert: dict) -> str:
    """Build a clearly labelled local reference copy of an official live alert."""
    rows = [
        "LIVE NWS ALERT — REFERENCE COPY ONLY",
        "Do not edit this text into a new official product or retransmit it as one.",
        "",
        f"Event: {alert.get('event', 'Unknown event')}",
        f"Headline: {alert.get('headline', '')}",
        f"Severity / urgency / certainty: {alert.get('severity', 'Unknown')} / "
        f"{alert.get('urgency', 'Unknown')} / {alert.get('certainty', 'Unknown')}",
        f"Area: {alert.get('area', 'Area not provided')}",
        f"Effective: {alert.get('effective', 'Not provided')}",
        f"Expires: {alert.get('expires', 'Not provided')}",
        f"Source: {alert.get('sender', 'NWS')}",
        f"Official source URL: {alert.get('url', '')}",
        "",
        "DESCRIPTION",
        alert.get("description", "").strip() or "(No description supplied.)",
    ]
    instruction = (alert.get("instruction") or "").strip()
    if instruction:
        rows.extend(["", "INSTRUCTIONS", instruction])
    return "\n".join(rows)


class NWSClient:
    """Small standard-library client for public api.weather.gov endpoints."""

    @staticmethod
    def _get_json(url: str) -> dict:
        request = Request(url, headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/geo+json, application/ld+json, application/json",
        })
        try:
            with urlopen(request, timeout=18) as response:
                status = getattr(response, "status", 200)
                if status < 200 or status >= 300:
                    raise RuntimeError(f"NWS API returned HTTP {status}")
                raw = response.read()
        except HTTPError as exc:
            raise RuntimeError(f"NWS API returned HTTP {exc.code}: {exc.reason}") from exc
        except URLError as exc:
            raise RuntimeError(f"Could not reach api.weather.gov: {exc.reason}") from exc
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("NWS API response was not valid JSON.") from exc
        if not isinstance(data, dict):
            raise RuntimeError("NWS API returned an unexpected response.")
        return data

    def active_alerts(self) -> list[dict]:
        """Fetch active alerts for both states; de-duplicate overlapping features."""
        found: dict[str, dict] = {}
        for state in ("IL", "IN"):
            url = f"{API_ROOT}/alerts/active?{urlencode({'area': state})}"
            payload = self._get_json(url)
            for feature in payload.get("features", []) or []:
                alert = normalize_alert(feature)
                key = alert["id"] or alert["url"] or (
                    alert["event"] + "|" + alert["area"] + "|" + alert["sent"]
                )
                found[key] = alert
        return sorted(found.values(), key=alert_sort_key)

    def zone_forecast(self, zone: str) -> dict:
        """Resolve an NWS forecast zone and retrieve its official forecast periods."""
        zone = validate_zone_code(zone)
        zone_payload = self._get_json(f"{API_ROOT}/zones/forecast/{zone}")
        props = zone_payload.get("properties") or {}
        forecast_url = props.get("forecast")
        if not forecast_url:
            raise RuntimeError(f"NWS did not return a forecast URL for {zone}.")
        forecast_payload = self._get_json(forecast_url)
        forecast_props = forecast_payload.get("properties") or {}
        return {
            "zone": zone,
            "name": props.get("name") or zone,
            "url": forecast_url,
            "periods": forecast_props.get("periods") or [],
        }


class LiveNWSWindow:
    """Tkinter window for reading current official NWS data without retransmission."""

    def __init__(self, parent, on_insert_reference=None):
        self.parent = parent
        self.on_insert_reference = on_insert_reference
        self.win = tk.Toplevel(parent)
        self.win.title("BMH Suite — Live NWS Alerts and Forecasts")
        self.win.geometry("1120x760")
        self.win.minsize(850, 580)
        self.client = NWSClient()
        self._results = queue.Queue()
        self._alerts: dict[str, dict] = {}
        self._periods: list[dict] = []
        self._build_ui()
        self.win.after(120, self._drain_results)
        self.refresh_alerts()

    def _build_ui(self):
        banner = ttk.Frame(self.win, padding=(12, 10))
        banner.pack(fill="x")
        ttk.Label(banner, text="LIVE NWS DATA", font=("Segoe UI", 15, "bold")).pack(side="left")
        ttk.Label(
            banner,
            text="READ-ONLY • NO RF / EAS TRANSMISSION / PUBLIC DISPATCH",
            foreground="#a02020",
            font=("Segoe UI", 9, "bold"),
        ).pack(side="right")
        tools = ttk.Frame(self.win, padding=(12, 0, 12, 8))
        tools.pack(fill="x")
        ttk.Button(tools, text="Refresh Active IL / IN Alerts", command=self.refresh_alerts).pack(side="left")
        ttk.Label(tools, text="Forecast zone:").pack(side="left", padx=(18, 5))
        self.zone_var = tk.StringVar(value="INZ011")
        ttk.Entry(tools, textvariable=self.zone_var, width=10).pack(side="left")
        ttk.Button(tools, text="Load Official Zone Forecast", command=self.load_forecast).pack(side="left", padx=6)
        self.status_var = tk.StringVar(value="Connecting to api.weather.gov…")
        ttk.Label(self.win, textvariable=self.status_var, padding=(12, 2)).pack(fill="x")

        self.tabs = ttk.Notebook(self.win)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=8)
        alerts_tab = ttk.Frame(self.tabs, padding=8)
        forecast_tab = ttk.Frame(self.tabs, padding=8)
        self.tabs.add(alerts_tab, text="Active NWS Alerts")
        self.tabs.add(forecast_tab, text="Zone Forecast")

        split = ttk.Panedwindow(alerts_tab, orient="vertical")
        split.pack(fill="both", expand=True)
        list_frame = ttk.Frame(split, padding=2)
        detail_frame = ttk.Frame(split, padding=2)
        split.add(list_frame, weight=3)
        split.add(detail_frame, weight=2)
        cols = ("severity", "event", "area", "expires", "sender")
        self.alert_tree = ttk.Treeview(list_frame, columns=cols, show="headings", selectmode="browse")
        for key, title, width in [
            ("severity", "Severity", 85), ("event", "Event", 220),
            ("area", "Affected Area", 390), ("expires", "Expires (UTC)", 150),
            ("sender", "Issuing Office", 180),
        ]:
            self.alert_tree.heading(key, text=title)
            self.alert_tree.column(key, width=width, anchor="w")
        scroll_y = ttk.Scrollbar(list_frame, orient="vertical", command=self.alert_tree.yview)
        self.alert_tree.configure(yscrollcommand=scroll_y.set)
        self.alert_tree.pack(side="left", fill="both", expand=True)
        scroll_y.pack(side="right", fill="y")
        self.alert_tree.bind("<<TreeviewSelect>>", self._show_selected_alert)

        ttk.Label(detail_frame, text="Selected alert details", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        detail_box = ttk.Frame(detail_frame)
        detail_box.pack(fill="both", expand=True, pady=(4, 6))
        self.alert_detail = tk.Text(detail_box, wrap="word", height=10, state="disabled", font=("Consolas", 9))
        detail_scroll = ttk.Scrollbar(detail_box, orient="vertical", command=self.alert_detail.yview)
        self.alert_detail.configure(yscrollcommand=detail_scroll.set)
        self.alert_detail.pack(side="left", fill="both", expand=True)
        detail_scroll.pack(side="right", fill="y")
        alert_buttons = ttk.Frame(detail_frame)
        alert_buttons.pack(fill="x")
        ttk.Button(alert_buttons, text="Read Selected Alert Locally", command=self.speak_selected).pack(side="left", padx=(0, 6))
        ttk.Button(alert_buttons, text="Open Official Source", command=self.open_selected_source).pack(side="left", padx=(0, 6))
        if self.on_insert_reference:
            ttk.Button(
                alert_buttons, text="Insert Reference Copy into Text Workstation",
                command=self.insert_selected_reference,
            ).pack(side="left")

        ttk.Label(
            forecast_tab,
            text="Official NWS forecast-zone periods (retrieved live from api.weather.gov).",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", pady=(0, 6))
        fcols = ("name", "temperature", "wind", "precip", "short")
        self.forecast_tree = ttk.Treeview(forecast_tab, columns=fcols, show="headings", height=10)
        for key, title, width in [
            ("name", "Period", 140), ("temperature", "Temperature", 110),
            ("wind", "Wind", 130), ("precip", "Precipitation", 130), ("short", "Forecast", 520),
        ]:
            self.forecast_tree.heading(key, text=title)
            self.forecast_tree.column(key, width=width, anchor="w")
        forecast_scroll = ttk.Scrollbar(forecast_tab, orient="vertical", command=self.forecast_tree.yview)
        self.forecast_tree.configure(yscrollcommand=forecast_scroll.set)
        self.forecast_tree.pack(side="left", fill="both", expand=True)
        forecast_scroll.pack(side="right", fill="y")
        self.forecast_detail = tk.Text(forecast_tab, height=7, wrap="word", state="disabled", font=("Consolas", 9))
        self.forecast_detail.pack(fill="x", pady=(7, 0))
        self.forecast_tree.bind("<<TreeviewSelect>>", self._show_selected_period)

        ttk.Label(
            self.win,
            text="Source: National Weather Service API. Data may be delayed or revised by NWS; use official source products for decisions.",
            padding=(12, 3),
        ).pack(fill="x")

    def _start_task(self, kind: str, task):
        self.status_var.set(f"Fetching {kind} from api.weather.gov…")

        def run():
            try:
                self._results.put((kind, True, task()))
            except Exception as exc:
                self._results.put((kind, False, str(exc)))

        threading.Thread(target=run, daemon=True, name=f"bmh-nws-{kind}").start()

    def _drain_results(self):
        try:
            while True:
                kind, ok, payload = self._results.get_nowait()
                if not self.win.winfo_exists():
                    return
                if not ok:
                    if kind == "speech":
                        self.status_var.set(str(payload))
                    else:
                        self.status_var.set(f"{kind.title()} request failed: {payload}")
                    continue
                if kind == "alerts":
                    self._render_alerts(payload)
                elif kind == "forecast":
                    self._render_forecast(payload)
                elif kind == "speech":
                    self.status_var.set(str(payload))
        except queue.Empty:
            pass
        except tk.TclError:
            return
        try:
            if self.win.winfo_exists():
                self.win.after(120, self._drain_results)
        except tk.TclError:
            pass

    def refresh_alerts(self):
        self._start_task("alerts", self.client.active_alerts)

    def load_forecast(self):
        try:
            zone = validate_zone_code(self.zone_var.get())
        except ValueError as exc:
            messagebox.showwarning("Forecast Zone", str(exc), parent=self.win)
            return
        self.zone_var.set(zone)
        self._start_task("forecast", lambda: self.client.zone_forecast(zone))

    def _render_alerts(self, alerts: list[dict]):
        self._alerts.clear()
        self.alert_tree.delete(*self.alert_tree.get_children())
        for index, alert in enumerate(alerts):
            iid = f"alert_{index}"
            self._alerts[iid] = alert
            self.alert_tree.insert("", "end", iid=iid, values=(
                alert["severity"], alert["event"], alert["area"],
                alert["expires"].replace("T", " ") if alert["expires"] else "Unknown",
                alert["sender"],
            ))
        self.status_var.set(f"Loaded {len(alerts)} active alert(s) from the official NWS API for Illinois and Indiana.")
        if alerts:
            first = self.alert_tree.get_children()[0]
            self.alert_tree.selection_set(first)
            self.alert_tree.focus(first)
            self._show_selected_alert()
        else:
            self._set_text(self.alert_detail, "No active alerts were returned for Illinois or Indiana at retrieval time.")

    def _show_selected_alert(self, _event=None):
        selection = self.alert_tree.selection()
        if not selection:
            return
        alert = self._alerts.get(selection[0])
        if not alert:
            return
        text = (
            f"{alert['headline']}\n\nEvent: {alert['event']}\nSeverity: {alert['severity']}\n"
            f"Urgency: {alert['urgency']}\nCertainty: {alert['certainty']}\n"
            f"Affected area: {alert['area']}\nIssued: {alert['sent'] or 'Not supplied'}\n"
            f"Effective: {alert['effective'] or 'Not supplied'}\nExpires: {alert['expires'] or 'Not supplied'}\n"
            f"Issued by: {alert['sender']}\nSAME codes: {alert['same_codes'] or 'Not supplied'}\n"
            f"Official URL: {alert['url']}\n\nDESCRIPTION\n{alert['description'] or '(No description supplied.)'}"
        )
        if alert["instruction"]:
            text += "\n\nINSTRUCTIONS\n" + alert["instruction"]
        self._set_text(self.alert_detail, text)

    def _render_forecast(self, result: dict):
        self._periods = list(result.get("periods") or [])
        self.forecast_tree.delete(*self.forecast_tree.get_children())
        for index, period in enumerate(self._periods):
            pop = period.get("probabilityOfPrecipitation") or {}
            amount = pop.get("value")
            precip = f"{amount}%" if amount is not None else "Not supplied"
            temp = period.get("temperature")
            unit = period.get("temperatureUnit") or ""
            temperature = f"{temp}°{unit}" if temp is not None else "Not supplied"
            wind = " ".join(str(x) for x in (period.get("windSpeed"), period.get("windDirection")) if x) or "Not supplied"
            self.forecast_tree.insert("", "end", iid=f"period_{index}", values=(
                period.get("name", f"Period {index + 1}"), temperature, wind, precip, period.get("shortForecast", ""),
            ))
        self.status_var.set(
            f"Loaded {len(self._periods)} forecast period(s) for {result.get('name')} ({result.get('zone')}). "
            "Select a period for details."
        )
        if self._periods:
            first = self.forecast_tree.get_children()[0]
            self.forecast_tree.selection_set(first)
            self._show_selected_period()

    def _show_selected_period(self, _event=None):
        selection = self.forecast_tree.selection()
        if not selection:
            return
        try:
            index = int(selection[0].split("_")[-1])
            period = self._periods[index]
        except (ValueError, IndexError):
            return
        details = [
            period.get("name", "Forecast period"), period.get("startTime", ""),
            period.get("endTime", ""), "", period.get("detailedForecast", "") or period.get("shortForecast", ""),
        ]
        self._set_text(self.forecast_detail, "\n".join(x for x in details if x is not None))

    @staticmethod
    def _set_text(widget, text: str):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _get_selected_alert(self):
        selection = self.alert_tree.selection()
        return self._alerts.get(selection[0]) if selection else None

    def open_selected_source(self):
        alert = self._get_selected_alert()
        if not alert or not alert["url"]:
            messagebox.showinfo("Official Source", "No official URL was returned for this alert.", parent=self.win)
            return
        import webbrowser
        webbrowser.open(alert["url"])

    def insert_selected_reference(self):
        alert = self._get_selected_alert()
        if not alert or not self.on_insert_reference:
            return
        self.on_insert_reference(format_alert_reference(alert))
        self.status_var.set("Inserted a labelled reference copy into the local workstation; nothing was sent.")

    def speak_selected(self):
        alert = self._get_selected_alert()
        if not alert:
            messagebox.showinfo("Local Speech", "Select an alert first.", parent=self.win)
            return
        text = " ".join(part for part in (
            alert["headline"], f"Areas: {alert['area']}.", alert["description"], alert["instruction"],
        ) if part)

        def speak():
            try:
                import pyttsx3
                engine = pyttsx3.init()
                engine.say(text)
                engine.runAndWait()
                self._results.put(("speech", True, "Finished local computer-speaker playback."))
            except ImportError:
                self._results.put(("speech", False, "Install optional package pyttsx3 to enable local speech."))
            except Exception as exc:
                self._results.put(("speech", False, f"Local speech failed: {exc}"))

        self.status_var.set("Speaking selected alert through this computer's local audio output…")
        threading.Thread(target=speak, daemon=True, name="bmh-nws-local-speech").start()
