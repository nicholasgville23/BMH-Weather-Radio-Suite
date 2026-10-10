import unittest
from datetime import datetime, timezone

from bmh_suite_gui import build_wmo_header, priority_sort, make_alert_text, DEFAULT_CONFIG

class SuiteCoreTests(unittest.TestCase):
    def test_wmo_header_format(self):
        stamp = datetime(2026, 10, 10, 12, 34, tzinfo=timezone.utc)
        self.assertEqual(build_wmo_header("wwus53", "klot", "nor", stamp), "WWUS53 KLOT 101234 NOR")

    def test_priority_order(self):
        rows = [
            {"hazard": "Special Weather Statement", "created": "2"},
            {"hazard": "Tornado Warning", "created": "1"},
            {"hazard": "National Emergency Message", "created": "0"},
        ]
        ordered = priority_sort(rows)
        self.assertEqual([x["hazard"] for x in ordered], [
            "National Emergency Message", "Tornado Warning", "Special Weather Statement"
        ])

    def test_alert_text_is_marked_simulation(self):
        text = make_alert_text("Tornado Warning", "Porter County", "Move indoors")
        self.assertIn("TORNADO WARNING", text)
        self.assertIn("PORTER COUNTY", text)
        self.assertIn("NOT AN OFFICIAL NWS PRODUCT", text)

    def test_config_defaults_are_local_only(self):
        self.assertTrue(DEFAULT_CONFIG["simulation_only"])
        self.assertEqual(DEFAULT_CONFIG["workstation_port"], 6000)

if __name__ == "__main__":
    unittest.main()
