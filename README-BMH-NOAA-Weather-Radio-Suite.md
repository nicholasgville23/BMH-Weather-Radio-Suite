# BMH NOAA Weather Radio Suite — Tkinter GUI

This project adds a standalone Tkinter control-room interface to the existing Python BMH Weather Radio Suite. It is an incremental GUI entry point; the existing audio/product generator scripts are left unchanged.

## Run

Requires Python 3.10+ and a Python distribution that includes Tkinter. Run: python bmh_suite_gui.py

On first launch the app creates bmh_suite_config.json in the repository folder. Settings can be changed in Text_Workstation_Settings. This GUI uses only the Python standard library for its interface and local tone preview.

## Included in this GUI build

- KLOT LOTIEM Text Workstation: editable WMO-style header fields, product categories, editor options, local drafts, a local outbox, and a sent-intent viewer.
- WarnGen / WatchGen-style hazard segment builder and a schematic click-to-draw polygon tool with LAT...LON output.
- BMH Network dashboard with a ticker editor, active transmitter profiles for WXK89 and KBB57, and per-station controller windows.
- Alert priority list, Required Weekly/Monthly Test buttons, editable SAME/EAS preview settings, 1050 Hz tone WAV preview, and local alert/queue actions.
- Broadcast-mode and cycle-order editor, static message IDs, queue read/loop simulation, listening-area options, and JSON settings.
- Broadcast-language template selector for English, Turkish, German, Spanish, and French; selectable Tom, Paul, Harry, and Donna voice labels; optional VoiceText EXE path setting.

## Station data note

noaa_stations_catalog.py is copied from the companion nicholasgville23/noaa-weather-radio-simulator project as a seed catalog. It contains 520 entries spanning all 50 states, but the source data includes duplicate call signs and has not been verified entry-by-entry against current NWS listings. It is not an official station database. Confirm callsign, station ID, frequency, coordinates, FIPS/SAME coverage, and current operational status against the official NWS NWR station listing before using station data for anything beyond simulation: https://www.weather.gov/nwr/station_listing?force_isolation=true. The two local station profiles WXK89 (Valparaiso, 162.400 MHz) and KBB57 (Gary, 162.425 MHz) are included as user-configured simulation profiles.

## Live current observations

The dashboard also includes **Live Current Observations**. It requests the latest station observation from the official `api.weather.gov/stations/{stationId}/observations/latest` endpoint (default station `KVPZ`, editable in the viewer), and displays time, conditions, temperature, dew point, wind, humidity, pressure, visibility, and recent precipitation when reported. This uses real NWS observation data; it is still a read-only data viewer, not a receiver of the station's RF broadcast. No continuous polling is enabled; refresh is manual.

## Safety and integration boundaries

SIMULATION ONLY. This is not an operational warning system. The code does not transmit radio-frequency energy, create an operational EAS encoder connection, open a network socket at the configured IP/port, send email, post to IEMBOT, or publish to websites/outlets. TRANSMIT, START TX, queue playback, SAME/EAS, and test-alert buttons modify local GUI state or create local preview files only. The 1050 Hz WAV is a basic tone preview, not an authenticated SAME/EAS audio sequence. The polygon canvas is schematic, not live radar or authoritative warning geometry.

The UI language and voice labels are selections/template helpers; this first GUI build does not include licensed SAPI/VoiceText data or a full translation of every control. Existing weather-product generation and audio playback scripts can be integrated in a separate step after their runtime and data dependencies are configured.

## Live NWS data viewer

The dashboard includes **Live NWS Alerts / Forecast**, which retrieves active alerts for Illinois and Indiana from the official api.weather.gov service and can load an official forecast-zone period list (for example, INZ011). The viewer is read-only. It can show alert details, open the official source URL, insert a clearly labelled reference copy into the local text editor, and optionally speak an alert through the computer's local audio output if pyttsx3 is installed.

Run pip install pyttsx3 only if you want local speech. Voice availability depends on the operating system and installed speech engines; the viewer does not claim that a local system voice is the licensed VoiceText Paul voice.

Live data retrieval is real, but this feature does **not** make the suite an authorized public-warning transmitter. It does not connect to RF transmitters, an EAS encoder, email, IEMBOT, websites, or public distribution endpoints. Treat the workstation's generated/reference text as local working material and verify official products at their NWS source.
