import unittest
from unittest.mock import patch

from bmh_live_monitor import (
    alert_priority,
    fetch_active_alerts,
    format_monitor_detail,
    parse_areas,
    sort_alerts,
)


class LiveMonitorTests(unittest.TestCase):
    def test_parse_state_areas(self):
        self.assertEqual(parse_areas("il, IN, il"), ["IL", "IN"])
        self.assertEqual(parse_areas("US"), [None])
        self.assertEqual(parse_areas(""), [None])

    def test_rejects_invalid_area_codes(self):
        with self.assertRaises(ValueError):
            parse_areas("XX")
        with self.assertRaises(ValueError):
            parse_areas("IL,ALL")

    def test_priority_order(self):
        self.assertEqual(alert_priority("National Emergency Message"), 0)
        self.assertEqual(alert_priority("Tornado Warning"), 1)
        self.assertEqual(alert_priority("Severe Thunderstorm Watch"), 2)
        self.assertEqual(alert_priority("Winter Weather Advisory"), 3)
        self.assertEqual(alert_priority("Special Weather Statement"), 4)

    def test_sort_uses_event_priority_before_severity(self):
        alerts = [
            {"event": "Special Weather Statement", "severity": "Extreme", "area": "A"},
            {"event": "Severe Thunderstorm Warning", "severity": "Severe", "area": "B"},
            {"event": "National Emergency Message", "severity": "Minor", "area": "C"},
            {"event": "Tornado Watch", "severity": "Moderate", "area": "D"},
        ]
        ordered = sort_alerts(alerts)
        self.assertEqual(
            [item["event"] for item in ordered],
            [
                "National Emergency Message",
                "Severe Thunderstorm Warning",
                "Tornado Watch",
                "Special Weather Statement",
            ],
        )

    def test_detail_discloses_read_only_boundary(self):
        detail = format_monitor_detail({
            "id": "x",
            "event": "Tornado Warning",
            "headline": "Tornado Warning for Porter County",
            "area": "Porter County, IN",
            "severity": "Extreme",
            "urgency": "Immediate",
            "certainty": "Observed",
            "url": "https://api.weather.gov/alerts/x",
            "description": "Take shelter.",
        })
        self.assertIn("Take shelter.", detail)
        self.assertIn("read-only display", detail)
        self.assertIn("not a transmitter", detail)

    @patch("bmh_live_monitor.NWSClient._get_json")
    def test_fetch_queries_official_api_per_area(self, get_json):
        get_json.return_value = {"features": []}
        self.assertEqual(fetch_active_alerts(["IL", "IN"]), [])
        self.assertEqual(get_json.call_count, 2)
        self.assertIn("area=IL", get_json.call_args_list[0].args[0])
        self.assertIn("area=IN", get_json.call_args_list[1].args[0])


if __name__ == "__main__":
    unittest.main()
