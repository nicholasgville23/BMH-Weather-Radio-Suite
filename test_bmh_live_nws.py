import unittest

from bmh_live_nws import alert_sort_key, format_alert_reference, normalize_alert, validate_zone_code


class LiveNWSTests(unittest.TestCase):
    def test_validate_zone_code(self):
        self.assertEqual(validate_zone_code("inz011"), "INZ011")
        self.assertEqual(validate_zone_code(" ILZ013 "), "ILZ013")
        with self.assertRaises(ValueError):
            validate_zone_code("CAZ006")
        with self.assertRaises(ValueError):
            validate_zone_code("INZ011?url=https://example.com")

    def test_normalize_alert(self):
        alert = normalize_alert({
            "id": "https://api.weather.gov/alerts/123",
            "properties": {
                "event": "Tornado Warning", "severity": "Extreme", "areaDesc": "Porter County",
                "description": "Take shelter.", "instruction": "Move to a safe room.",
                "geocode": {"SAME": ["018127"]},
            },
        })
        self.assertEqual(alert["event"], "Tornado Warning")
        self.assertEqual(alert["area"], "Porter County")
        self.assertEqual(alert["same_codes"], "018127")
        self.assertEqual(alert["url"], "https://api.weather.gov/alerts/123")

    def test_alert_sorting_orders_severe_first(self):
        rows = [
            {"severity": "Minor", "event": "Statement", "area": "A"},
            {"severity": "Extreme", "event": "Tornado Warning", "area": "B"},
            {"severity": "Severe", "event": "Warning", "area": "C"},
        ]
        self.assertEqual([x["severity"] for x in sorted(rows, key=alert_sort_key)],
                         ["Extreme", "Severe", "Minor"])

    def test_reference_is_labelled_and_keeps_source(self):
        text = format_alert_reference({
            "event": "Flood Warning", "headline": "Flood Warning issued", "severity": "Severe",
            "urgency": "Immediate", "certainty": "Observed", "area": "Lake County",
            "sender": "NWS Chicago", "url": "https://api.weather.gov/alerts/123",
            "description": "Flooding is occurring.", "instruction": "Move to higher ground.",
        })
        self.assertIn("REFERENCE COPY ONLY", text)
        self.assertIn("https://api.weather.gov/alerts/123", text)
        self.assertIn("Move to higher ground.", text)


if __name__ == "__main__":
    unittest.main()
