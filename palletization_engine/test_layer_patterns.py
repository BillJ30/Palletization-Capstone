import unittest
from collections import Counter

from layer_patterns import (
    enumerate_mixed_layer_patterns,
    enumerate_homogeneous_patterns,
    select_best_homogeneous_pattern,
)
from pallet_validation import cuboids_overlap
from palet_conformador import (
    MAX_TOTAL_PALLET_HEIGHT_CM,
    PALLET_BASE_HEIGHT_CM,
    SubLinea,
    conformar_palets_3d,
)


class LayerPatternTests(unittest.TestCase):
    def test_regular_pattern_is_exact_and_broad(self):
        pattern = select_best_homogeneous_pattern(
            article=1, station_index=1, width_cm=20.0, length_cm=30.0,
            height_cm=10.0, z_cm=PALLET_BASE_HEIGHT_CM, max_cases=8,
        )
        self.assertIsNotNone(pattern)
        self.assertEqual(len(pattern.placements), 8)
        self.assertAlmostEqual(pattern.covered_area_cm2, 4800.0)
        for placement in pattern.placements:
            self.assertGreaterEqual(placement.x_cm, 0.0)
            self.assertGreaterEqual(placement.y_cm, 0.0)
            self.assertLessEqual(placement.x_cm + placement.width_cm, 120.0 + 1e-6)
            self.assertLessEqual(placement.y_cm + placement.length_cm, 80.0 + 1e-6)
        boxes = [p.__dict__ | {
            "ancho_cm": p.width_cm, "largo_cm": p.length_cm,
            "alto_cm": p.height_cm,
        } for p in pattern.placements]
        for index, box in enumerate(boxes):
            self.assertFalse(any(cuboids_overlap(box, other) for other in boxes[index + 1:]))

    def test_execution_completes_broad_base_before_second_layer(self):
        sublinea = SubLinea(
            descripcion="SKU", cajas=8, alergeno=False,
            cajas_por_palet_real=16, peso_caja=1.0,
            cajas_por_capa=8, capas_por_palet=2, grupo_art="G",
            alto_caja_cm=10.0, ancho_caja_cm=20.0, largo_caja_cm=30.0,
            station_index=1,
        )
        pallets = conformar_palets_3d([sublinea])
        self.assertEqual(len(pallets), 1)
        self.assertEqual({box["z_cm"] for box in pallets[0].cajas_3d}, {PALLET_BASE_HEIGHT_CM})
        self.assertLessEqual(pallets[0].altura_total_cm, MAX_TOTAL_PALLET_HEIGHT_CM)

    def test_mixed_pattern_requires_one_common_top_plane(self):
        specs = [
            {"article": 1, "station_index": 1, "width_cm": 20.0,
             "length_cm": 30.0, "height_cm": 10.0},
            {"article": 2, "station_index": 2, "width_cm": 20.0,
             "length_cm": 30.0, "height_cm": 10.0},
        ]
        self.assertTrue(enumerate_mixed_layer_patterns(specs, PALLET_BASE_HEIGHT_CM))
        specs[1]["height_cm"] = 10.01
        self.assertFalse(enumerate_mixed_layer_patterns(specs, PALLET_BASE_HEIGHT_CM))

    def test_eighty_case_regression_has_eight_full_layers_and_remainder(self):
        sublinea = SubLinea(
            descripcion="CAN-REGRESSION", cajas=80, alergeno=False,
            cajas_por_palet_real=100, peso_caja=1.0,
            cajas_por_capa=9, capas_por_palet=10, grupo_art="G",
            alto_caja_cm=10.0, ancho_caja_cm=39.9, largo_caja_cm=26.6,
            station_index=1, articulo=9001,
        )
        pallet = conformar_palets_3d([sublinea])[0]
        counts = Counter(round(box["z_cm"], 6) for box in pallet.cajas_3d)
        self.assertEqual(sorted(counts.values()), [8] + [9] * 8)
        self.assertEqual(len(pallet.cajas_3d), 80)
        self.assertEqual(len(pallet.layer_patterns), 9)

    def test_case_that_cannot_fit_height_opens_a_new_pallet(self):
        sublinea = SubLinea(
            descripcion="TALL-FULL-PALLET", cajas=2, alergeno=False,
            cajas_por_palet_real=2, peso_caja=1.0,
            cajas_por_capa=1, capas_por_palet=1, grupo_art="G",
            alto_caja_cm=100.0, ancho_caja_cm=120.0, largo_caja_cm=80.0,
            station_index=1, articulo=9002,
        )
        pallets = conformar_palets_3d([sublinea])
        self.assertEqual(len(pallets), 2)
        self.assertEqual([len(pallet.cajas_3d) for pallet in pallets], [1, 1])
        self.assertTrue(all(
            box["z_cm"] + box["alto_cm"] <= MAX_TOTAL_PALLET_HEIGHT_CM + 1e-6
            for pallet in pallets for box in pallet.cajas_3d
        ))


if __name__ == "__main__":
    unittest.main()
