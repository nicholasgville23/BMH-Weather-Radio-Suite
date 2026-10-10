#!/usr/bin/env python3
"""Read-only current-observation viewer backed by the official NWS API.

This module displays real observations from api.weather.gov. It does not
transmit radio signals, activate EAS equipment, or dispatch public alerts.
"""
from __future__ import annotations

import json
import math
import queue
import re
import threading
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser

API_ROOT = "https://api.weather.gov"
USER_AGENT = "BMH-NOAA-Weather-Radio-Suite/1.1 (read-only observation viewer)"
_STATION_RE = re.compile(r"^[A-Z0-9]{3,5}$")
MPS_TO_MPH = 2.2369362921
METERS_TO_MILES = 0.000621371192
PA_PER_INHG = 3386.389
MM_TO_INCHES = 1.0 / 25.4


def validate_station_id(station_id: str) -> str:
    """Validate an NWS station identifier before building an API URL."""
    value = (station_id or "").strip().upper()
    if not _STATION_RE.fullmatch(value):
        raise ValueError("Enter a station identifier using 3–5 letters or digits, such as KVPZ.")
    return value


def _number(measurement, convert=lambda value: value):
    if not isinstance(measurement, dict):
        return None
    value = measurement.get("value")
    if value is None:
        return None
    try:
        number = float(value)
        if not math.isfinite(number):
            return None
        return convert(number)
    except (TypeError, ValueError, OverflowError):
        return None


def celsius_to_fahrenheit(value):
    return value * 9.0 / 5.0 + 32.0


def degrees_to_compass(value):
    if value is None:
        return "Calm/unknown"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "Unknown"
    if not math.isfinite(number):
        return "Unknown"
    points = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
              "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")
    return points[int((number % 360.0) / 22.5 + 0.5) % 16]


def normalize_observation(payload: dict, station_id: str = "") -> dict:
    """Normalize one /observations/latest response into display fields."""
    props = payload.get("properties") or {}
    temp = _number(props.get("temperature"), celsius_to_fahrenheit)
    dewpoint = _number(props.get("dewpoint"), celsius_to_fahrenheit)
    wind = _number(props.get("windSpeed"), lambda value: value * MPS_TO_MPH)
    gust = _number(props.get("windGust"), lambda value: value * MPS_TO_MPH)
    pressure = _number(props.get("barometricPressure"), lambda value: value / PA_PER_INHG)
    visibility = _number(props.get("visibility"), lambda value: value * METERS_TO_MILES)
    precip = _number(props.get("precipitationLastHour"), lambda value: value * MM_TO_INCHES)
    humidity = _number(props.get("relativeHumidity"))
    return {
        "station_id": validate_station_id(station_id) if station_id else "",
        "timestamp": props.get("timestamp") or "Not provided",
        "description": props.get("textDescription") or "Not provided",
        "temperature_f": temp,
        "dewpoint_f": dewpoint,
        "wind_speed_mph": wind,
        "wind_gust_mph": gust,
        "wind_direction": degrees_to_compass(_number(props.get("windDirection"))),
        "humidity_percent": humidity,
        "pressure_inhg": pressure,
        "visibility_miles": visibility,
        "precipitation_last_hour_in": precip,
        "source_url": str(payload.get("@id") or payload.get("id") or ""),
    }


def format_observation(observation: dict) -> str:
    """Format normalized values for people; absent measurements stay explicit."""
    def show(value, suffix="", digits=1):
        return "Not reported" if value is None else f"{value:.{digits}f}{suffix}"

    return "\n".join([
        "LIVE NWS CURRENT OBSERVATION — READ-ONLY REFERENCE",
        "Not a warning or a substitute for official NWS alerts.",
        "",
        f"Station: {observation.get('station_id') or 'Unknown'}",
        f"Observation time: {observation.get('timestamp', 'Not provided')}",
        f"Conditions: {observation.get('description', 'Not provided')}",
        f"Temperature: {show(observation.get('temperature_f'), ' °F')}",
        f"Dew point: {show(observation.get('dewpoint_f'), ' °F')}",
        f"Wind: {observation.get('wind_direction', 'Unknown')} at {show(observation.get('wind_speed_mph'), ' mph')}",
        f"Wind gust: {show(observation.get('wind_gust_mph'), ' mph')}",
        f"Relative humidity: {show(observation.get('humidity_percent'), '%')}",
        f"Pressure: {show(observation.get('pressure_inhg'), ' inHg', 2)}",
        f"Visibility: {show(observation.get('visibility_miles'), ' mi')}",
        f"Precipitation, last hour: {show(observation.get('precipitation_last_hour_in'), ' in', 2)}",
        f"Official data URL: {observation.get('source_url') or 'Not supplied'}",
    ])


