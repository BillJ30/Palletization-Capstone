import csv
from pathlib import Path
import tempfile
import unittest

import palet_conformador as pc
from pallet_validation import validate_order_geometry


CONFIG = {
    "PALET_ANCHO_CM": pc.PALET_ANCHO_CM,
    "PALET_LARGO_CM": pc.PALET_LARGO_CM,
    "PALLET_BASE_HEIGHT_CM": pc.PALLET_BASE_HEIGHT_CM,
    "MAX_TOTAL_PALLET_HEIGHT_CM": pc.MAX_TOTAL_PALLET_HEIGHT_CM,
    "MIN_SUPPORT_RATIO": pc.MIN_SUPPORT_RATIO,
    "MAX_MIXED_PALLET_GROSS_WEIGHT_KG": pc.MAX_MIXED_PALLET_GROSS_WEIGHT_KG,
    "PALLET_TARE_WEIGHT_KG": pc.PALLET_TARE_WEIGHT_KG,
}


def box(height, z=pc.PALLET_BASE_HEIGHT_CM):
    return {
        "x_cm": 0.0, "y_cm": 0.0, "z_cm": z,
        "ancho_cm": 10.0, "largo_cm": 10.0, "alto_cm": height,
        "descripcion": "HEIGHT-TEST",
        "station_index": 1,
        "peso_caja": 1.0,
    }


class HeightContractTests(unittest.TestCase):
    def test_exact_total_height_is_accepted(self):
        result = validate_order_geometry(
            [{"numero": 1, "cajas_3d": [box(pc.MAX_TOTAL_PALLET_HEIGHT_CM - pc.PALLET_BASE_HEIGHT_CM)]}],
            CONFIG,
        )
        self.assertTrue(result.valid, result.issues)

    def test_height_above_total_limit_is_rejected(self):
        result = validate_order_geometry(
            [{"numero": 1, "cajas_3d": [box(pc.MAX_TOTAL_PALLET_HEIGHT_CM - pc.PALLET_BASE_HEIGHT_CM + 0.0001)]}],
            CONFIG,
        )
        self.assertFalse(result.valid)
        self.assertEqual(result.issues[0].code, "HEIGHT_EXCEEDED")

    def test_empty_pallet_total_height_is_base_height(self):
        pallet = pc.PaletConformado(numero=1)
        self.assertEqual(pallet.altura_total_cm, pc.PALLET_BASE_HEIGHT_CM)

    def test_first_layer_starts_at_deck_height(self):
        heightmap = [[pc.PALLET_BASE_HEIGHT_CM] * pc.GRID_L for _ in range(pc.GRID_W)]
        position = pc.buscar_posicion_optima(
            heightmap, 10.0, 10.0, 10.0, pc.MAX_TOTAL_PALLET_HEIGHT_CM, []
        )
        self.assertIsNotNone(position)
        self.assertEqual(position[2], pc.PALLET_BASE_HEIGHT_CM)

    def test_displayed_cargo_height_plus_base_equals_total(self):
        line = pc.LineaPedido(
            descripcion="DISPLAY-TEST", articulo=1, grupo_art="TEST", orden_apilado=1,
            cajas_linea=1.0, cajas_por_palet_real=1.0, cajas_por_capa_real=1.0,
            capas_por_palet_real=1.0, es_palet_entero=False, semipalet=False,
            cajas_por_palet_csv=1.0, es_picking=True, tipo_resto="",
            palets_completos=0.0, peso_palet_bruto=1.0, alergeno=False,
            alto_caja_cm=10.0, ancho_caja_cm=10.0, largo_caja_cm=10.0,
            station_index=1, station_name="TEST",
        )
        result = pc.procesar_pedido_dict("ORDER", [line])
        pallet = result["palets_picking"][0]
        self.assertAlmostEqual(
            pallet["altura_carga_cm"] + pc.PALLET_BASE_HEIGHT_CM,
            pallet["altura_total_cm"],
            places=6,
        )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "height.csv"
            pc.exportar_pedido_a_csv_visualizacion("ORDER", [line], result, path)
            with path.open(newline="", encoding="utf-8-sig") as stream:
                row = next(csv.DictReader(stream))
        self.assertEqual(row["Z_Reference"], "PALLET_TOTAL_COORDINATES")
        self.assertAlmostEqual(
            float(row["Pallet_Cargo_Height_cm"]) + pc.PALLET_BASE_HEIGHT_CM,
            float(row["Pallet_Total_Height_cm"]),
            places=6,
        )


if __name__ == "__main__":
    unittest.main()
