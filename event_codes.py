"""
SAME (Specific Area Message Encoding) Event Codes
Reference: NWSI 10-1712
"""

EVENT_CODES = {
    "ADR": "Administrative Message",
    "AVA": "Avalanche Watch",
    "AVW": "Avalanche Warning",
    "BLU": "Blue Alert",
    "BZW": "Blizzard Warning",
    "CAE": "Child Abduction Emergency",
    "CDW": "Civil Danger Warning",
    "CEM": "Civil Emergency Message",
    "CFA": "Coastal Flood Watch",
    "CFW": "Coastal Flood Warning",
    "DMO": "Practice/Demo Warning",
    "DSW": "Dust Storm Warning",
    "EVI": "Evacuation Immediate",
    "EWW": "Extreme Wind Warning",
    "FFA": "Flash Flood Watch",
    "FFW": "Flash Flood Warning",
    "FFS": "Flash Flood Statement",
    "FLA": "Flood Watch",
    "FLW": "Flood Warning",
    "FLS": "Flood Statement",
    "HWA": "High Wind Watch",
    "HWW": "High Wind Warning",
    "HUA": "Hurricane Watch",
    "HUW": "Hurricane Warning",
    "HLS": "Hurricane Statement",
    "LEW": "Law Enforcement Warning",
    "LAE": "Local Area Emergency",
    "NUW": "Nuclear Power Plant Warning",
    "RHW": "Radiological Hazard Warning",
    "RMT": "Required Monthly Test",
    "RWT": "Required Weekly Test",
    "SMW": "Special Marine Warning",
    "SPS": "Special Weather Statement",
    "SVA": "Severe Thunderstorm Watch",
    "SVR": "Severe Thunderstorm Warning",
    "SVS": "Severe Weather Statement",
    "TOA": "Tornado Watch",
    "TOR": "Tornado Warning",
    "TSA": "Tsunami Watch",
    "TSW": "Tsunami Warning",
    "VOW": "Volcano Warning",
    "WXR": "Weather Radio Receiver",
}

def get_event_name(code):
    return EVENT_CODES.get(code.upper(), "Unknown Event")

def is_test(code):
    return code.upper() in ["RMT", "RWT", "DMO"]