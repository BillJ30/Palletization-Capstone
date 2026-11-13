import unittest

from palet_conformador import LineaPedido
from promotion_capacity import additional_cases


def line(article, cases=1, weight=1.0, width=10.0, length=10.0, height=10.0):
    return LineaPedido(
        descripcion=f"SKU-{article}", articulo=article, grupo_art="G", orden_apilado=1,
        cajas_linea=cases, cajas_por_palet_real=100, cajas_por_capa_real=10,
        capas_por_palet_real=10, es_palet_entero=False, semipalet=False,
        cajas_por_palet_csv=100, es_picking=True, tipo_resto="", palets_completos=0,
        peso_palet_bruto=weight, alergeno=False, alto_caja_cm=height,
        ancho_caja_cm=width, largo_caja_cm=length, estabilidad="",
        case_weight_kg=weight, station_index=1, station_name="TEST",
    )


class PromotionCapacityTests(unittest.TestCase):
    def test_weight_limited_capacity_is_integer_and_validated(self):
        order = [line(1, cases=1, weight=800.0)]
        result = additional_cases(order, line(2, weight=100.0), upper_bound=4)
        self.assertEqual(result.additional_cases_without_new_pallet, 2)
        self.assertEqual(result.baseline_pallet_count, result.resulting_pallet_count)

    def test_height_limited_capacity_returns_zero(self):
        order = [line(1, cases=1, height=100.0, width=80.0, length=120.0)]
        result = additional_cases(order, line(2, height=100.0, width=80.0, length=120.0), upper_bound=2)
        self.assertEqual(result.additional_cases_without_new_pallet, 0)

    def test_unsupported_geometry_returns_zero(self):
        order = [line(1, cases=1, width=80.0, length=120.0, height=10.0)]
        candidate = line(2, width=81.0, length=120.0, height=10.0)
        result = additional_cases(order, candidate, upper_bound=1)
        self.assertEqual(result.additional_cases_without_new_pallet, 0)

    def test_trials_do_not_mutate_original_case_counts(self):
        order = [line(1, cases=2)]
        original = order[0].cajas_linea
        additional_cases(order, line(2), upper_bound=3)
        self.assertEqual(order[0].cajas_linea, original)


if __name__ == "__main__":
    unittest.main()
