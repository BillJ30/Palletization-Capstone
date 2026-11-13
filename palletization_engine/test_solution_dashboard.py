import tempfile
import unittest
from pathlib import Path

from solution_dashboard import render_solution_dashboard, write_solution_dashboard


class SolutionDashboardTests(unittest.TestCase):
    def test_dashboard_contains_written_layer_summary(self):
        result = {
            "alerta_75": False,
            "palets_picking": [{
                "descripciones_str": "SKU TEST",
                "ocupacion": 0.75,
                "altura_total_cm": 24.4,
                "altura_carga_cm": 10.0,
                "peso_bruto_total_kg": 12.0,
                "cajas_3d": [{
                    "articulo": 123, "descripcion": "SKU TEST", "x_cm": 0.0,
                    "y_cm": 0.0, "z_cm": 14.4, "ancho_cm": 39.9,
                    "largo_cm": 26.6, "alto_cm": 10.0,
                }],
            }],
        }
        html = render_solution_dashboard(result, "MANUAL")
        self.assertIn("Pallet solution dashboard", html)
        self.assertIn("SKU TEST", html)
        self.assertIn("Layer 1", html)
        self.assertIn("Exact footprint filled", html)
        self.assertIn("1 cases", html)
        self.assertNotIn("Top view", html)
        self.assertNotIn("class=\"case\"", html)
        with tempfile.TemporaryDirectory() as directory:
            path = write_solution_dashboard(result, Path(directory) / "dashboard.html", "MANUAL")
            self.assertTrue(path.exists())
            self.assertIn("120 x 80 cm", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
