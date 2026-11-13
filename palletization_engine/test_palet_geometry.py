import unittest

import palet_conformador as pc


def make_box(
    x_cm,
    y_cm,
    z_cm,
    ancho_cm=39.9,
    largo_cm=26.5,
    alto_cm=10.0,
    descripcion="BOX",
):
    return {
        "x_cm": x_cm,
        "y_cm": y_cm,
        "z_cm": z_cm,
        "ancho_cm": ancho_cm,
        "largo_cm": largo_cm,
        "alto_cm": alto_cm,
        "descripcion": descripcion,
    }


def make_sublinea(cajas, descripcion="TEST", ancho_cm=39.9, largo_cm=26.5, alto_cm=10.0):
    return pc.SubLinea(
        descripcion=descripcion,
        cajas=float(cajas),
        alergeno=False,
        cajas_por_palet_real=1.0,
        peso_caja=1.0,
        cajas_por_capa=1.0,
        capas_por_palet=1.0,
        grupo_art="TEST",
        alto_caja_cm=alto_cm,
        ancho_caja_cm=ancho_cm,
        largo_caja_cm=largo_cm,
        estabilidad="ESTABLE",
        orden_apilado=1,
    )


def assert_no_case_overlaps(palet):
    boxes = palet.cajas_3d
    for i, left in enumerate(boxes):
        for j in range(i + 1, len(boxes)):
            right = boxes[j]
            if pc.cuboids_overlap(left, right):
                left_id = left.get("descripcion", f"case[{i}]")
                right_id = right.get("descripcion", f"case[{j}]")
                raise AssertionError(
                    f"Overlap between case {i} ({left_id}) {left} and "
                    f"case {j} ({right_id}) {right}"
                )


class GeometryTests(unittest.TestCase):
    def test_faces_touch_do_not_overlap(self):
        left = make_box(0.0, 0.0, pc.MADERA_CM)
        right = make_box(39.9, 0.0, pc.MADERA_CM)
        self.assertFalse(pc.cuboids_overlap(left, right))

    def test_small_positive_intersection_is_invalid(self):
        left = make_box(0.0, 0.0, pc.MADERA_CM)
        right = make_box(39.89, 26.49, pc.MADERA_CM + 9.99)
        self.assertTrue(pc.cuboids_overlap(left, right))

    def test_same_footprint_separated_in_z_is_valid(self):
        left = make_box(0.0, 0.0, pc.MADERA_CM)
        right = make_box(0.0, 0.0, pc.MADERA_CM + 10.1)
        self.assertFalse(pc.cuboids_overlap(left, right))

    def test_rotated_orientation_collision_detection(self):
        left = make_box(0.0, 0.0, pc.MADERA_CM, ancho_cm=39.9, largo_cm=26.5)
        rotated = make_box(26.0, 0.0, pc.MADERA_CM, ancho_cm=26.5, largo_cm=39.9)
        self.assertTrue(pc.cuboids_overlap(left, rotated))

    def test_399_by_265_case_at_x36_is_invalid(self):
        left = make_box(0.0, 0.0, pc.MADERA_CM)
        bad = make_box(36.0, 0.0, pc.MADERA_CM)
        self.assertTrue(pc.cuboids_overlap(left, bad))

    def test_399_case_can_be_considered_at_x399(self):
        heightmap = [[pc.MADERA_CM] * pc.GRID_L for _ in range(pc.GRID_W)]
        placed = []
        for y0 in (0.0, 26.5, 53.0, 79.5):
            box = make_box(0.0, y0, pc.MADERA_CM)
            placed.append(box)
            pc.actualizar_heightmap(
                heightmap,
                box["x_cm"],
                box["y_cm"],
                box["ancho_cm"],
                box["largo_cm"],
                box["alto_cm"],
                box["z_cm"],
            )

        pos = pc.buscar_posicion_optima(
            heightmap,
            placed,
            39.9,
            26.5,
            10.0,
            pc.ALTURA_MAX_CM,
        )

        self.assertIsNotNone(pos)
        self.assertAlmostEqual(pos[0], 39.9, places=6)

    def test_generated_pallet_has_no_overlaps(self):
        palets = pc.conformar_palets_3d([make_sublinea(8)])
        self.assertTrue(palets)
        for palet in palets:
            assert_no_case_overlaps(palet)


if __name__ == "__main__":
    unittest.main()
