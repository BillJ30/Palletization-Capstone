import unittest

from palet_conformador import SubLinea, conformar_palets_3d
from placement_optimization import (
    PlacementScore,
    choose_best_feasible_pallet,
    physical_pallet_metrics,
)


class PlacementOptimizationTests(unittest.TestCase):
    def test_lexicographic_score_prefers_zero_new_pallet(self):
        better = PlacementScore(0, 1, -1, 9000, 0, 0, 0, 0, (1,))
        worse = PlacementScore(1, 2, -100, 0, 0, 0, 0, 0, (0,))
        self.assertLess(better, worse)

    def test_chooser_never_scores_candidates_outside_feasible_set(self):
        first = object()
        second = object()
        self.assertIs(choose_best_feasible_pallet([first, second], [second]), second)

    def test_single_active_does_not_open_when_existing_pallet_can_continue(self):
        line = SubLinea(
            "SKU", 2, False, 10, 1.0, 2, 1, "G",
            alto_caja_cm=10.0, ancho_caja_cm=40.0, largo_caja_cm=60.0,
            station_index=1,
        )
        pallets = conformar_palets_3d([line], operational_policy="single_active")
        self.assertEqual(len(pallets), 1)

    def test_multiple_open_policy_is_available_and_metrics_are_physical(self):
        line = SubLinea(
            "SKU", 2, False, 10, 1.0, 2, 1, "G",
            alto_caja_cm=10.0, ancho_caja_cm=40.0, largo_caja_cm=60.0,
            station_index=1,
        )
        pallets = conformar_palets_3d([line], operational_policy="multiple_open")
        metrics = physical_pallet_metrics(pallets)
        self.assertEqual(metrics["pallet_count"], 1)
        self.assertEqual(metrics["validation_violation_count"], 0)
        self.assertGreater(metrics["base_layer_union_area_utilization"], 0.0)


if __name__ == "__main__":
    unittest.main()
