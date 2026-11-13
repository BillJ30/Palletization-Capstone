import unittest

import palet_conformador as pc
from pallet_validation import exact_support_result, validate_order_geometry


CONFIG = {
    "PALET_ANCHO_CM": pc.PALET_ANCHO_CM,
    "PALET_LARGO_CM": pc.PALET_LARGO_CM,
    "MADERA_CM": 14.4,
    "ALTURA_MAX_CM": 160.0,
    "MIN_SUPPORT_RATIO": 1.0,
    "MAX_MIXED_PALLET_GROSS_WEIGHT_KG": 1000.0,
    "PALLET_TARE_WEIGHT_KG": 0.0,
}


def case(x, y, z=14.4, w=10.0, d=10.0, h=10.0, name="BOX", station_index=1):
    return {
        "x_cm": x, "y_cm": y, "z_cm": z,
        "ancho_cm": w, "largo_cm": d, "alto_cm": h,
        "descripcion": name,
        "station_index": station_index,
        "peso_caja": 1.0,
    }


class ExactSupportTests(unittest.TestCase):
    def test_first_layer_is_fully_supported(self):
        result = exact_support_result(5, 5, 10, 10, 14.4, [], CONFIG)
        self.assertTrue(result.supported)
        self.assertEqual(result.support_ratio, 1.0)

    def test_same_size_case_supports_upper_case(self):
        result = exact_support_result(0, 0, 10, 10, 24.4, [case(0, 0)], CONFIG)
        self.assertTrue(result.supported)
        self.assertEqual(result.contact_area_cm2, 100.0)

    def test_two_boxes_can_provide_full_union_support(self):
        placed = [case(0, 0, w=5), case(5, 0, w=5)]
        result = exact_support_result(0, 0, 10, 10, 24.4, placed, CONFIG)
        self.assertTrue(result.supported)
        self.assertEqual(result.support_ratio, 1.0)

    def test_overlapping_support_rectangles_are_not_double_counted(self):
        placed = [case(0, 0, w=7), case(3, 0, w=7)]
        result = exact_support_result(0, 0, 10, 10, 24.4, placed, CONFIG)
        self.assertEqual(result.contact_area_cm2, 100.0)
        self.assertEqual(result.support_ratio, 1.0)

    def test_configured_support_thresholds(self):
        placed = [case(0, 0, w=6.9)]
        for threshold, expected in ((0.69, True), (0.99, False), (1.0, False)):
            config = dict(CONFIG, MIN_SUPPORT_RATIO=threshold)
            result = exact_support_result(0, 0, 10, 10, 24.4, placed, config)
            self.assertAlmostEqual(result.support_ratio, 0.69)
            self.assertEqual(result.supported, expected)

        full = exact_support_result(0, 0, 10, 10, 24.4, [case(0, 0)], dict(CONFIG, MIN_SUPPORT_RATIO=1.0))
        self.assertTrue(full.supported)

    def test_different_top_heights_do_not_form_one_plane(self):
        placed = [case(0, 0, w=5), case(5, 0, z=15.4, w=5)]
        result = exact_support_result(0, 0, 10, 10, 24.4, placed, CONFIG)
        self.assertFalse(result.supported)
        self.assertAlmostEqual(result.support_ratio, 0.5)

    def test_supported_case_that_intersects_another_box_is_invalid(self):
        boxes = [case(0, 0), case(5, 0, z=20.0, name="INTERSECTING"), case(0, 0, z=24.4, name="UPPER")]
        result = validate_order_geometry([{"numero": 1, "cajas_3d": boxes}], CONFIG)
        self.assertFalse(result.valid)
        self.assertTrue(any(issue.code == "OVERLAP" for issue in result.issues))

    def test_generated_order_has_no_under_supported_upper_cases(self):
        line = pc.SubLinea(
            descripcion="SUPPORT-TEST", cajas=30.0, alergeno=False,
            cajas_por_palet_real=30.0, peso_caja=1.0,
            cajas_por_capa=8.0, capas_por_palet=4.0, grupo_art="TEST",
            alto_caja_cm=10.0, ancho_caja_cm=39.9, largo_caja_cm=26.5,
            estabilidad="ESTABLE", orden_apilado=1,
        )
        palets = pc.conformar_palets_3d([line])
        result = validate_order_geometry(palets, dict(CONFIG, MIN_SUPPORT_RATIO=pc.MIN_SUPPORT_RATIO))
        self.assertTrue(result.valid, result.issues)
        self.assertFalse(any(issue.code == "UNDER_SUPPORTED" for issue in result.issues))


if __name__ == "__main__":
    unittest.main()
