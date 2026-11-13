"""Bounded exact layer-pattern construction."""

from dataclasses import dataclass
from pallet_validation import cuboids_overlap


# Planner x/y bounds: x is the 120 cm direction, y is the 80 cm direction.
PALLET_WIDTH_CM = 120.0
PALLET_LENGTH_CM = 80.0
EPS_CM = 1e-6
# Construction requires a genuinely common top plane; this is independent of
# the legacy support/search tolerances.
CONSTRUCTION_LAYER_TOLERANCE_CM = 1e-6


@dataclass(frozen=True)
class PlannedPlacement:
    article: int | str
    station_index: int
    x_cm: float
    y_cm: float
    z_cm: float
    width_cm: float
    length_cm: float
    height_cm: float
    rotated: bool
    layer_id: int


@dataclass(frozen=True)
class LayerPattern:
    placements: tuple[PlannedPlacement, ...]
    covered_area_cm2: float
    utilization: float
    top_z_cm: float


def _grid(x0, x1, y0, y1, width, length, article, station, z, height, layer_id, rotated):
    placements = []
    y = y0
    while y + length <= y1 + EPS_CM:
        x = x0
        while x + width <= x1 + EPS_CM:
            placements.append(PlannedPlacement(
                article=article, station_index=station,
                x_cm=round(x, 6), y_cm=round(y, 6), z_cm=round(z, 6),
                width_cm=width, length_cm=length, height_cm=height,
                rotated=rotated, layer_id=layer_id,
            ))
            x += width
        y += length
    return placements


def _candidate_patterns(article, station, width, length, height, z, layer_id):
    orientations = [(width, length, False), (length, width, True)]
    candidates = []
    for first_w, first_d, first_rotated in orientations:
        candidates.append(_grid(
            0.0, PALLET_WIDTH_CM, 0.0, PALLET_LENGTH_CM,
            first_w, first_d, article, station, z, height, layer_id, first_rotated,
        ))

    # Two-shelf guillotine candidates. Split coordinates are exact dimension
    # boundaries, so no regular grid border is used as physical geometry.
    for left_w in sorted({0.0, PALLET_WIDTH_CM, width, length, 2 * width, 2 * length}):
        if left_w <= EPS_CM or left_w >= PALLET_WIDTH_CM - EPS_CM:
            continue
        left = _grid(0.0, left_w, 0.0, PALLET_LENGTH_CM,
                     width, length, article, station, z, height, layer_id, False)
        right = _grid(left_w, PALLET_WIDTH_CM, 0.0, PALLET_LENGTH_CM,
                      length, width, article, station, z, height, layer_id, True)
        candidates.append(left + right)
        left = _grid(0.0, left_w, 0.0, PALLET_LENGTH_CM,
                     length, width, article, station, z, height, layer_id, True)
        right = _grid(left_w, PALLET_WIDTH_CM, 0.0, PALLET_LENGTH_CM,
                      width, length, article, station, z, height, layer_id, False)
        candidates.append(left + right)

    for bottom_d in sorted({0.0, PALLET_LENGTH_CM, width, length, 2 * width, 2 * length}):
        if bottom_d <= EPS_CM or bottom_d >= PALLET_LENGTH_CM - EPS_CM:
            continue
        bottom = _grid(0.0, PALLET_WIDTH_CM, 0.0, bottom_d,
                       width, length, article, station, z, height, layer_id, False)
        top = _grid(0.0, PALLET_WIDTH_CM, bottom_d, PALLET_LENGTH_CM,
                    length, width, article, station, z, height, layer_id, True)
        candidates.append(bottom + top)
    return candidates


def _valid_pattern(placements, placed):
    boxes = [{
        "x_cm": p.x_cm, "y_cm": p.y_cm, "z_cm": p.z_cm,
        "ancho_cm": p.width_cm, "largo_cm": p.length_cm, "alto_cm": p.height_cm,
    } for p in placements]
    for box in boxes:
        if box["x_cm"] < -EPS_CM or box["y_cm"] < -EPS_CM:
            return False
        if box["x_cm"] + box["ancho_cm"] > PALLET_WIDTH_CM + EPS_CM:
            return False
        if box["y_cm"] + box["largo_cm"] > PALLET_LENGTH_CM + EPS_CM:
            return False
    for index, box in enumerate(boxes):
        if any(cuboids_overlap(box, other) for other in boxes[index + 1:]):
            return False
        if any(cuboids_overlap(box, other) for other in placed):
            return False
    return True


