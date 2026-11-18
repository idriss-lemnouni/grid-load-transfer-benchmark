from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zoneinfo import ZoneInfo

from benchmark import fold_partitions, sequential_radius
from grid_data import LAGS, local_day_hours, make_records, origin_for, read_series


class GridTests(unittest.TestCase):
    def test_daylight_saving_calendar(self):
        vienna = ZoneInfo("Europe/Vienna")
        self.assertEqual(local_day_hours(date(2020, 3, 29), vienna), 23)
        self.assertEqual(local_day_hours(date(2020, 10, 25), vienna), 25)
        self.assertEqual(local_day_hours(date(2020, 2, 29), vienna), 24)
        self.assertEqual(origin_for(date(2020, 3, 29), vienna).hour, 11)
        self.assertEqual(origin_for(date(2020, 3, 30), vienna).hour, 10)

    def test_record_lags_use_issue_time_and_skip_gaps(self):
        target = datetime(2020, 6, 1, 19, tzinfo=timezone.utc)
        history = {target - timedelta(hours=lag): 100.0 + count for count, lag in enumerate(LAGS)}
        source = history | {target: 500.0}
        zone = ZoneInfo("Europe/Berlin")
        rows, _ = make_records(source, zone)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertLess(max(history), row.origin)
        self.assertLess(row.origin, row.target)
        self.assertEqual(row.lag_week, 102.0)
        self.assertEqual(row.scale, 103.5)
        del source[max(history)]
        rows, dropped = make_records(source, zone)
        self.assertEqual(rows, [])
        self.assertGreater(dropped, 0)

    def test_folds_purge_labels_after_first_origin(self):
        zone = ZoneInfo("Europe/Vienna")
        start = datetime(2018, 12, 1, tzinfo=timezone.utc)
        end = datetime(2020, 1, 1, tzinfo=timezone.utc)
        source = {start + timedelta(hours=index): 100.0
                  for index in range(int((end - start).total_seconds() / 3600))}
        rows, _ = make_records(source, zone)
        for fitting, validation in fold_partitions(rows):
            self.assertLess(max(row.target for row in fitting), min(row.origin for row in validation))
        self.assertEqual(sequential_radius([1, 3, 2, 4, 5], 0.8), 5)

    def test_duplicate_utc_rejected(self):
        row = "2017-02-01T00:00:00Z,15000,3500\n"
        header = "utc_timestamp,DE_load_actual_entsoe_transparency,AT_load_actual_entsoe_transparency\n"
        with TemporaryDirectory() as folder:
            path = Path(folder) / "data.csv"
            path.write_text(header + row + row, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                read_series(path)


if __name__ == "__main__":
    unittest.main()
