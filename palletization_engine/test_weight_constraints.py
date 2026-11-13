import csv
from pathlib import Path
import tempfile
import unittest

import palet_conformador as pc
from pallet_validation import validate_order_geometry
from sku_master import build_sku_master


CONFIG = {
    "PALET_ANCHO_CM": 120.0,
    "PALET_LARGO_CM": 80.0,
    "PALLET_BASE_HEIGHT_CM": 14.4,
    "MAX_TOTAL_PALLET_HEIGHT_CM": 160.0,
    "MIN_SUPPORT_RATIO": 1.0,
    "MAX_MIXED_PALLET_GROSS_WEIGHT_KG": 100.0,
    "PALLET_TARE_WEIGHT_KG": 0.0,
}


def subline(cases, weight):
    return pc.SubLinea(
        descripcion="WEIGHT", cajas=float(cases), alergeno=False,
        cajas_por_palet_real=float(cases), peso_caja=weight,
        cajas_por_capa=1.0, capas_por_palet=float(cases), grupo_art="PA70",
        alto_caja_cm=10.0, ancho_caja_cm=10.0, largo_caja_cm=10.0,
        estabilidad="ESTABLE", orden_apilado=1, station_index=1,
        station_name="S1",
    )


def case(weight, z=14.4):
    return {
        "x_cm": 0.0, "y_cm": 0.0, "z_cm": z,
        "ancho_cm": 10.0, "largo_cm": 10.0, "alto_cm": 10.0,
        "descripcion": "WEIGHT", "peso_caja": weight, "station_index": 1,
    }


class WeightConstraintTests(unittest.TestCase):
    def test_placement_exactly_at_weight_limit_passes(self):
        pallets = pc.conformar_palets_3d(
            [subline(1, 100.0)], max_gross_weight_kg=100.0
        )
        self.assertEqual(len(pallets), 1)
        self.assertEqual(pallets[0].peso_bruto_total_kg, 100.0)

    def test_placement_exceeding_weight_limit_fails(self):
        with self.assertRaises(ValueError):
            pc.conformar_palets_3d(
                [subline(1, 100.0001)], max_gross_weight_kg=100.0
            )

    def test_final_validator_detects_overweight_pallet(self):
        result = validate_order_geometry(
            [{"numero": 1, "cajas_3d": [case(100.0001)]}], CONFIG
        )
        self.assertFalse(result.valid)
        self.assertEqual(result.issues[0].code, "OVERWEIGHT")
        self.assertAlmostEqual(result.gross_weight_kg, 100.0001)

    def test_export_weight_metadata_matches_reconciled_gross_weight(self):
        sub = subline(1, 42.5)
        pallet = pc.conformar_palets_3d([sub], max_gross_weight_kg=100.0)[0]
        result = {"palets_picking": [{
            "numero": pallet.numero,
            "altura_total_cm": pallet.altura_total_cm,
            "altura_carga_cm": pallet.altura_total_cm - pc.PALLET_BASE_HEIGHT_CM,
            "peso_total": pallet.peso_bruto_total_kg,
            "peso_carga_total": pallet.peso_total,
            "peso_tara_kg": pallet.peso_tara_kg,
            "peso_bruto_total_kg": pallet.peso_bruto_total_kg,
            "cajas_3d": pallet.cajas_3d,
        }]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "weight.csv"
            pc.exportar_pedido_a_csv_visualizacion("ORDER", [], result, path)
            with path.open(newline="", encoding="utf-8-sig") as stream:
                row = next(csv.DictReader(stream))
        self.assertAlmostEqual(float(row["Pallet_Gross_Weight_kg"]), 42.5)
        self.assertAlmostEqual(
            float(row["Pallet_Cargo_Weight_kg"]) + float(row["Pallet_Tare_Weight_kg"]),
            float(row["Pallet_Gross_Weight_kg"]),
        )

    def test_missing_compression_data_is_diagnostic_not_density_strength(self):
        dimensions = __import__("pandas").DataFrame([{
            "Material": 1, "UMB": "ZCJ", "Longitud_cm": 10.0,
            "Ancho_cm": 10.0, "Altura_cm": 10.0, "Peso bruto": 1.0,
        }])
        capacity = __import__("pandas").DataFrame([{
            "Material": 1, "UMB": "ZCJ", "Cajas/Capa": 1,
            "Capas/Palet": 1, "BRUTO ZPA": 1.0,
        }])
        master, report = build_sku_master(dimensions, capacity)
        self.assertEqual(report.valid_specs, 1)
        self.assertIsNone(master.loc[0, "MAX_LOAD_ABOVE_KG"])

        result = validate_order_geometry(
            [{"numero": 1, "cajas_3d": [case(1.0), case(1.0, z=24.4)]}], CONFIG
        )
        self.assertTrue(result.valid, result.issues)
        self.assertIn("load_data_unavailable", result.diagnostics)


if __name__ == "__main__":
    unittest.main()
