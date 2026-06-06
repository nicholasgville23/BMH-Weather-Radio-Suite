import re
from dataclasses import dataclass
from typing import Optional

@dataclass
class VTECRecord:
    action: str
    office: str
    phenomena: str
    significance: str
    etn: str
    start_time: str
    end_time: str

class VTECParser:
    # Example: /O.NEW.KGRR.TO.W.0001.230206T0300Z-230206T0400Z/
    VTEC_PATTERN = r"/(?P<product_class>[A-Z])\.(?P<action>[A-Z]{3})\.(?P<office>[A-Z]{4})\.(?P<phenomena>[A-Z]{2})\.(?P<significance>[A-Z])\.(?P<etn>\d{4})\.(?P<start>\d{6}T\d{4}Z)-(?P<end>\d{6}T\d{4}Z)/"

    @staticmethod
    def parse(text: str) -> Optional[VTECRecord]:
        match = re.search(VTECParser.VTEC_PATTERN, text)
        if match:
            return VTECRecord(
                action=match.group("action"),
                office=match.group("office"),
                phenomena=match.group("phenomena"),
                significance=match.group("significance"),
                etn=match.group("etn"),
                start_time=match.group("start"),
                end_time=match.group("end")
            )
        return None

    @staticmethod
    def get_readable_phenomena(phenomena: str) -> str:
        mapping = {
            "TO": "Tornado",
            "SV": "Severe Thunderstorm",
            "FF": "Flash Flood",
            "MA": "Special Marine",
            "BZ": "Blizzard"
        }
        return mapping.get(phenomena, "Weather")

    @staticmethod
    def get_readable_significance(significance: str) -> str:
        mapping = {
            "W": "Warning",
            "A": "Watch",
            "Y": "Advisory",
            "S": "Statement"
        }
        return mapping.get(significance, "Information")