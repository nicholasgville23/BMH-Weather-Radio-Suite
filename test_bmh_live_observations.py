import unittest

from bmh_live_observations import (
    degrees_to_compass,
    format_observation,
    normalize_observation,
    validate_station_id,
)


class ObservationCoreTests(unittest.TestCase):
    def test_station_id_validation(self):
        self.assertEqual(validate_station_id(" kvpz "), "KVPZ")
        with self.assertRaises(ValueError):
            validate_station_id("KVPZ?url=https://example.com")
        with self.assertRaises(ValueError):
            validate_station_id("")

    def test_unit_normalization(self):
        payload = {
            "@id": "https://api.weather.gov/stations/KVPZ/observations/latest",
            "properties": {
                "timestamp": "2026-10-10T12:00:00+00:00",
                "textDescription": "Clear",
                "temperature": {"value": 20.0},
                "dewpoint": {"value": 10.0},
                "windSpeed": {"value": 5.0},
                "windGust": {"value": None},
                "windDirection": {"value": 90.0},
                "relativeHumidity": {"value": 45.0},
                "barometricPressure": {"value": 101325.0},
                "visibility": {"value": 16093.44},
                "precipitationLastHour": {"value": 2.54},
            },
        }
        result = normalize_observation(payload, "KVPZ")
        self.assertAlmostEqual(result["temperature_f"], 68.0)
        self.assertAlmostEqual(result["dewpoint_f"], 50.0)
        self.assertAlmostEqual(result["wind_speed_mph"], 5.0 * 2.2369362921)
        self.assertAlmostEqual(result["precipitation_last_hour_in"], 0.1)
        self.assertEqual(result["wind_direction"], "E")

    def test_missing_values_are_explicit(self):
        result = normalize_observation({"properties": {}}, "KVPZ")
        text = format_observation(result)
        self.assertIn("Not reported", text)
        self.assertIn("READ-ONLY REFERENCE", text)


if __name__ == "__main__":
    unittest.main()
