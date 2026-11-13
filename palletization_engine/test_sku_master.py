import unittest

import pandas as pd

from sku_master import build_sku_master


def dimensions(**overrides):
    row = {
        "Material": 100,
        "UMB": "ZCJ",
        "Longitud_cm": 20.0,
        "Ancho_cm": 10.0,
        "Altura_cm": 10.0,
        "Peso bruto": 2.0,
        "Grupo art.": "PA70",
        "NUM_ZPA": 100,
        "Densidad_kg_m3": 700.0,
        "Estabilidad": "MUY_ESTABLE",
        "Familia_detectada": "LATAS_330",
    }
    row.update(overrides)
    return pd.DataFrame([row])


def capacity(**overrides):
    row = {
        "Material": 100,
        "UMB": "ZCJ",
        "Cajas/Capa": 4,
        "Capas/Palet": 10,
        "BRUTO ZPA": 800.0,
    }
    row.update(overrides)
    return pd.DataFrame([row])


class SKUContractTests(unittest.TestCase):
    def test_compatible_one_to_one_pick_unit_join_passes(self):
        master, report = build_sku_master(dimensions(), capacity())
        self.assertEqual(report.valid_specs, 1)
        self.assertTrue(report.to_dict()["valid_specs"] == 1)
        self.assertEqual(master.loc[0, "CASE_WEIGHT_KG"], 2.0)
        self.assertEqual(master.loc[0, "SKU_PICK_UOM"], "ZCJ")

    def test_same_article_with_different_uom_does_not_merge(self):
        master, report = build_sku_master(dimensions(), capacity(UMB="ZUD"))
        self.assertEqual(report.valid_specs, 0)
        self.assertEqual(report.unit_incompatible[0]["code"], "UOM_MISMATCH")
        self.assertTrue(master.empty)

    def test_area_ratio_above_one_fails(self):
        master, report = build_sku_master(
            dimensions(Longitud_cm=40.0, Ancho_cm=40.0), capacity(**{"Cajas/Capa": 7})
        )
        self.assertEqual(report.valid_specs, 0)
        self.assertEqual(report.unit_incompatible[0]["code"], "LAYER_AREA_EXCEEDED")
        self.assertTrue(master.empty)

    def test_missing_dimensions_fails_before_packing(self):
        master, report = build_sku_master(dimensions(Altura_cm=None), capacity())
        self.assertEqual(report.valid_specs, 0)
        self.assertEqual(report.missing[0]["code"], "INVALID_PHYSICAL_VALUES")
        self.assertTrue(master.empty)

    def test_duplicate_conflicting_dimensions_fail(self):
        conflicting = pd.concat([dimensions(), dimensions(Ancho_cm=11.0)], ignore_index=True)
        master, report = build_sku_master(conflicting, capacity())
        self.assertEqual(report.valid_specs, 0)
        self.assertEqual(report.conflicting[0]["code"], "CONFLICTING_DIMENSIONS")
        self.assertTrue(master.empty)

    def test_missing_capacity_reference_is_allowed_with_exact_geometry(self):
        master, report = build_sku_master(dimensions(), pd.DataFrame(columns=capacity().columns))
        self.assertEqual(report.valid_specs, 1)
        self.assertIsNone(master.loc[0, "CAJAS_POR_CAPA_REFERENCE"])
        self.assertTrue(master.loc[0, "SKU_SPEC_VALID"])


if __name__ == "__main__":
    unittest.main()
