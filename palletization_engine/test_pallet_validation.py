import csv
from pathlib import Path
import tempfile
import unittest

import palet_conformador as pc
from pallet_validation import (
    InvalidPalletGeometryError,
    validate_order_geometry,
)


CONFIG = {
    "PALET_ANCHO_CM": pc.PALET_ANCHO_CM,
    "PALET_LARGO_CM": pc.PALET_LARGO_CM,
    "MADERA_CM": pc.MADERA_CM,
    "ALTURA_MAX_CM": pc.ALTURA_MAX_CM,
    "MAX_MIXED_PALLET_GROSS_WEIGHT_KG": pc.MAX_MIXED_PALLET_GROSS_WEIGHT_KG,
    "PALLET_TARE_WEIGHT_KG": pc.PALLET_TARE_WEIGHT_KG,
}


def box(x=0.0, y=0.0, z=14.4, w=20.0, d=20.0, h=10.0, name="BOX"):
    return {
        "x_cm": x, "y_cm": y, "z_cm": z,
        "ancho_cm": w, "largo_cm": d, "alto_cm": h,
        "descripcion": name,
        "station_index": 1,
        "peso_caja": 1.0,
    }


def pallet(*boxes, number=1):
    return {"numero": number, "cajas_3d": list(boxes)}


class PalletValidationTests(unittest.TestCase):
    def test_valid_touching_boxes_pass(self):
        result = validate_order_geometry(
            [pallet(box(name="LEFT"), box(x=20.0, name="RIGHT"))], CONFIG
        )
        self.assertTrue(result.valid)
        self.assertEqual(result.issues, ())

    def test_overlapping_pair_blocks_export(self):
        invalid = pallet(box(name="A"), box(x=19.99, name="B"))
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "placements.csv"
            with self.assertRaises(InvalidPalletGeometryError) as raised:
                pc.exportar_pedido_a_csv_visualizacion(
                    "ORDER", [], {"palets_picking": [invalid]}, destination
                )
        self.assertIn("OVERLAP", str(raised.exception.result.issues[0].code))
        self.assertIn("cases 0", str(raised.exception))
        self.assertIn("coordinates", str(raised.exception))

    def test_out_of_bounds_case_blocks_export(self):
        result = validate_order_geometry([pallet(box(x=120.1))], CONFIG)
        self.assertFalse(result.valid)
        self.assertEqual(result.issues[0].code, "OUT_OF_BOUNDS")

    def test_non_positive_dimension_blocks_export(self):
        result = validate_order_geometry([pallet(box(w=0.0))], CONFIG)
        self.assertFalse(result.valid)
        self.assertEqual(result.issues[0].code, "NON_POSITIVE_DIMENSION")

    def test_failed_export_leaves_existing_destination_unchanged(self):
        invalid = pallet(box(name="A"), box(x=19.99, name="B"))
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "placements.csv"
            destination.write_text("sentinel\n", encoding="utf-8")
            with self.assertRaises(InvalidPalletGeometryError):
                pc.exportar_pedido_a_csv_visualizacion(
                    "ORDER", [], {"palets_picking": [invalid]}, destination
                )
            self.assertEqual(destination.read_text(encoding="utf-8"), "sentinel\n")

    def test_valid_order_exports_normally(self):
        result = {"palets_picking": [pallet(box(name="VALID"))]}
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "placements.csv"
            returned = pc.exportar_pedido_a_csv_visualizacion(
                "ORDER", [], result, destination
            )
            self.assertEqual(returned, destination)
            with destination.open(newline="", encoding="utf-8-sig") as stream:
                rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Placement_Status"], "PLACED")


if __name__ == "__main__":
    unittest.main()