def _pattern_key(pattern):
    placements = pattern.placements
    covered = pattern.covered_area_cm2
    # Exact covered area is primary after count. The remaining terms make ties
    # deterministic without introducing a packing objective beyond the layer.
    centroid_x = sum((p.x_cm + p.width_cm / 2) * p.width_cm * p.length_cm for p in placements) / max(covered, 1.0)
    centroid_y = sum((p.y_cm + p.length_cm / 2) * p.width_cm * p.length_cm for p in placements) / max(covered, 1.0)
    coords = tuple((p.x_cm, p.y_cm, p.rotated) for p in placements)
    return (-len(placements), -covered, PALLET_WIDTH_CM * PALLET_LENGTH_CM - covered,
            abs(centroid_x - PALLET_WIDTH_CM / 2) + abs(centroid_y - PALLET_LENGTH_CM / 2), coords)


def enumerate_homogeneous_patterns(
    article, station_index, width_cm, length_cm, height_cm,
    z_cm, layer_id=1, max_cases=None, placed=(),
):
    patterns = []
    for placements in _candidate_patterns(
        article, station_index, width_cm, length_cm, height_cm, z_cm, layer_id
    ):
        if max_cases is not None:
            placements = placements[:max_cases]
        if not placements or not _valid_pattern(placements, placed):
            continue
        covered = sum(p.width_cm * p.length_cm for p in placements)
        patterns.append(LayerPattern(
            placements=tuple(placements),
            covered_area_cm2=covered,
            utilization=covered / (PALLET_WIDTH_CM * PALLET_LENGTH_CM),
            top_z_cm=z_cm + height_cm,
        ))
    return tuple(sorted(patterns, key=_pattern_key))


def select_best_homogeneous_pattern(*args, **kwargs):
    patterns = enumerate_homogeneous_patterns(*args, **kwargs)
    return patterns[0] if patterns else None


def enumerate_mixed_layer_patterns(
    specs, z_cm, layer_id=1, max_cases=None, placed=(),
    construction_tolerance_cm=CONSTRUCTION_LAYER_TOLERANCE_CM,
):
    """Enumerate bounded two-shelf patterns for compatible SKU remainders.

    Each spec is a mapping with ``article``, ``station_index``, ``width_cm``,
    ``length_cm``, ``height_cm`` and optional ``remaining``.  The function is
    intentionally conservative: all cases in a pattern share one top plane,
    and shelf order follows station order.
    """
    specs = sorted(specs, key=lambda spec: spec["station_index"])
    if not specs or any(
        abs(float(spec["height_cm"]) - float(specs[0]["height_cm"]))
        > construction_tolerance_cm for spec in specs
    ):
        return ()
    candidates = []
    first = specs[0]
    for second in specs[1:]:
        for split in sorted({first["width_cm"], first["length_cm"],
                             second["width_cm"], second["length_cm"]}):
            if split <= EPS_CM or split >= PALLET_WIDTH_CM - EPS_CM:
                continue
            left = _grid(
                0.0, split, 0.0, PALLET_LENGTH_CM,
                first["width_cm"], first["length_cm"], first["article"],
                first["station_index"], z_cm, first["height_cm"], layer_id, False,
            )
            right = _grid(
                split, PALLET_WIDTH_CM, 0.0, PALLET_LENGTH_CM,
                second["width_cm"], second["length_cm"], second["article"],
                second["station_index"], z_cm, second["height_cm"], layer_id, False,
            )
            placements = left + right
            limit = max_cases
            if limit is not None:
                placements = placements[:limit]
            if placements and _valid_pattern(placements, placed):
                area = sum(p.width_cm * p.length_cm for p in placements)
                candidates.append(LayerPattern(
                    placements=tuple(placements), covered_area_cm2=area,
                    utilization=area / (PALLET_WIDTH_CM * PALLET_LENGTH_CM),
                    top_z_cm=z_cm + first["height_cm"],
                ))
    return tuple(sorted(candidates, key=_pattern_key))


def select_best_mixed_layer_pattern(*args, **kwargs):
    patterns = enumerate_mixed_layer_patterns(*args, **kwargs)
    return patterns[0] if patterns else None
