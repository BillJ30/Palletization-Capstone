import unittest

import pandas as pd

from run_csv import ManualOrderValidationError, construir_pedido_manual


def manual_master():
    return pd.DataFrame([
        {
            "ARTICULO": 1001, "SKU_SPEC_VALID": True,
            "DESCRIPCION_FINAL": "Valid SKU", "CASE_WEIGHT_KG": 1.0,
            "STATION_INDEX": 1, "STATION_NAME": "TEST", "Grupo art.": "G",
            "ORDEN_APILADO": 1, "CAJAS_POR_PALET_REAL": 10,
            "CAJAS_POR_CAPA_REAL": 5, "CAPAS_POR_PALET_REAL": 2,
            "CAJAS_POR_PALET": 10, "PALETS_COMPLETOS": 0, "BRUTO ZPA": 1.0,
            "ES_ALERGENO": False, "ALTO_CAJA_CM": 10.0,
            "ANCHO_CAJA_CM": 20.0, "LARGO_CAJA_CM": 30.0,
            "Estabilidad": "ESTABLE",
        },
    ])


class ManualOrderValidationTests(unittest.TestCase):
    def test_all_invalid_materials_are_reported_together(self):
        with self.assertRaises(ManualOrderValidationError) as context:
            construir_pedido_manual("1001,2\n9999,1\n8888,3", manual_master())
        self.assertEqual(
            [item["article"] for item in context.exception.invalid_materials],
            [8888, 9999],
        )
        self.assertIn("not found", str(context.exception))

    def test_removing_invalid_materials_keeps_valid_lines_only(self):
        lines = construir_pedido_manual(
            "1001,2\n9999,1\n8888,3", manual_master(),
            skip_invalid_materials={8888, 9999},
        )
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["ARTICULO"], 1001)
        self.assertEqual(lines[0]["CAJAS_LINEA"], 2.0)


if __name__ == "__main__":
    unittest.main()