class NWSObservationClient:
    """Small standard-library client for a station's latest NWS observation."""

    @staticmethod
    def latest(station_id: str) -> dict:
        station_id = validate_station_id(station_id)
        url = f"{API_ROOT}/stations/{station_id}/observations/latest"
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
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("NWS API response was not valid JSON.") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("properties"), dict):
            raise RuntimeError("NWS API returned an unexpected observation format.")
        result = normalize_observation(payload, station_id)
        result["source_url"] = url
        return result


class LiveObservationsWindow:
    """Tkinter window for manually refreshing real NWS surface observations."""

    def __init__(self, parent, default_station="KVPZ"):
        self.parent = parent
        self.win = tk.Toplevel(parent)
        self.win.title("BMH Suite — Live NWS Current Observations")
        self.win.geometry("900x640")
        self.win.minsize(720, 480)
        self._results = queue.Queue()
        self._build_ui(default_station)
        self.win.after(120, self._drain_results)
        self.refresh()

    def _build_ui(self, default_station):
        banner = ttk.Frame(self.win, padding=(12, 10))
        banner.pack(fill="x")
        ttk.Label(banner, text="LIVE NWS OBSERVATIONS", font=("Segoe UI", 15, "bold")).pack(side="left")
        ttk.Label(banner, text="READ-ONLY • NO TRANSMISSION", foreground="#a02020",
                  font=("Segoe UI", 9, "bold")).pack(side="right")
        controls = ttk.Frame(self.win, padding=(12, 0, 12, 8))
        controls.pack(fill="x")
        ttk.Label(controls, text="NWS station ID:").pack(side="left")
        self.station_var = tk.StringVar(value=default_station)
        ttk.Entry(controls, textvariable=self.station_var, width=12).pack(side="left", padx=6)
        ttk.Button(controls, text="Refresh Latest Observation", command=self.refresh).pack(side="left")
        ttk.Button(controls, text="Open Official API Source", command=self.open_source).pack(side="left", padx=6)
        self.status_var = tk.StringVar(value="Connecting to api.weather.gov…")
        ttk.Label(self.win, textvariable=self.status_var, padding=(12, 2)).pack(fill="x")
        frame = ttk.Frame(self.win, padding=12)
        frame.pack(fill="both", expand=True)
        self.detail = tk.Text(frame, wrap="word", font=("Consolas", 11), state="disabled")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.detail.yview)
        self.detail.configure(yscrollcommand=scroll.set)
        self.detail.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        ttk.Label(self.win,
                  text="Source: National Weather Service API. Observations can be missing, delayed, or revised; use official alerts for warning decisions.",
                  padding=(12, 4), wraplength=860).pack(fill="x")

    def refresh(self):
        try:
            station = validate_station_id(self.station_var.get())
        except ValueError as exc:
            messagebox.showwarning("NWS Station ID", str(exc), parent=self.win)
            return
        self.station_var.set(station)
        self.status_var.set(f"Fetching latest observation for {station}…")

        def run():
            try:
                self._results.put((True, NWSObservationClient.latest(station)))
            except Exception as exc:
                self._results.put((False, str(exc)))

        threading.Thread(target=run, daemon=True, name="bmh-nws-observation").start()

    def _drain_results(self):
        try:
            while True:
                ok, result = self._results.get_nowait()
                if not self.win.winfo_exists():
                    return
                if not ok:
                    self.status_var.set(f"Observation request failed: {result}")
                    self._set_detail(str(result))
                    continue
                self._latest = result
                self.status_var.set(f"Loaded latest observation for {result['station_id']} from the official NWS API.")
                self._set_detail(format_observation(result))
        except queue.Empty:
            pass
        except tk.TclError:
            return
        try:
            if self.win.winfo_exists():
                self.win.after(120, self._drain_results)
        except tk.TclError:
            pass

    def _set_detail(self, text):
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", text)
        self.detail.configure(state="disabled")

    def open_source(self):
        station = self.station_var.get().strip().upper()
        try:
            station = validate_station_id(station)
        except ValueError as exc:
            messagebox.showwarning("NWS Station ID", str(exc), parent=self.win)
            return
        webbrowser.open(f"{API_ROOT}/stations/{station}/observations/latest")
