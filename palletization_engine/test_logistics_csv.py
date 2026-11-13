import csv
import io
from pathlib import Path
import tempfile
import unittest

from logistics_csv import MalformedLogisticsCSVError, read_logistics_csv


HEADER = ["PEDIDO", "DESCRIPCION_FINAL", "CAJAS_LINEA", "ES_PICKING"]


class LogisticsCsvTests(unittest.TestCase):
    def write_fixture(self, rows):
        handle = tempfile.NamedTemporaryFile(
            mode="w", newline="", encoding="utf-8", suffix=".csv", delete=False,
        )
        with handle:
            writer = csv.writer(handle)
            writer.writerow(HEADER)
            for row in rows:
                handle.write(row)
                if not row.endswith("\n"):
                    handle.write("\n")
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        return handle.name

    def test_normal_wrapped_and_quoted_comma_records(self):
        wrapped_inner = ["1002", "wrapped, description", "20", "False"]
        buffer = io.StringIO(newline="")
        csv.writer(buffer).writerow(wrapped_inner)
        outer = io.StringIO(newline="")
        csv.writer(outer).writerow([buffer.getvalue().rstrip("\r\n")])

        path = self.write_fixture([
            "1001,normal description,10,True",
            outer.getvalue().rstrip("\r\n"),
            '1003,"normal, quoted description",30,True',
        ])
        frame, metrics = read_logistics_csv(path, return_metrics=True)

        self.assertEqual(len(frame), 3)
        self.assertEqual(frame.loc[1, "DESCRIPCION_FINAL"], "wrapped, description")
        self.assertEqual(metrics.physical_records_read, 3)
        self.assertEqual(metrics.repaired_wrapped_records, 1)
        self.assertEqual(metrics.records_rejected, 0)
        self.assertEqual(metrics.unique_numeric_orders, 3)

    def test_wrong_field_count_fails_clearly(self):
        path = self.write_fixture(["1001,normal,10"])
        with self.assertRaises(MalformedLogisticsCSVError) as raised:
            read_logistics_csv(path)
        self.assertIn("expected 4 fields", str(raised.exception))
        self.assertIn("found 3 fields", str(raised.exception))
        self.assertEqual(raised.exception.metrics.records_rejected, 1)


if __name__ == "__main__":
    unittest.main()
