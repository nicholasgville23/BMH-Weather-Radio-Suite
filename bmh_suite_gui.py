#!/usr/bin/env python3
"""BMH NOAA Weather Radio Suite - local Tkinter simulation console.

This is a simulation only. It does not emit RF, connect to an EAS encoder,
or transmit public-warning audio. Network address/port fields are metadata only.
"""
from __future__ import annotations

import json
import math
import os
import struct
import wave
from datetime import datetime, timezone
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog

APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "bmh_suite_config.json"
OUTBOX_PATH = APP_DIR / "bmh_outbox.json"
AUDIO_DIR = APP_DIR / "audio_preview"

HAZARDS = [
    "Tornado Warning", "Severe Thunderstorm Warning", "Flash Flood Warning",
    "Extreme Wind Warning", "Civil Emergency Message", "Civil Danger Warning",
    "Evacuation Immediate", "Emergency Action Notification", "National Emergency Message",
    "Tornado Watch", "Severe Thunderstorm Watch", "Flash Flood Watch",
    "Winter Storm Warning", "Winter Weather Advisory", "Special Weather Statement",
    "Required Monthly Test", "Required Weekly Test", "Statement"
]
PRIORITY = {
    "National Emergency Message": 0, "Emergency Action Notification": 0,
    "Civil Danger Warning": 0, "Evacuation Immediate": 0, "Civil Emergency Message": 0,
    "Tornado Warning": 1, "Extreme Wind Warning": 1, "Severe Thunderstorm Warning": 1,
    "Flash Flood Warning": 1, "Winter Storm Warning": 1,
    "Tornado Watch": 2, "Severe Thunderstorm Watch": 2, "Flash Flood Watch": 2,
    "Winter Weather Advisory": 3, "Special Weather Statement": 4,
    "Required Monthly Test": 5, "Required Weekly Test": 5, "Statement": 6
}
MODES = [
    "Winter Weather", "Flooding", "Severe Weather", "Severe Weather Possible",
    "Off the Air", "Station ID Only", "Current Time Only", "General",
    "Zone Forecast", "Severe Weather and Alert Summary"
]
PRODUCT_IDS = [
    "ADVANCE", "EMR_STATION_ID", "PREPAREDNESS_ACTIONS", "SLGT_STATION_ID",
    "OFF_AIR", "STATION_ID", "SHORT_ID", "LONG_ID", "SEVERE_MESSAGE", "FORECAST",
    "OBSERVATIONS", "HWO", "CURRENT_TIME"
]
CYCLE_ENTRIES = [
    "@AUTO_ID", "@ACTIVE_ALERTS", "@SEVERE_DYNAMIC", "@PRODUCT:ZFPLOT",
    "@PRODUCT:HWOLOT", "@PRODUCT:HWOIWX", "@AUTO_SEVERE_ID",
    "@NEW_CON_ALERTS", "@CAN_EXP_ALERTS"
]
LANGUAGES = ["English", "Turkish", "German", "Spanish", "French"]
BROADCAST_TEXT = {
    "English": "This is a simulated National Weather Radio broadcast. No alert is being transmitted.",
    "Turkish": "Bu, simüle edilmiş bir hava durumu radyo yayınıdır. Hiçbir uyarı iletilmiyor.",
    "German": "Dies ist eine simulierte Wetterfunkdurchsage. Es wird keine Warnung gesendet.",
    "Spanish": "Este es un mensaje simulado de radio meteorológica. No se transmite ninguna alerta.",
    "French": "Ceci est un bulletin météo radio simulé. Aucune alerte n'est transmise."
}
DEFAULT_CONFIG = {
    "application": "BMH-NOAA-Weather-Radio-Suite",
    "simulation_only": True,
    "region": "Northeast Illinois and Northwest Indiana",
    "station_id": "WXK89",
    "station_location": "Valparaiso, Indiana",
    "station_frequency_mhz": "162.400",
    "secondary_station_id": "KBB57",
    "secondary_station_location": "Gary, Indiana",
    "secondary_station_frequency_mhz": "162.425",
    "workstation_ip": "192.168.10.144",
    "workstation_port": 6000,
    "language": "English",
    "voice": "Paul",
    "voicetext_exe": "",
    "product_designator": "LOT",
    "wfo": "LOT",
    "wmo_ttaa_ii": "WWUS53",
    "wmo_bbb": "NOR",
    "bbb_version": "A",
    "addressee": "ALL",
    "same_codes": "ILC031, INC089, INC127",
    "listening_area": "Illinois and Indiana",
    "enable_listening_area_filter": True,
    "allow_routine_without_codes": True,
    "broadcast_mode": "General",
    "cycle_order": ["@AUTO_ID", "@ACTIVE_ALERTS", "@PRODUCT:ZFPLOT", "@PRODUCT:HWOLOT"]
}

def load_station_catalog():
    """Load the bundled companion catalog plus two requested local simulator profiles."""
    try:
        from noaa_stations_catalog import NOAA_STATIONS
        rows = [(name.replace("_", " "), dict(data)) for name, data in NOAA_STATIONS.items()]
    except Exception:
        rows = []
    rows.extend([
        ("WXK89 - Valparaiso (SIM)", {
            "callsign": "WXK89", "frequency": "162.400", "lat": 41.4731, "lon": -87.0611,
            "city": "Valparaiso", "state": "Indiana", "region": "midwest",
            "station_id": "WXK89", "description": "User-configured local simulation station",
            "voice": "paul", "simulation_profile": True
        }),
        ("KBB57 - Gary (SIM)", {
            "callsign": "KBB57", "frequency": "162.425", "lat": 41.5934, "lon": -87.3464,
            "city": "Gary", "state": "Indiana", "region": "midwest",
            "station_id": "KBB57", "description": "User-configured local simulation station",
            "voice": "paul", "simulation_profile": True
        })
    ])
    return rows

def save_json(path: Path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

def load_config():
    if not CONFIG_PATH.exists():
        save_json(CONFIG_PATH, DEFAULT_CONFIG)
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        merged = dict(DEFAULT_CONFIG)
        if isinstance(data, dict):
            merged.update(data)
        return merged
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULT_CONFIG)

def build_wmo_header(ttaa_ii, cccc, bbb, when=None):
    """Build an editable WMO-style simulation header line."""
    now = when or datetime.now(timezone.utc)
    valid_ttaa = (ttaa_ii or "WWUS53").strip().upper()
    valid_cccc = (cccc or "KLOT").strip().upper()
    stamp = now.strftime("%d%H%M")
    return " ".join(part for part in (valid_ttaa, valid_cccc, stamp, (bbb or "").strip().upper()) if part)

def priority_sort(alerts):
    return sorted(alerts, key=lambda x: (PRIORITY.get(x.get("hazard", "Statement"), 6), x.get("created", "")))

def make_alert_text(hazard, area, action, expires=""):
    parts = [hazard.upper()]
    if area.strip():
        parts.append("FOR " + area.strip().upper())
    if expires.strip():
        parts.append("UNTIL " + expires.strip())
    parts.extend(["", action.strip() or "This is a simulated alert message for software testing only.", "",
                  "THIS MESSAGE IS A SIMULATION. IT IS NOT AN OFFICIAL NWS PRODUCT."])
    return "\n".join(parts)

