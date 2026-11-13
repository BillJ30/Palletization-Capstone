import unittest

import pandas as pd

import palet_conformador as pc
from pallet_validation import validate_order_geometry
from station_route import StationRouteError, load_station_route, validate_picking_route


def line(name, station, article):
    return pc.LineaPedido(
        descripcion=name, articulo=article, grupo_art="PA70", orden_apilado=1,
        cajas_linea=1.0, cajas_por_palet_real=1.0, cajas_por_capa_real=1.0,
        capas_por_palet_real=1.0, es_palet_entero=False, semipalet=False,
        cajas_por_palet_csv=1.0, es_picking=True, tipo_resto="MANUAL",
        palets_completos=0.0, peso_palet_bruto=1.0, alergeno=False,
        alto_caja_cm=10.0, ancho_caja_cm=10.0, largo_caja_cm=10.0,
        case_weight_kg=1.0, station_index=station, station_name=f"S{station}",
    )


def box(z, station, name):
    return {
        "x_cm": 0.0, "y_cm": 0.0, "z_cm": z,
        "ancho_cm": 10.0, "largo_cm": 10.0, "alto_cm": 10.0,
        "descripcion": name, "station_index": station,
        "peso_caja": 1.0,
    }


class StationRouteTests(unittest.TestCase):
    def test_route_config_loads_documented_station_mappings(self):
        route = load_station_route()
        self.assertEqual(route["PA70"].station_index, 1)
        self.assertEqual(route["PA14"].station_index, 5)

    def test_lines_are_processed_in_station_order_and_stable_within_station(self):
        result = pc.procesar_pedido_dict(
            "ORDER",
            [line("LATE", 2, 2), line("EARLY-A", 1, 3), line("EARLY-B", 1, 4)],
            usar_3d=True,
        )
        descriptions = [box["descripcion"] for box in result["palets_picking"][0]["cajas_3d"]]
        self.assertEqual(descriptions[:3], ["EARLY-A", "EARLY-B", "LATE"])

    def test_missing_route_mapping_fails(self):
        frame = pd.DataFrame({"ES_PICKING": [True], "GRUPO_ART": ["UNKNOWN"]})
        with self.assertRaises(StationRouteError) as raised:
            validate_picking_route(frame, load_station_route())
        self.assertIn("UNKNOWN", str(raised.exception))

    def test_missing_station_on_picking_line_fails_before_packing(self):
        with self.assertRaises(StationRouteError):
            pc.procesar_pedido_dict("ORDER", [line("UNMAPPED", None, 5)])

    def test_earlier_station_above_later_station_fails(self):
        result = validate_order_geometry(
            [{"numero": 1, "cajas_3d": [box(14.4, 2, "LATER"), box(24.4, 1, "EARLIER")]}],
            {"MADERA_CM": 14.4, "ALTURA_MAX_CM": 160.0, "MIN_SUPPORT_RATIO": 1.0,
             "MAX_MIXED_PALLET_GROSS_WEIGHT_KG": 1000.0, "PALLET_TARE_WEIGHT_KG": 0.0},
        )
        self.assertFalse(result.valid)
        self.assertTrue(any(issue.code == "STATION_ORDER_VIOLATION" for issue in result.issues))

    def test_later_station_above_earlier_station_passes(self):
        result = validate_order_geometry(
            [{"numero": 1, "cajas_3d": [box(14.4, 1, "EARLIER"), box(24.4, 2, "LATER")]}],
            {"MADERA_CM": 14.4, "ALTURA_MAX_CM": 160.0, "MIN_SUPPORT_RATIO": 1.0,
             "MAX_MIXED_PALLET_GROSS_WEIGHT_KG": 1000.0, "PALLET_TARE_WEIGHT_KG": 0.0},
        )
        self.assertTrue(result.valid, result.issues)


if __name__ == "__main__":
    unittest.main()