class BMHWeatherRadioSuite:
    def __init__(self, root):
        self.root = root
        self.config = load_config()
        self.stations = load_station_catalog()
        self.current_station = next((row for row in self.stations if row[1].get("callsign") == "WXK89"),
                                    self.stations[0] if self.stations else ("WXK89 - Valparaiso (SIM)", {}))
        self.alerts = []
        self.queue = []
        self.drafts = []
        self.sent_messages = []
        self.segments = []
        self.tx_simulation_running = False
        self.iid_station = {}
        self.iid_queue = {}
        self.status_text = tk.StringVar(value="READY - LOCAL SIMULATION ONLY")
        self.language_var = tk.StringVar(value=self.config.get("language", "English"))
        self.mode_var = tk.StringVar(value=self.config.get("broadcast_mode", "General"))
        self.hazard_var = tk.StringVar(value="Severe Thunderstorm Warning")
        self._setup_window()
        self._build_ui()
        self._refresh_all()
        self.root.after(1000, self._update_clock)

    def _setup_window(self):
        self.root.title("BMH NOAA Weather Radio Suite | LOTIEM / LOTWPS Simulation")
        self.root.geometry("1500x930")
        self.root.minsize(1180, 720)
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TNotebook.Tab", padding=(12, 7), font=("Segoe UI", 9, "bold"))
        style.configure("Treeview", rowheight=24, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))
        style.configure("Header.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("Subhead.TLabel", font=("Segoe UI", 10, "bold"))
        style.configure("Danger.TLabel", foreground="#b02020", font=("Segoe UI", 10, "bold"))
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        top = ttk.Frame(self.root, padding=(12, 10))
        top.pack(fill="x")
        ttk.Label(top, text="BMH NOAA WEATHER RADIO SUITE", style="Header.TLabel").pack(side="left")
        ttk.Label(top, text="LOTIEM TEXT WORKSTATION  •  LOTWPS  •  BMH", padding=(14, 4)).pack(side="left")
        ttk.Label(top, text="SIMULATION ONLY — NO RF / EAS TRANSMISSION", style="Danger.TLabel").pack(side="right")
        bar = ttk.Frame(self.root, padding=(12, 2, 12, 8)); bar.pack(fill="x")
        ttk.Label(bar, text="Region: Northeast IL / Northwest IN").pack(side="left")
        ttk.Label(bar, text="Station:").pack(side="left", padx=(16, 4))
        self.station_badge = ttk.Label(bar, text="WXK89 — Valparaiso, Indiana"); self.station_badge.pack(side="left")
        self.clock_label = ttk.Label(bar, text=""); self.clock_label.pack(side="right")
        self.tabs = ttk.Notebook(self.root); self.tabs.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        self.dashboard_tab = ttk.Frame(self.tabs, padding=8)
        self.text_tab = ttk.Frame(self.tabs, padding=8)
        self.network_tab = ttk.Frame(self.tabs, padding=8)
        self.cycles_tab = ttk.Frame(self.tabs, padding=8)
        self.settings_tab = ttk.Frame(self.tabs, padding=8)
        self.tabs.add(self.dashboard_tab, text="Dashboard")
        self.tabs.add(self.text_tab, text="KLOT LOTIEM TEXT WORKSTATION")
        self.tabs.add(self.network_tab, text="BMH Network")
        self.tabs.add(self.cycles_tab, text="Broadcast Cycles / Queue")
        self.tabs.add(self.settings_tab, text="Text_Workstation_Settings")
        self._build_dashboard(); self._build_text_workstation(); self._build_network()
        self._build_cycles(); self._build_settings()
        status = ttk.Frame(self.root, padding=(10, 4)); status.pack(fill="x")
        ttk.Label(status, textvariable=self.status_text).pack(side="left")
        ttk.Label(status, text="WXK89 / KBB57 are local simulation profiles").pack(side="right")

    def _build_dashboard(self):
        container = ttk.Frame(self.dashboard_tab); container.pack(fill="both", expand=True)
        cards = ttk.Frame(container); cards.pack(fill="x", pady=(0, 8))
        self.card_stations = ttk.Label(cards, text="Station profiles: —", style="Subhead.TLabel", padding=8); self.card_stations.pack(side="left", padx=(0, 8))
        self.card_alerts = ttk.Label(cards, text="Active alerts: 0", style="Subhead.TLabel", padding=8); self.card_alerts.pack(side="left", padx=8)
        self.card_queue = ttk.Label(cards, text="Live queue: 0", style="Subhead.TLabel", padding=8); self.card_queue.pack(side="left", padx=8)
        self.card_tx = ttk.Label(cards, text="TX simulation: STOPPED", style="Subhead.TLabel", padding=8); self.card_tx.pack(side="left", padx=8)
        body = ttk.Panedwindow(container, orient="horizontal"); body.pack(fill="both", expand=True)
        left = ttk.Frame(body, padding=4); right = ttk.Frame(body, padding=8)
        body.add(left, weight=3); body.add(right, weight=2)
        search = ttk.Frame(left); search.pack(fill="x", pady=(0, 6))
        ttk.Label(search, text="Station catalog search").pack(side="left")
        self.station_filter = tk.StringVar()
        filter_entry = ttk.Entry(search, textvariable=self.station_filter); filter_entry.pack(side="left", fill="x", expand=True, padx=8)
        filter_entry.bind("<KeyRelease>", lambda _e: self._populate_station_tree())
        ttk.Button(search, text="Clear", command=lambda: (self.station_filter.set(""), self._populate_station_tree())).pack(side="left")
        ttk.Label(left, text="Double-click a station for its controller. Seed data must be verified against official NWS listings.", wraplength=650).pack(anchor="w", pady=(0, 4))
        cols = ("city", "callsign", "state", "frequency", "station_id", "voice")
        self.station_tree = ttk.Treeview(left, columns=cols, show="headings", selectmode="browse")
        heads = {"city":"Station / City", "callsign":"Call Sign", "state":"State", "frequency":"MHz", "station_id":"Station ID", "voice":"Voice"}
        widths = {"city":210,"callsign":90,"state":130,"frequency":70,"station_id":90,"voice":70}
        for col in cols: self.station_tree.heading(col, text=heads[col]); self.station_tree.column(col, width=widths[col], anchor="w")
        y = ttk.Scrollbar(left, orient="vertical", command=self.station_tree.yview); self.station_tree.configure(yscrollcommand=y.set)
        self.station_tree.pack(side="left", fill="both", expand=True); y.pack(side="left", fill="y")
        self.station_tree.bind("<Double-1>", self._station_double_click)
        ttk.Label(right, text="Global Network Controls", style="Subhead.TLabel").pack(anchor="w")
        ttk.Label(right, text="Broadcast Action").pack(anchor="w", pady=(8, 2))
        self.dashboard_action = tk.StringVar(value="Update Periodic Scroll")
        ttk.Combobox(right, textvariable=self.dashboard_action, values=["Update Periodic Scroll", "Queue New Product", "Refresh Active Alerts"], state="readonly").pack(fill="x")
        ttk.Label(right, text="Hazard").pack(anchor="w", pady=(8, 2))
        ttk.Combobox(right, textvariable=self.hazard_var, values=HAZARDS, state="readonly").pack(fill="x")
        ttk.Label(right, text="Ticker Text").pack(anchor="w", pady=(8, 2))
        self.global_ticker = ttk.Entry(right); self.global_ticker.insert(0, "Simulated BMH Network — no live alert transmission"); self.global_ticker.pack(fill="x")
        row=ttk.Frame(right); row.pack(fill="x", pady=8)
        ttk.Button(row, text="Update Periodic Scroll", command=self._update_ticker).pack(side="left", padx=(0, 5))
        ttk.Button(row, text="Live NWS Alerts / Forecast", command=self._open_live_nws).pack(side="left", padx=(0, 5))
        ttk.Button(row, text="Live Current Observations", command=self._open_live_observations).pack(side="left", padx=(0, 5))
        ttk.Button(row, text="Live NWS Auto Monitor", command=self._open_live_monitor).pack(side="left", padx=(0, 5))
        ttk.Button(row, text="TRANSMIT (SIM)", command=self._simulate_transmit).pack(side="left")
        ttk.Separator(right).pack(fill="x", pady=10)
        ttk.Label(right, text="Active transmitters (simulated)", style="Subhead.TLabel").pack(anchor="w")
        self.active_tx_tree = ttk.Treeview(right, columns=("station","location","state"), show="headings", height=5)
        for c,h,w in [("station","Station ID",105),("location","Location",170),("state","Status",110)]:
            self.active_tx_tree.heading(c,text=h); self.active_tx_tree.column(c,width=w,anchor="w")
        self.active_tx_tree.pack(fill="x", pady=5)
        self.active_tx_tree.insert("", "end", iid="sim_wxk89", values=("WXK89", "Valparaiso, Indiana", "ONLINE (SIM)"))
        self.active_tx_tree.insert("", "end", iid="sim_kbb57", values=("KBB57", "Gary, Indiana", "ONLINE (SIM)"))
        self.active_tx_tree.bind("<Double-1>", self._active_tx_double_click)
        ttk.Button(right, text="Open selected Station Controller", command=self._open_selected_station_controller).pack(anchor="w", pady=5)
        ttk.Label(right, text="This panel never controls a physical transmitter.", style="Danger.TLabel", wraplength=380).pack(anchor="w", pady=(8, 0))

    def _open_live_monitor(self):
        """Open the polling live-alert monitor; only official NWS data is read."""
        try:
            from bmh_live_monitor import LiveMonitorWindow
            LiveMonitorWindow(self.root, default_areas="IL,IN")
            self._set_status("Live NWS auto monitor opened; no RF/EAS/public dispatch.")
        except Exception as exc:
            messagebox.showerror("Live NWS Auto Monitor", f"Could not open the live monitor: {exc}", parent=self.root)

    def _open_live_nws(self):
        """Open the read-only viewer backed by the real api.weather.gov service."""
        try:
            from bmh_live_nws import LiveNWSWindow
            LiveNWSWindow(self.root, on_insert_reference=self._insert_live_alert_reference)
            self._set_status("Live NWS viewer opened; official data is read-only and local.")
        except Exception as exc:
            messagebox.showerror("Live NWS Viewer", f"Could not open the live NWS viewer: {exc}", parent=self.root)

    def _open_live_observations(self):
        """Open current observations from the real NWS API in read-only mode."""
        try:
            from bmh_live_observations import LiveObservationsWindow
            LiveObservationsWindow(self.root, default_station="KVPZ")
            self._set_status("Live NWS observations opened; official data is read-only and local.")
        except Exception as exc:
            messagebox.showerror("Live NWS Observations", f"Could not open live observations: {exc}", parent=self.root)

    def _insert_live_alert_reference(self, reference_text):
        """Insert official live alert data as a labelled local reference, never as a sent product."""
        self.tabs.select(self.text_tab)
        self.editor.insert("insert", reference_text + "\n\n")
        self._set_status("Inserted live NWS reference copy in local editor. Nothing was dispatched.")

    def _build_text_workstation(self):
        outer = ttk.Frame(self.text_tab); outer.pack(fill="both", expand=True)
        header = ttk.LabelFrame(outer, text="AWIPS Header Block — simulated product", padding=8); header.pack(fill="x", pady=(0, 8))
        self.header_vars = {}
        fields = [("WMO Header (TTAAii)", "wmo_ttaa_ii", 12),("CCCC", "cccc", 7),("BBB", "wmo_bbb", 7),
                  ("BBB Version", "bbb_version", 7),("WSFO ID (optional)", "wfo_id", 8),
                  ("Product Designator", "product_designator", 8),("Addressee", "addressee", 8)]
        values = {"wmo_ttaa_ii":self.config.get("wmo_ttaa_ii","WWUS53"),"cccc":"KLOT",
                  "wmo_bbb":self.config.get("wmo_bbb","NOR"),"bbb_version":self.config.get("bbb_version","A"),
                  "wfo_id":"CHI","product_designator":self.config.get("product_designator","LOT"),
                  "addressee":self.config.get("addressee","ALL")}
        for i,(label,key,width) in enumerate(fields):
            col=i%7; ttk.Label(header,text=label).grid(row=0,column=col,sticky="w",padx=4)
            var=tk.StringVar(value=values.get(key,"")); self.header_vars[key]=var
            ttk.Entry(header,textvariable=var,width=width).grid(row=1,column=col,sticky="ew",padx=4,pady=(2,4)); header.columnconfigure(col,weight=1)
        ttk.Label(header,text="Product Category").grid(row=2,column=0,sticky="w",padx=4)
        self.category_var=tk.StringVar(value="Severe Thunderstorm Warning")
        ttk.Combobox(header,textvariable=self.category_var,values=HAZARDS,state="readonly",width=28).grid(row=3,column=0,columnspan=2,sticky="ew",padx=4)
        ttk.Button(header,text="Generate Automatically",command=self._generate_header).grid(row=3,column=2,padx=4,sticky="ew")
        ttk.Button(header,text="WarnGen / WatchGen",command=self.open_hazard_builder).grid(row=3,column=3,padx=4,sticky="ew")
        ttk.Button(header,text="KLOT Polygon Tool",command=self.open_polygon_tool).grid(row=3,column=4,padx=4,sticky="ew")
        ttk.Button(header,text="View Sent Alerts / Edit Sent Alerts",command=self._view_sent_messages).grid(row=3,column=5,columnspan=2,padx=4,sticky="ew")
        controls=ttk.LabelFrame(outer,text="New Text Message — Message Options",padding=6); controls.pack(fill="x",pady=(0,8))
        self.send_vars={}
        for col,(key,label) in enumerate([("bmh","Send to BMH"),("email","Send to Email"),("iembot","Send to IEMBOT"),("websites","Send to Websites & Outlets")]):
            v=tk.BooleanVar(value=(key=="bmh")); self.send_vars[key]=v; ttk.Checkbutton(controls,text=label,variable=v).grid(row=0,column=col,sticky="w",padx=8)
        ttk.Label(controls,text="Wrap chat edits (characters)").grid(row=0,column=4,padx=(14,3))
        self.wrap_var=tk.IntVar(value=80); ttk.Spinbox(controls,from_=20,to=160,textvariable=self.wrap_var,width=5,command=self._wrap_editor).grid(row=0,column=5)
        ttk.Button(controls,text="Enter Editor Mode",command=self._focus_editor).grid(row=0,column=6,padx=8)
        body=ttk.Panedwindow(outer,orient="horizontal"); body.pack(fill="both",expand=True)
        edit_frame=ttk.Frame(body,padding=(0,0,6,0)); side=ttk.Frame(body,padding=(6,0,0,0))
        body.add(edit_frame,weight=3); body.add(side,weight=2)
        ttk.Label(edit_frame,text="Message / Product Editor",style="Subhead.TLabel").pack(anchor="w")
        editor_box=ttk.Frame(edit_frame); editor_box.pack(fill="both",expand=True,pady=4)
        self.editor=tk.Text(editor_box,wrap="word",undo=True,font=("Consolas",10),height=20); self.editor.pack(side="left",fill="both",expand=True)
        edit_scroll=ttk.Scrollbar(editor_box,orient="vertical",command=self.editor.yview); edit_scroll.pack(side="right",fill="y"); self.editor.configure(yscrollcommand=edit_scroll.set)
        self.context_menu=tk.Menu(self.root,tearoff=0)
        for label,fn in [("Add Segment",self._add_segment),("Edit Segment",self._edit_segment),("Remove Segment",self._remove_segment),("Combine Segment",self._combine_segments)]:
            self.context_menu.add_command(label=label,command=fn)
        self.editor.bind("<Button-3>",self._show_editor_menu)
        buttons=ttk.Frame(edit_frame); buttons.pack(fill="x",pady=4)
        for label,cmd in [("Save Draft",self._save_draft),("Dispatch (SIM)",self._dispatch_message),("Add New Hazard Segment",self.open_hazard_builder),
                          ("Add Hazard to Existing Segment",self.open_hazard_builder),("Build SAME / EAS",self.open_same_builder),("Preview Tone (local)",self._preview_tone)]:
            ttk.Button(buttons,text=label,command=cmd).pack(side="left",padx=(0,4),pady=2)
        ttk.Label(side,text="AWIPS Active Alerts — Unified",style="Subhead.TLabel").pack(anchor="w")
        self.alert_tree=ttk.Treeview(side,columns=("id","hazard","action","expires"),show="headings",height=9)
        for c,h,w in [("id","Alert ID",90),("hazard","Hazard",180),("action","Action",60),("expires","Expires",140)]:
            self.alert_tree.heading(c,text=h); self.alert_tree.column(c,width=w,anchor="w")
        self.alert_tree.pack(fill="both",expand=True,pady=4)
        row=ttk.Frame(side); row.pack(fill="x")
        for label,cmd in [("Refresh List",self._refresh_alerts),("Edit Selected",self._edit_selected_alert),("SAME Retone",self.open_same_builder),("1050 HZ",self._preview_tone),("Silent Interrupt",self._silent_interrupt)]:
            ttk.Button(row,text=label,command=cmd).pack(side="left",padx=2,pady=2)
        ttk.Label(side,text="Official product routing is disabled. Destinations are recorded as local dispatch intents only.",style="Danger.TLabel",wraplength=380).pack(anchor="w",pady=5)

    def _build_network(self):
        body=ttk.Frame(self.network_tab); body.pack(fill="both",expand=True)
        left=ttk.Frame(body,padding=6); right=ttk.Frame(body,padding=6)
        left.pack(side="left",fill="both",expand=True); right.pack(side="left",fill="both",expand=True)
        ttk.Label(left,text="Global Network Controls",style="Subhead.TLabel").pack(anchor="w")
        g=ttk.LabelFrame(left,text="Broadcast Action",padding=8); g.pack(fill="x",pady=6)
        self.network_action=tk.StringVar(value="Update Periodic Scroll")
        ttk.Combobox(g,textvariable=self.network_action,values=["Update Periodic Scroll","Refresh station status","Queue new product"],state="readonly").pack(fill="x",pady=3)
        ttk.Label(g,text="Hazard").pack(anchor="w",pady=(6,2))
        self.network_hazard=tk.StringVar(value="Severe Thunderstorm Warning")
        ttk.Combobox(g,textvariable=self.network_hazard,values=HAZARDS,state="readonly").pack(fill="x")
        ttk.Label(g,text="Ticker Text").pack(anchor="w",pady=(6,2))
        self.network_ticker=ttk.Entry(g); self.network_ticker.insert(0,"Simulated BMH Network — no live transmission"); self.network_ticker.pack(fill="x")
        row=ttk.Frame(g); row.pack(fill="x",pady=6)
        ttk.Button(row,text="Update Periodic Scroll",command=self._update_ticker).pack(side="left",padx=(0,5))
        ttk.Button(row,text="TRANSMIT (SIM)",command=self._simulate_transmit).pack(side="left")
        ttk.Label(left,text="Active Transmitters",style="Subhead.TLabel").pack(anchor="w",pady=(8,2))
        self.network_tx_tree=ttk.Treeview(left,columns=("id","location","frequency","status"),show="headings",height=9)
        for c,h,w in [("id","Station ID",95),("location","Location",180),("frequency","MHz",75),("status","Status",115)]:
            self.network_tx_tree.heading(c,text=h); self.network_tx_tree.column(c,width=w,anchor="w")
        self.network_tx_tree.pack(fill="both",expand=True)
        for iid,rowdata in [("wxk89",("WXK89","Valparaiso, Indiana","162.400","ONLINE (SIM)")),("kbb57",("KBB57","Gary, Indiana","162.425","ONLINE (SIM)"))]:
            self.network_tx_tree.insert("", "end",iid=iid,values=rowdata)
        self.network_tx_tree.bind("<Double-1>",self._active_tx_double_click)
        ttk.Button(left,text="Open selected Station Controller",command=self._open_selected_station_controller).pack(anchor="w",pady=5)
        ttk.Label(right,text="Weather Message / Alert Console",style="Subhead.TLabel").pack(anchor="w")
        ttk.Label(right,text="Hazard Category").pack(anchor="w",pady=(6,2))
        self.network_hazard2=tk.StringVar(value="Severe Thunderstorm Warning")
        ttk.Combobox(right,textvariable=self.network_hazard2,values=HAZARDS,state="readonly").pack(fill="x")
        ttk.Label(right,text="Warning Message / Call to Action Text").pack(anchor="w",pady=(6,2))
        self.network_message=tk.Text(right,height=7,wrap="word"); self.network_message.pack(fill="x")
        self.network_message.insert("1.0","This is a simulation-only message. Verify all alert facts before use.")
        ttk.Label(right,text="SAME / EAS Builder").pack(anchor="w",pady=(8,2))
        row=ttk.Frame(right); row.pack(fill="x")
        ttk.Button(row,text="Open SAME / EAS Builder",command=self.open_same_builder).pack(side="left",padx=(0,5))
        ttk.Button(row,text="Preview 1050 Hz",command=self._preview_tone).pack(side="left")
        ttk.Label(right,text="Test Alerts").pack(anchor="w",pady=(8,2))
        row=ttk.Frame(right); row.pack(fill="x")
        ttk.Button(row,text="Required Monthly Test",command=lambda:self._create_alert("Required Monthly Test",message="Monthly test — simulation only.")).pack(side="left",padx=(0,5))
        ttk.Button(row,text="Required Weekly Test (Wednesday)",command=lambda:self._create_alert("Required Weekly Test",message="Weekly test — simulation only.")).pack(side="left")
        ttk.Label(right,text="All transmit controls only change simulator state. Do not connect to a real transmitter.",style="Danger.TLabel",wraplength=500).pack(anchor="w",pady=10)

    def _build_cycles(self):
        body=ttk.Panedwindow(self.cycles_tab,orient="horizontal"); body.pack(fill="both",expand=True)
        left=ttk.Frame(body,padding=5); right=ttk.Frame(body,padding=5)
        body.add(left,weight=1); body.add(right,weight=2)
        ttk.Label(left,text="Broadcast Cycles",style="Subhead.TLabel").pack(anchor="w")
        ttk.Label(left,text="Broadcast Mode").pack(anchor="w",pady=(6,2))
        ttk.Combobox(left,textvariable=self.mode_var,values=MODES,state="readonly").pack(fill="x")
        row=ttk.Frame(left); row.pack(fill="x",pady=6)
        ttk.Button(row,text="NEW MODE",command=self._new_mode).pack(side="left",padx=(0,4))
        ttk.Button(row,text="DELETE MODE",command=self._delete_mode).pack(side="left",padx=4)
        ttk.Button(row,text="RESET MODE",command=self._reset_mode).pack(side="left",padx=4)
        ttk.Label(left,text="Available Entries").pack(anchor="w",pady=(8,2))
        self.entries_list=tk.Listbox(left,height=10,exportselection=False)
        for item in CYCLE_ENTRIES:self.entries_list.insert("end",item)
        self.entries_list.pack(fill="both",expand=True)
        ttk.Button(left,text="Add selected entry to cycle",command=self._add_cycle_entry).pack(anchor="w",pady=5)
        ttk.Label(left,text="Cycle Order").pack(anchor="w",pady=(6,2))
        self.cycle_tree=ttk.Treeview(left,columns=("order","entry"),show="headings",height=6)
        self.cycle_tree.heading("order",text="#"); self.cycle_tree.column("order",width=35)
        self.cycle_tree.heading("entry",text="Message / Product"); self.cycle_tree.column("entry",width=280)
        self.cycle_tree.pack(fill="both",expand=True)
        row=ttk.Frame(left); row.pack(fill="x",pady=5)
        ttk.Button(row,text="Move Up",command=lambda:self._move_cycle(-1)).pack(side="left",padx=2)
        ttk.Button(row,text="Move Down",command=lambda:self._move_cycle(1)).pack(side="left",padx=2)
        ttk.Button(row,text="Remove",command=self._remove_cycle_entry).pack(side="left",padx=2)
        ttk.Label(right,text="Static Messages",style="Subhead.TLabel").pack(anchor="w")
        self.static_list=ttk.Treeview(right,columns=("id","description"),show="headings",height=6)
        self.static_list.heading("id",text="Static Message ID"); self.static_list.column("id",width=220)
        self.static_list.heading("description",text="Action"); self.static_list.column("description",width=260)
        self.static_list.pack(fill="x",pady=4)
        for p in PRODUCT_IDS:self.static_list.insert("", "end",values=(p,"Read / preview locally"))
        ttk.Label(right,text="Live Queue",style="Subhead.TLabel").pack(anchor="w",pady=(8,2))
        self.queue_tree=ttk.Treeview(right,columns=("n","id","product","status"),show="headings",height=10)
        for c,h,w in [("n","#",35),("id","Product ID",140),("product","Message / Product",360),("status","Status",130)]:
            self.queue_tree.heading(c,text=h); self.queue_tree.column(c,width=w,anchor="w")
        self.queue_tree.pack(fill="both",expand=True)
        row=ttk.Frame(right); row.pack(fill="x",pady=5)
        ttk.Button(row,text="REFRESH NOW",command=self._refresh_queue).pack(side="left",padx=2)
        ttk.Button(row,text="READ SELECTED NOW",command=self._read_selected_queue).pack(side="left",padx=2)
        ttk.Button(row,text="LOOP SELECTED",command=self._loop_selected_queue).pack(side="left",padx=2)
        ttk.Button(row,text="STOP LOOP",command=self._stop_loop).pack(side="left",padx=2)
        ttk.Button(row,text="Add Current Editor Product",command=self._dispatch_message).pack(side="left",padx=2)
        ttk.Label(right,text="Queue read/loop actions are simulated; no audio transmitter is attached.",style="Danger.TLabel").pack(anchor="w",pady=4)

    def _build_settings(self):
        body=ttk.Frame(self.settings_tab,padding=12); body.pack(fill="both",expand=True)
        ttk.Label(body,text="Text_Workstation_Settings",style="Header.TLabel").grid(row=0,column=0,columnspan=4,sticky="w",pady=(0,12))
        self.setting_vars={}
        fields=[
            ("IP Address / Display Host","workstation_ip"),("IP Port","workstation_port"),
            ("Primary Station ID","station_id"),("Primary Location","station_location"),
            ("Primary Frequency (MHz)","station_frequency_mhz"),("Secondary Station ID","secondary_station_id"),
            ("Secondary Location","secondary_station_location"),("Secondary Frequency (MHz)","secondary_station_frequency_mhz"),
            ("WFO / Office","wfo"),("Product Designator","product_designator"),
            ("VoiceText EXE Path (optional)","voicetext_exe"),("Listening Area","listening_area"),
            ("SAME / FIPS / UGC Codes (editable)","same_codes")
        ]
        for i,(label,key) in enumerate(fields):
            r=1+(i//2)*2; c=(i%2)*2
            ttk.Label(body,text=label).grid(row=r,column=c,sticky="w",padx=(0,8),pady=(2,0))
            var=tk.StringVar(value=str(self.config.get(key,""))); self.setting_vars[key]=var
            ttk.Entry(body,textvariable=var,width=44).grid(row=r+1,column=c,columnspan=2,sticky="ew",padx=(0,20),pady=(2,7))
            body.columnconfigure(c,weight=1); body.columnconfigure(c+1,weight=1)
        r=15
        ttk.Label(body,text="Broadcast Language").grid(row=r,column=0,sticky="w")
        self.setting_vars["language"]=tk.StringVar(value=self.language_var.get())
        ttk.Combobox(body,textvariable=self.setting_vars["language"],values=LANGUAGES,state="readonly",width=20).grid(row=r+1,column=0,sticky="w",pady=(2,8))
        ttk.Label(body,text="TTS Voice").grid(row=r,column=1,sticky="w")
        self.setting_vars["voice"]=tk.StringVar(value=self.config.get("voice","Paul"))
        ttk.Combobox(body,textvariable=self.setting_vars["voice"],values=["Tom","Paul","Harry","Donna"],state="readonly",width=20).grid(row=r+1,column=1,sticky="w",pady=(2,8))
        self.filter_var=tk.BooleanVar(value=bool(self.config.get("enable_listening_area_filter",True)))
        self.routine_var=tk.BooleanVar(value=bool(self.config.get("allow_routine_without_codes",True)))
        ttk.Checkbutton(body,text="Enable listening-area filtering",variable=self.filter_var).grid(row=17,column=0,sticky="w",pady=3)
        ttk.Checkbutton(body,text="Allow routine products without FIPS or zone coding",variable=self.routine_var).grid(row=17,column=1,sticky="w",pady=3)
        row=ttk.Frame(body); row.grid(row=18,column=0,columnspan=4,sticky="w",pady=10)
        ttk.Button(row,text="Save Settings to JSON",command=self._save_settings).pack(side="left",padx=(0,5))
        ttk.Button(row,text="Restore Defaults",command=self._restore_settings).pack(side="left",padx=5)
        ttk.Button(row,text="Open VoiceText EXE…",command=self._browse_voicetext).pack(side="left",padx=5)
        ttk.Button(row,text="Preview Language Template",command=self._preview_language).pack(side="left",padx=5)
        ttk.Label(body,text="Safety: IP/port are saved as settings only. No socket listener, email, IEMBOT, website, or radio integration is active.",style="Danger.TLabel",wraplength=1000).grid(row=19,column=0,columnspan=4,sticky="w",pady=(10,0))

    def _update_clock(self):
        self.clock_label.configure(text="Local workstation time: " + datetime.now().astimezone().strftime("%a %Y-%m-%d %H:%M:%S %Z"))
        self.root.after(1000,self._update_clock)

    def _set_status(self,message): self.status_text.set(message)

    def _refresh_all(self):
        self._populate_station_tree(); self._refresh_alerts(); self._refresh_queue(); self._refresh_cycle_tree()
        self.card_stations.configure(text=f"Station profiles: {len(self.stations)}")
        self.card_alerts.configure(text=f"Active alerts: {len(self.alerts)}")
        self.card_queue.configure(text=f"Live queue: {len(self.queue)}")
        self.card_tx.configure(text="TX simulation: RUNNING" if self.tx_simulation_running else "TX simulation: STOPPED")
        data=self.current_station[1]
        self.station_badge.configure(text=f"{data.get('callsign','WXK89')} — {data.get('city','Valparaiso')}, {data.get('state','Indiana')}")

    def _populate_station_tree(self):
        if not hasattr(self,"station_tree"):return
        q=self.station_filter.get().strip().lower() if hasattr(self,"station_filter") else ""
        self.station_tree.delete(*self.station_tree.get_children()); self.iid_station={}
        for i,(name,data) in enumerate(self.stations):
            alltext=" ".join([name,str(data.get("callsign","")),str(data.get("state","")),str(data.get("station_id","")),str(data.get("frequency",""))]).lower()
            if q and q not in alltext:continue
            iid=f"station_{i}"; self.iid_station[iid]=(name,data)
            self.station_tree.insert("", "end",iid=iid,values=(name,data.get("callsign",""),data.get("state",""),data.get("frequency",""),data.get("station_id",""),str(data.get("voice","")).title()))

    def _get_selected_station(self):
        selection=self.station_tree.selection() if hasattr(self,"station_tree") else ()
        if selection and selection[0] in self.iid_station:self.current_station=self.iid_station[selection[0]]
        return self.current_station

    def _station_double_click(self,_event=None):
        self._get_selected_station(); self._open_station_controller(self.current_station)

    def _active_tx_double_click(self,event=None):
        widget=event.widget if event is not None else self.active_tx_tree
        selected=widget.selection() if widget is not None else ()
        iid=selected[0] if selected else ""
        station_id="KBB57" if iid in ("sim_kbb57","kbb57") else "WXK89"
        self.current_station=self._station_profile(station_id); self._open_station_controller(self.current_station)

    def _station_profile(self,station_id):
        name="WXK89 - Valparaiso (SIM)" if station_id=="WXK89" else "KBB57 - Gary (SIM)"
        row=next((x for x in self.stations if x[0]==name),None)
        return row or (name,{"callsign":station_id,"station_id":station_id,"city":"Valparaiso" if station_id=="WXK89" else "Gary","state":"Indiana","frequency":"162.400" if station_id=="WXK89" else "162.425","voice":"paul","simulation_profile":True})

    def _open_selected_station_controller(self):
        selected_tab = self.tabs.select()
        if selected_tab == str(self.network_tab) and self.network_tx_tree.selection():
            iid = self.network_tx_tree.selection()[0]
            self.current_station = self._station_profile("KBB57" if iid == "kbb57" else "WXK89")
        elif selected_tab == str(self.dashboard_tab) and self.active_tx_tree.selection():
            iid = self.active_tx_tree.selection()[0]
            self.current_station = self._station_profile("KBB57" if iid == "sim_kbb57" else "WXK89")
        elif hasattr(self,"station_tree") and self.station_tree.selection():
            self._get_selected_station()
        self._refresh_all()
        self._open_station_controller(self.current_station)

    def _open_station_controller(self,station):
        name,data=station
        win=tk.Toplevel(self.root); win.title(f"BMH Station Controller - {data.get('callsign','UNKNOWN')}"); win.geometry("850x740")
        online="ONLINE (SIM)" if data.get("simulation_profile") else "CATALOG PROFILE"
        ttk.Label(win,text=f"STATION: {data.get('callsign','UNKNOWN')}   {online}",style="Header.TLabel",padding=8).pack(anchor="w")
        ttk.Label(win,text=f"{data.get('city',name)}, {data.get('state','')}  |  {data.get('frequency','')} MHz  |  Station ID: {data.get('station_id','')}").pack(anchor="w",padx=10)
        ttk.Label(win,text="Simulation only: Start/Stop changes GUI state and does not control RF equipment.",style="Danger.TLabel",padding=8).pack(anchor="w")
        notebook=ttk.Notebook(win); notebook.pack(fill="both",expand=True,padx=8,pady=8)
        controls=ttk.Frame(notebook,padding=8); weather=ttk.Frame(notebook,padding=8); products=ttk.Frame(notebook,padding=8); area=ttk.Frame(notebook,padding=8)
        notebook.add(controls,text="Transmitter Control"); notebook.add(weather,text="Weather Message"); notebook.add(products,text="@Products / Queue"); notebook.add(area,text="Listening Area")
        state={"running":False}; state_label=ttk.Label(controls,text="STATION OFFLINE (SIM)",style="Subhead.TLabel"); state_label.pack(anchor="w",pady=4)
        def toggle_tx(on):
            state["running"]=on; state_label.configure(text="STATION ONLINE (SIM)" if on else "STATION OFFLINE (SIM)")
            self._set_status(f"{data.get('callsign')} local TX simulation {'started' if on else 'stopped'}")
        row=ttk.Frame(controls); row.pack(anchor="w",pady=4)
        ttk.Button(row,text="START TX (SIM)",command=lambda:toggle_tx(True)).pack(side="left",padx=3)
        ttk.Button(row,text="STOP TX",command=lambda:toggle_tx(False)).pack(side="left",padx=3)
        ttk.Button(row,text="NEXT PRODUCT",command=lambda:self._queue_product("CURRENT_TIME","Current time")).pack(side="left",padx=3)
        ttk.Button(row,text="RESTART SERVICE (SIM)",command=lambda:toggle_tx(False)).pack(side="left",padx=3)
        mode=tk.StringVar(value=self.mode_var.get()); ttk.Label(controls,text="Operational Mode").pack(anchor="w",pady=(12,2))
        ttk.Combobox(controls,textvariable=mode,values=MODES,state="readonly",width=35).pack(anchor="w")
        ttk.Button(controls,text="Apply Mode",command=lambda:(self.mode_var.set(mode.get()),self._set_status(f"Mode set to {mode.get()} (simulation)"))).pack(anchor="w",pady=4)
        quick=ttk.LabelFrame(controls,text="Quick Read Internal IDs",padding=6); quick.pack(fill="x",pady=8)
        for key in ["STATION_ID","CURRENT_TIME","SVR_STATION_ID","SEVERE_MESSAGE","NWSLOT","SUMMARY","EMR_STATION_ID","PREPAREDNESS_ACTIONS"]:
            ttk.Button(quick,text=key,command=lambda k=key:self._queue_product(k,k.replace("_"," ").title())).pack(side="left",padx=2,pady=2)
        ttk.Label(weather,text="Hazard Category").pack(anchor="w")
        h=tk.StringVar(value=self.hazard_var.get()); ttk.Combobox(weather,textvariable=h,values=HAZARDS,state="readonly",width=36).pack(anchor="w",pady=3)
        ttk.Label(weather,text="Warning Message / Call to Action Text").pack(anchor="w",pady=(8,2))
        msg=tk.Text(weather,height=9,wrap="word"); msg.pack(fill="both",expand=True); msg.insert("1.0","This is a simulated warning message. Please verify all details.")
        row=ttk.Frame(weather); row.pack(fill="x",pady=6)
        ttk.Button(row,text="Add Hazard",command=lambda:self._create_alert(h.get(),message=msg.get("1.0","end").strip())).pack(side="left",padx=3)
        ttk.Button(row,text="WarnGen / WatchGen",command=self.open_hazard_builder).pack(side="left",padx=3)
        ttk.Button(row,text="SAME / EAS Builder",command=self.open_same_builder).pack(side="left",padx=3)
        p_list=tk.Listbox(products,height=9); p_list.pack(fill="both",expand=True)
        for p in PRODUCT_IDS:p_list.insert("end",p)
        row=ttk.Frame(products); row.pack(fill="x",pady=5)
        ttk.Button(row,text="READ NOW",command=lambda:self._queue_product(p_list.get(p_list.curselection()[0]) if p_list.curselection() else "CURRENT_TIME","Station product")).pack(side="left",padx=3)
        ttk.Button(row,text="LOOP PRODUCT",command=lambda:self._set_status("Selected product loop started (simulated)")).pack(side="left",padx=3)
        ttk.Button(row,text="STOP LOOP",command=lambda:self._set_status("Product loop stopped (simulated)")).pack(side="left",padx=3)
        ttk.Label(area,text="Station Coverage Behavior",style="Subhead.TLabel").pack(anchor="w")
        f=tk.BooleanVar(value=self.filter_var.get()); r=tk.BooleanVar(value=self.routine_var.get())
        ttk.Checkbutton(area,text="Enable listening-area filtering",variable=f).pack(anchor="w",pady=3)
        ttk.Checkbutton(area,text="Allow routine products without FIPS or zone coding",variable=r).pack(anchor="w",pady=3)
        ttk.Label(area,text="Listening area text").pack(anchor="w",pady=(8,2))
        area_text=tk.Text(area,height=8,wrap="word"); area_text.pack(fill="both",expand=True); area_text.insert("1.0",self.config.get("listening_area","Illinois and Indiana"))
        ttk.Button(area,text="Save station listening settings",command=lambda:self._set_status("Station listening-area settings saved in UI session")).pack(anchor="w",pady=4)

    def _generate_header(self):
        wmo=build_wmo_header(self.header_vars["wmo_ttaa_ii"].get(),self.header_vars["cccc"].get(),self.header_vars["wmo_bbb"].get())
        version=self.header_vars["bbb_version"].get().strip(); office=self.header_vars["wfo_id"].get().strip()
        designator=self.header_vars["product_designator"].get().strip(); addressee=self.header_vars["addressee"].get().strip()
        header=wmo+"\n"
        if office:header+=f"WSFO: {office}\n"
        if version:header+=f"BBB VERSION: {version}\n"
        if designator:header+=f"PRODUCT DESIGNATOR: {designator}\n"
        if addressee:header+=f"ADDRESSEE: {addressee}\n"
        header+="\n"; self.editor.insert("1.0",header); self._set_status("Generated editable WMO-style simulation header. Review before saving.")

    def _focus_editor(self):
        self.tabs.select(self.text_tab); self.editor.focus_set()

    def _wrap_editor(self):
        self.editor.configure(wrap="word" if self.wrap_var.get()>=20 else "none")

    def _show_editor_menu(self,event):
        try:
            self.editor.mark_set("insert",f"@{event.x},{event.y}"); self.context_menu.tk_popup(event.x_root,event.y_root)
        finally:self.context_menu.grab_release()

    def _add_segment(self):
        try:text=self.editor.get("sel.first","sel.last")
        except tk.TclError:text=""
        if not text.strip():
            messagebox.showinfo("Add Segment","Select text in the editor first, then right-click and choose Add Segment."); return
        self.segments.append(text); self._set_status(f"Added segment #{len(self.segments)} to local segment list.")

    def _edit_segment(self):
        try:old=self.editor.get("sel.first","sel.last")
        except tk.TclError:
            messagebox.showinfo("Edit Segment","Select the segment text first."); return
        new=simpledialog.askstring("Edit Segment","Edit selected segment:",initialvalue=old,parent=self.root)
        if new is not None:self.editor.delete("sel.first","sel.last"); self.editor.insert("insert",new); self._set_status("Edited selected text segment.")

    def _remove_segment(self):
        try:self.editor.delete("sel.first","sel.last"); self._set_status("Removed selected segment text.")
        except tk.TclError:messagebox.showinfo("Remove Segment","Select text first.")

    def _combine_segments(self):
        try:text=self.editor.get("sel.first","sel.last")
        except tk.TclError:messagebox.showinfo("Combine Segment","Select text segments to combine first."); return
        combined=" ".join(part.strip() for part in text.splitlines() if part.strip())
        self.editor.delete("sel.first","sel.last"); self.editor.insert("insert",combined); self._set_status("Combined selected lines into one text segment.")

    def open_hazard_builder(self):
        win=tk.Toplevel(self.root); win.title("Build Hazard Segment — WarnGen / WatchGen"); win.geometry("640x590")
        ttk.Label(win,text="Weather Generator / Hazard Segment Builder",style="Header.TLabel",padding=10).pack(anchor="w")
        ttk.Label(win,text="Simulation tool only; polygon and message text are not sent to operational systems.",style="Danger.TLabel",padding=8).pack(anchor="w")
        form=ttk.Frame(win,padding=10); form.pack(fill="both",expand=True)
        hazard=tk.StringVar(value=self.category_var.get()); area=tk.StringVar(value="Northeast Illinois and Northwest Indiana")
        expires=tk.StringVar(value="6:00 PM CDT"); headline=tk.StringVar(value="Severe weather may impact the area.")
        ttk.Label(form,text="Hazard / Product").grid(row=0,column=0,sticky="w")
        ttk.Combobox(form,textvariable=hazard,values=HAZARDS,state="readonly",width=34).grid(row=0,column=1,sticky="ew",pady=3)
        ttk.Label(form,text="Area / Counties").grid(row=1,column=0,sticky="w")
        ttk.Entry(form,textvariable=area,width=45).grid(row=1,column=1,sticky="ew",pady=3)
        ttk.Label(form,text="Expiration (editable)").grid(row=2,column=0,sticky="w")
        ttk.Entry(form,textvariable=expires,width=24).grid(row=2,column=1,sticky="w",pady=3)
        ttk.Label(form,text="Headline / Warning Message").grid(row=3,column=0,sticky="nw")
        ttk.Entry(form,textvariable=headline).grid(row=3,column=1,sticky="ew",pady=3)
        ttk.Label(form,text="Call to Action").grid(row=4,column=0,sticky="nw")
        action=tk.Text(form,height=10,wrap="word"); action.grid(row=4,column=1,sticky="nsew",pady=3)
        action.insert("1.0","Move to a safe location if threatening weather approaches. Monitor official alerts.")
        form.columnconfigure(1,weight=1); form.rowconfigure(4,weight=1)
        def insert_segment():
            text=make_alert_text(hazard.get(),area.get(),headline.get()+"\n"+action.get("1.0","end").strip(),expires.get())
            self.editor.insert("insert",text+"\n\n"); self.category_var.set(hazard.get())
            self._set_status("Hazard segment inserted into editor (simulation)."); win.destroy(); self.tabs.select(self.text_tab)
        row=ttk.Frame(win,padding=10); row.pack(fill="x")
        ttk.Button(row,text="Open KLOT Polygon Tool",command=self.open_polygon_tool).pack(side="left",padx=3)
        ttk.Button(row,text="Build Hazard Segment / Insert",command=insert_segment).pack(side="right",padx=3)

    def open_polygon_tool(self):
        win=tk.Toplevel(self.root); win.title("KLOT Polygon Tool — schematic only"); win.geometry("840x670")
        ttk.Label(win,text="KLOT Polygon Tool | WarnGen / WatchGen",style="Header.TLabel",padding=8).pack(anchor="w")
        ttk.Label(win,text="SCHEMATIC CANVAS — no live radar, rotation feed, or authoritative warning polygon.",style="Danger.TLabel",padding=6).pack(anchor="w")
        top=ttk.Frame(win,padding=6); top.pack(fill="x"); kind=tk.StringVar(value="Single Storm")
        ttk.Label(top,text="Polygon Type").pack(side="left")
        ttk.Combobox(top,textvariable=kind,values=["Single Storm","Line of Storms"],state="readonly",width=18).pack(side="left",padx=6)
        ttk.Label(top,text="Approximate coordinates only.").pack(side="left",padx=10)
        canvas=tk.Canvas(win,width=800,height=440,background="#e7edf2",highlightthickness=1,highlightbackground="#8b9aa8")
        canvas.pack(fill="both",expand=True,padx=8,pady=6)
        canvas.create_text(400,20,text="NE ILLINOIS / NW INDIANA — NOT LIVE RADAR",fill="#465568",font=("Segoe UI",12,"bold"))
        for x in range(40,800,40):canvas.create_line(x,40,x,430,fill="#d4dde5")
        for y in range(60,440,40):canvas.create_line(0,y,800,y,fill="#d4dde5")
        points=[]; coords_label=tk.StringVar(value="LAT...LON: (click canvas to add points)")
        ttk.Label(win,textvariable=coords_label,padding=6).pack(anchor="w")
        def redraw():
            canvas.delete("poly")
            for i,(x,y) in enumerate(points):
                canvas.create_oval(x-4,y-4,x+4,y+4,fill="#1f5a86",outline="",tags="poly")
                if i:canvas.create_line(points[i-1][0],points[i-1][1],x,y,fill="#d33",width=2,tags="poly")
            if len(points)>2:canvas.create_line(points[-1][0],points[-1][1],points[0][0],points[0][1],fill="#d33",dash=(4,3),tags="poly")
            w=max(canvas.winfo_width(),1); h=max(canvas.winfo_height(),1); coords=[]
            for x,y in points:coords.append(f"{42.45-(y/h)*1.25:.4f},{-89.95+(x/w)*2.05:.4f}")
            coords_label.set("LAT...LON: "+" ".join(coords) if coords else "LAT...LON: (click canvas to add points)")
        canvas.bind("<Button-1>",lambda e:(points.append((e.x,e.y)),redraw()))
        row=ttk.Frame(win,padding=6); row.pack(fill="x")
        def use_points():
            if len(points)<3:messagebox.showwarning("Polygon","Add at least three points.",parent=win); return
            w=max(canvas.winfo_width(),1); h=max(canvas.winfo_height(),1); coords=[]
            for x,y in points:coords.append(f"{42.45-(y/h)*1.25:.4f},{-89.95+(x/w)*2.05:.4f}")
            self.editor.insert("insert",f"{kind.get()} polygon (schematic):\nLAT...LON: "+" ".join(coords)+"\n")
            self._set_status("Schematic polygon coordinates inserted; not for operational warning use."); win.destroy(); self.tabs.select(self.text_tab)
        ttk.Button(row,text="Undo Point",command=lambda:(points.pop() if points else None,redraw())).pack(side="left",padx=3)
        ttk.Button(row,text="Clear Polygon",command=lambda:(points.clear(),redraw())).pack(side="left",padx=3)
        ttk.Button(row,text="Insert LAT...LON into Message",command=use_points).pack(side="right",padx=3)

    def open_same_builder(self):
        win=tk.Toplevel(self.root); win.title("SAME / EAS Builder — simulator"); win.geometry("650x540")
        ttk.Label(win,text="SAME / EAS Builder",style="Header.TLabel",padding=10).pack(anchor="w")
        ttk.Label(win,text="Local preview only. Does not create a valid OTA alert or connect to an EAS encoder.",style="Danger.TLabel",padding=8).pack(anchor="w")
        body=ttk.Frame(win,padding=10); body.pack(fill="both",expand=True)
        codes=tk.StringVar(value=self.config.get("same_codes","ILC031, INC089, INC127"))
        hazard=tk.StringVar(value=self.hazard_var.get()); duration=tk.StringVar(value="0015")
        ttk.Label(body,text="SAME / FIPS / UGC area codes").grid(row=0,column=0,sticky="w")
        ttk.Entry(body,textvariable=codes).grid(row=0,column=1,sticky="ew",pady=3)
        ttk.Label(body,text="Event / Hazard").grid(row=1,column=0,sticky="w")
        ttk.Combobox(body,textvariable=hazard,values=HAZARDS,state="readonly").grid(row=1,column=1,sticky="ew",pady=3)
        ttk.Label(body,text="Duration (HHMM, editable)").grid(row=2,column=0,sticky="w")
        ttk.Entry(body,textvariable=duration,width=10).grid(row=2,column=1,sticky="w",pady=3)
        ttk.Label(body,text="Custom Message").grid(row=3,column=0,sticky="nw")
        custom=tk.Text(body,height=8,wrap="word"); custom.grid(row=3,column=1,sticky="nsew",pady=3); custom.insert("1.0","This is a test.")
        output=tk.Text(body,height=8,wrap="word"); output.grid(row=4,column=0,columnspan=2,sticky="nsew",pady=(10,3)); output.insert("1.0","Preview will appear here.")
        body.columnconfigure(1,weight=1); body.rowconfigure(3,weight=1); body.rowconfigure(4,weight=1)
        def build():
            output.delete("1.0","end")
            output.insert("1.0",f"SIMULATED SAME / EAS DETAILS\nEvent: {hazard.get()}\nArea codes (unverified): {codes.get()}\nDuration: {duration.get()}\nAudio sequence: SAME header placeholder ×3 → 1050 Hz tone preview → narration placeholder → EOM marker ×3\nMessage: {custom.get('1.0','end').strip()}\n\nNO alert is transmitted. Verify codes and event mapping against official requirements.")
            self.config["same_codes"]=codes.get(); self._set_status("SAME/EAS preview built locally. No valid over-the-air header was emitted.")
        row=ttk.Frame(win,padding=8); row.pack(fill="x")
        ttk.Button(row,text="Build Preview",command=build).pack(side="left",padx=3)
        ttk.Button(row,text="Insert Message into Editor",command=lambda:(self.editor.insert("insert",custom.get("1.0","end").strip()+"\n"),self.tabs.select(self.text_tab))).pack(side="left",padx=3)
        ttk.Button(row,text="Preview 1050 Hz Tone",command=self._preview_tone).pack(side="left",padx=3)

    def _preview_tone(self):
        AUDIO_DIR.mkdir(exist_ok=True); path=AUDIO_DIR/"tone_1050hz_preview.wav"
        rate=22050; duration=1.0; freq=1050.0
        with wave.open(str(path),"wb") as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(rate); data=bytearray()
            for i in range(int(rate*duration)):
                envelope=min(1.0,i/(rate*.02),(rate*duration-i)/(rate*.02))
                sample=int(6500*max(0.0,envelope)*math.sin(2*math.pi*freq*i/rate))
                data.extend(struct.pack("<h",sample))
            wf.writeframes(data)
        self._set_status(f"Created local 1050 Hz tone preview: {path.name}. Not transmitted.")
        if os.name=="nt":
            try:
                import winsound
                winsound.PlaySound(str(path),winsound.SND_FILENAME|winsound.SND_ASYNC)
            except Exception as exc:messagebox.showinfo("Tone Preview",f"Preview WAV created at:\n{path}\nWindows playback failed: {exc}",parent=self.root)
        else:messagebox.showinfo("Tone Preview",f"Local 1050 Hz preview WAV created at:\n{path}\nUse an audio player to listen. No transmission occurred.",parent=self.root)

    def _create_alert(self,hazard,message="",area="Northeast Illinois and Northwest Indiana",expires=""):
        now=datetime.now().astimezone().isoformat(timespec="seconds")
        alert={"id":f"SIM-{len(self.alerts)+1:04d}","hazard":hazard,"summary":message or f"{hazard} — simulated test message",
               "area":area,"action":"NEW","expires":expires or "Not set","created":now}
        self.alerts.append(alert); self.alerts=priority_sort(self.alerts); self._refresh_all()
        self._set_status(f"Added {hazard} to local alert list; no outside alert was sent."); return alert

    def _refresh_alerts(self):
        if not hasattr(self,"alert_tree"):return
        self.alert_tree.delete(*self.alert_tree.get_children())
        for a in priority_sort(self.alerts):self.alert_tree.insert("", "end",iid=a["id"],values=(a["id"],a["hazard"],a["action"],a["expires"]))
        if hasattr(self,"card_alerts"):self.card_alerts.configure(text=f"Active alerts: {len(self.alerts)}")

    def _edit_selected_alert(self):
        selection=self.alert_tree.selection()
        if not selection:messagebox.showinfo("Edit Alert","Select an alert first."); return
        alert=next((a for a in self.alerts if a["id"]==selection[0]),None)
        if not alert:return
        new=simpledialog.askstring("Edit Alert","Edit summary:",initialvalue=alert["summary"],parent=self.root)
        if new is not None:alert["summary"]=new; alert["action"]="CON"; self._refresh_alerts(); self._set_status("Edited local simulated alert.")

    def _silent_interrupt(self):
        self._set_status("Silent interrupt simulated: current queue audio would be muted locally.")
        messagebox.showinfo("Silent Interrupt","Local simulation state only. No audio transmitter was interrupted.")

    def _update_ticker(self):
        if self.tabs.select() == str(self.network_tab):
            txt = self.network_ticker.get()
        else:
            txt = self.global_ticker.get()
        self._set_status("Periodic scroll updated (local): " + txt[:100])

    def _simulate_transmit(self):
        if not messagebox.askyesno("Simulation TX","Start a LOCAL transmit simulation only?\n\nNo radio, network socket, EAS encoder, email, IEMBOT, or public outlet will be contacted.",parent=self.root):return
        self.tx_simulation_running=not self.tx_simulation_running
        self._refresh_all(); self._set_status("Local TX simulation "+("started" if self.tx_simulation_running else "stopped")+". No RF transmission occurred.")

    def _save_draft(self):
        body=self.editor.get("1.0","end").strip()
        if not body:messagebox.showinfo("Save Draft","The editor is empty."); return
        record={"created":datetime.now().astimezone().isoformat(timespec="seconds"),"category":self.category_var.get(),
                "header":{k:v.get() for k,v in self.header_vars.items()},"body":body,
                "destinations":[k for k,v in self.send_vars.items() if v.get()],"status":"DRAFT"}
        self.drafts.append(record); previous=[]
        if OUTBOX_PATH.exists():
            try:previous=json.loads(OUTBOX_PATH.read_text(encoding="utf-8"))
            except Exception:previous=[]
        previous.append(record); save_json(OUTBOX_PATH,previous)
        self._set_status("Draft saved locally to bmh_outbox.json."); messagebox.showinfo("Draft Saved",f"Saved locally. Outbox entries: {len(previous)}")

    def _dispatch_message(self):
        body=self.editor.get("1.0","end").strip()
        if not body:body=BROADCAST_TEXT.get(self.language_var.get(),""); self.editor.insert("1.0",body)
        dest=[k for k,v in self.send_vars.items() if v.get()] if hasattr(self,"send_vars") else ["bmh"]
        record={"id":f"OUT-{len(self.sent_messages)+1:04d}","created":datetime.now().astimezone().isoformat(timespec="seconds"),
                "category":self.category_var.get() if hasattr(self,"category_var") else "Statement","message":body,
                "destinations":dest,"status":"SIMULATED / NOT SENT"}
        self.sent_messages.append(record); self._queue_product(record["id"],body[:95],status="SIMULATED / NOT SENT")
        self._set_status("Dispatch intent recorded locally; nothing was sent.")
        messagebox.showinfo("Local Dispatch",f"Recorded local dispatch intent only.\nDestinations: {', '.join(dest) if dest else '(none selected)'}\nNo email, IEMBOT, websites, or radio system was contacted.")

    def _view_sent_messages(self):
        win=tk.Toplevel(self.root); win.title("View / Edit Sent Alerts — local records"); win.geometry("780x500")
        tree=ttk.Treeview(win,columns=("id","category","status","destinations","created"),show="headings")
        for c,h,w in [("id","ID",90),("category","Category",190),("status","Status",140),("destinations","Destinations",170),("created","Created",170)]:
            tree.heading(c,text=h); tree.column(c,width=w)
        tree.pack(fill="both",expand=True,padx=8,pady=8)
        for m in self.sent_messages:tree.insert("", "end",values=(m["id"],m["category"],m["status"],", ".join(m["destinations"]),m["created"]))
        ttk.Button(win,text="Close",command=win.destroy).pack(anchor="e",padx=10,pady=8)

    def _queue_product(self,product_id,description,status="QUEUED (SIM)"):
        self.queue.append({"id":product_id,"description":description,"status":status,"created":datetime.now().astimezone().isoformat(timespec="seconds")})
        self._refresh_queue(); self._set_status(f"Queued {product_id} locally.")

    def _refresh_queue(self):
        if not hasattr(self,"queue_tree"):return
        self.queue_tree.delete(*self.queue_tree.get_children()); self.iid_queue={}
        for i,item in enumerate(self.queue):
            iid=f"q_{i}"; self.iid_queue[iid]=item
            self.queue_tree.insert("", "end",iid=iid,values=(i+1,item["id"],item["description"],item["status"]))
        if hasattr(self,"card_queue"):self.card_queue.configure(text=f"Live queue: {len(self.queue)}")

    def _read_selected_queue(self):
        sel=self.queue_tree.selection()
        if not sel:self._set_status("Queue read skipped: select an item."); return
        item=self.iid_queue[sel[0]]; item["status"]="READ LOCALLY (SIM)"; self._refresh_queue(); self._set_status("Read product simulated: "+item["id"])

    def _loop_selected_queue(self):
        sel=self.queue_tree.selection()
        if not sel:self._set_status("Loop skipped: select an item."); return
        item=self.iid_queue[sel[0]]; item["status"]="LOOPING (SIM)"; self._refresh_queue(); self._set_status("Selected product loop is simulated: "+item["id"])

    def _stop_loop(self):
        for item in self.queue:
            if item["status"]=="LOOPING (SIM)":item["status"]="STOPPED (SIM)"
        self._refresh_queue(); self._set_status("All local product loops stopped.")

    def _refresh_cycle_tree(self):
        if not hasattr(self,"cycle_tree"):return
        self.cycle_tree.delete(*self.cycle_tree.get_children())
        for i,item in enumerate(self.config.get("cycle_order",DEFAULT_CONFIG["cycle_order"]),1):
            self.cycle_tree.insert("", "end",iid=f"cycle_{i}",values=(i,item))

    def _add_cycle_entry(self):
        selection=self.entries_list.curselection()
        if not selection:return
        entry=self.entries_list.get(selection[0]); order=list(self.config.get("cycle_order",[])); order.append(entry)
        self.config["cycle_order"]=order; self._refresh_cycle_tree(); self._set_status("Added cycle entry (local).")

    def _remove_cycle_entry(self):
        selection=self.cycle_tree.selection()
        if not selection:return
        index=int(selection[0].split("_")[-1])-1; order=list(self.config.get("cycle_order",[]))
        if 0<=index<len(order):order.pop(index)
        self.config["cycle_order"]=order; self._refresh_cycle_tree(); self._set_status("Removed cycle entry.")

    def _move_cycle(self,direction):
        selection=self.cycle_tree.selection()
        if not selection:return
        index=int(selection[0].split("_")[-1])-1; order=list(self.config.get("cycle_order",[])); new=index+direction
        if 0<=index<len(order) and 0<=new<len(order):order[index],order[new]=order[new],order[index]
        self.config["cycle_order"]=order; self._refresh_cycle_tree()
        if order:self.cycle_tree.selection_set(f"cycle_{max(1,min(len(order),new+1))}")

    def _new_mode(self):
        name=simpledialog.askstring("New Broadcast Mode","Name the new local mode:",parent=self.root)
        if name and name.strip():
            if name.strip() not in MODES:MODES.append(name.strip())
            self.mode_var.set(name.strip()); self._set_status("Added local broadcast mode: "+name.strip())

    def _delete_mode(self):
        name=self.mode_var.get()
        if name in MODES:
            MODES.remove(name); self.mode_var.set("General" if "General" in MODES else MODES[0])
            self._set_status("Removed local mode: "+name)
        else:messagebox.showinfo("Delete Mode","Select a mode first.")

    def _reset_mode(self):
        self.mode_var.set("General"); self.config["cycle_order"]=list(DEFAULT_CONFIG["cycle_order"])
        self._refresh_cycle_tree(); self._set_status("Broadcast mode/order reset to defaults.")

    def _save_settings(self):
        for key,var in self.setting_vars.items():self.config[key]=var.get()
        try:self.config["workstation_port"]=int(self.config.get("workstation_port",6000))
        except (TypeError,ValueError):self.config["workstation_port"]=6000
        self.config["language"]=self.setting_vars["language"].get(); self.config["voice"]=self.setting_vars["voice"].get()
        self.config["enable_listening_area_filter"]=bool(self.filter_var.get()); self.config["allow_routine_without_codes"]=bool(self.routine_var.get())
        self.config["simulation_only"]=True
        try:
            save_json(CONFIG_PATH,self.config); self.language_var.set(self.config["language"])
            self._set_status("Settings saved to bmh_suite_config.json. Network values remain display/config only.")
            messagebox.showinfo("Settings Saved",f"Saved {CONFIG_PATH.name}. No network listener was started.")
        except OSError as exc:messagebox.showerror("Settings Error",str(exc))

    def _restore_settings(self):
        if not messagebox.askyesno("Restore Defaults","Restore local simulator settings to defaults?",parent=self.root):return
        self.config=dict(DEFAULT_CONFIG)
        for key,var in self.setting_vars.items():var.set(str(self.config.get(key,"")))
        self.setting_vars["language"].set(self.config["language"]); self.setting_vars["voice"].set(self.config["voice"])
        self.filter_var.set(True); self.routine_var.set(True); self.mode_var.set("General")
        self._set_status("Default values loaded in GUI. Click Save Settings to write JSON.")

    def _browse_voicetext(self):
        path=filedialog.askopenfilename(title="Select VoiceText EXE",filetypes=[("Executable","*.exe"),("All files","*.*")])
        if path and "voicetext_exe" in self.setting_vars:self.setting_vars["voicetext_exe"].set(path)

    def _preview_language(self):
        lang=self.setting_vars["language"].get()
        messagebox.showinfo("Broadcast Template",BROADCAST_TEXT.get(lang,BROADCAST_TEXT["English"]),parent=self.root)

    def _on_close(self):
        if self.tx_simulation_running:
            if not messagebox.askyesno("Stop Simulation","A local TX simulation is running. Stop it and exit?",parent=self.root):return
            self.tx_simulation_running=False
        self.root.destroy()

def main():
    root=tk.Tk()
    BMHWeatherRadioSuite(root)
    root.mainloop()

if __name__=="__main__":
    main()
