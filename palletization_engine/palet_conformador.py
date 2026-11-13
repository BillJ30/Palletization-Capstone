"""
Algoritmo de conformaciÃ³n logÃ­stica de palets para almacÃ©n de distribuciÃ³n de bebidas.

Fuentes de verdad:
  - inputs/dataset_logistico_lineas.csv        â†’ lÃ­neas de pedido
  - inputs/Packaging_Logistics_Data.csv        â†’ dimensiones precisas + densidad por SKU
  - inputs/productos_con_dimensiones_2.csv     â†’ Cajas/Capa, Capas/Palet, BRUTO ZPA

VersiÃ³n 3: nueva fuente de dimensiones con densidad â†’ estabilidad automÃ¡tica.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
import csv
import pandas as pd
from logistics_csv import read_logistics_csv
from sku_master import InvalidSKUContractError, build_sku_master
from station_route import (
    StationRouteError,
    load_station_route,
    station_for,
    validate_picking_route,
)
from pallet_validation import (
    SupportResult,
    exact_support_result,
    raise_if_invalid_order_geometry,
)
from layer_patterns import select_best_homogeneous_pattern
from placement_optimization import choose_best_feasible_pallet
from release_audit import assert_release_ready
from weight_config import (
    MAX_MIXED_PALLET_GROSS_WEIGHT_KG,
    PALLET_TARE_WEIGHT_KG,
)


# ---------------------------------------------------------------------------
# CONSTANTES FÃSICAS
# ---------------------------------------------------------------------------

EPS_CM           = 1e-6
# Canonical exported footprint is x=0..120, y=0..80.
PALLET_LENGTH_CM            = 120.0
PALLET_WIDTH_CM             = 80.0
# Internal x is the long direction and internal y is the short direction.
PALET_ANCHO_CM              = PALLET_LENGTH_CM
PALET_LARGO_CM              = PALLET_WIDTH_CM
# Warehouse contract: total height includes the 14.4 cm wooden base.
PALLET_BASE_HEIGHT_CM       = 14.4
PALLET_TOTAL_HEIGHT_CM      = 180.0
MAX_TOTAL_PALLET_HEIGHT_CM  = PALLET_TOTAL_HEIGHT_CM
MAX_CARGO_HEIGHT_CM         = MAX_TOTAL_PALLET_HEIGHT_CM - PALLET_BASE_HEIGHT_CM
assert PALLET_LENGTH_CM > 0.0 and PALLET_WIDTH_CM > 0.0
assert PALLET_BASE_HEIGHT_CM > 0.0
assert MAX_TOTAL_PALLET_HEIGHT_CM > PALLET_BASE_HEIGHT_CM
assert abs(MAX_CARGO_HEIGHT_CM - 165.6) <= EPS_CM
# Deprecated compatibility aliases. New call sites use the explicit names above.
MADERA_CM     = PALLET_BASE_HEIGHT_CM
ALTURA_MAX_CM = MAX_TOTAL_PALLET_HEIGHT_CM
TOLERANCIA_ALTO  = 3.0
SOPORTE_MIN      = 0.70
MIN_SUPPORT_RATIO = 1.0
HUECO_MIN_CM     = 5.0
CAPA_LLENA_PCT   = 0.85
GRID_CM          = 4       # resoluciÃ³n del heightmap (cm por celda)
GRID_W           = 30      # 120 cm / 4 cm = 30 celdas en X
GRID_L           = 20      # 80 cm / 4 cm = 20 celdas en Y


# ---------------------------------------------------------------------------
# UMBRALES DE DENSIDAD â†’ ESTABILIDAD
# ---------------------------------------------------------------------------
# BIB/Latas: 700-960 kg/mÂ³  |  PET: 550-620  |  VR: 520-550  |  Especiales: <400

DENSIDAD_MUY_ESTABLE = 700   # kg/mÂ³ â†’ latas y BIB
DENSIDAD_ESTABLE     = 550   # kg/mÂ³ â†’ VNR, VR, PET grandes
DENSIDAD_MEDIA       = 400   # kg/mÂ³ â†’ PET medianos
# densidad < 400 â†’ INESTABLE


def densidad_a_estabilidad(densidad: float) -> str:
    """Convierte densidad kg/mÂ³ a categorÃ­a de estabilidad."""
    if pd.isna(densidad) or densidad <= 0:
        return "MEDIA"
    if densidad >= DENSIDAD_MUY_ESTABLE:
        return "MUY_ESTABLE"
    if densidad >= DENSIDAD_ESTABLE:
        return "ESTABLE"
    if densidad >= DENSIDAD_MEDIA:
        return "MEDIA"
    return "INESTABLE"


# ---------------------------------------------------------------------------
# ORDEN DE APILADO POR FAMILIA (fallback)
# ---------------------------------------------------------------------------

ORDEN_FAMILIA: dict[str, int] = {
    # â”€â”€ 1 Â· LATA 330 + LATA 500 (base del palet) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    "PA70": 1, "PA71": 1, "PA72": 1, "PA74": 1,  # LATA 330
    "PA75": 1,                                     # LATA 500
    # â”€â”€ 2 Â· LATA 250 + LATA 200 â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    "PA65": 2,                                     # LATA 250
    "PA60": 2, "PA62": 2, "PA64": 2,              # LATA 200
    # â”€â”€ 3 Â· PET 500 + PET 2000 â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    "PA34": 3, "PA35": 3, "PA46": 3, "PA56": 3,  # PET 500
    "PA50": 3, "PA52": 3, "PA54": 3,              # PET 2000
    # â”€â”€ 4 Â· PET 1.5L + PET 1L + PET 600/650 â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    "PA41": 4, "PA42": 4, "PA43": 4, "PA45": 4,  # PET 1.5L
    "PA27": 4, "PA39": 4, "PA40": 4, "PA44": 4,  # PET 1L
    "PA37": 4,                                     # PET 600/650
    # â”€â”€ 5 Â· VNR + PET 1.25L â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    "PA15": 5, "PA16": 5, "PA17": 5,              # VNR
    "PA21": 5, "PA25": 5, "PA26": 5,              # VNR
    "PA38": 5,                                     # PET 1.25L
    # â”€â”€ 6 Â· BIB + CAPRI â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    "PA86": 6, "PA87": 6, "PA88": 6, "PA89": 6,  # BIB
    "PA78": 6, "PA79": 3,                          # CAPRI
    # â”€â”€ 7 Â· VR (vidrio retornable, techo del palet) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    "PA01": 7, "PA04": 7, "PA06": 7, "PA07": 7,  # VR
    "PA08": 7, "PA09": 7, "PA11": 7, "PA14": 5,  # VR
    "PA98": 7,                                     # VR
    # â”€â”€ 8 Â· Especiales / Buffer â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    "NESP": 8, "PAC2": 8, "PA81": 8,
    "PATC": 8, "PAVA": 8, "PA99": 8,
}


# ---------------------------------------------------------------------------
# CARGA Y ENRIQUECIMIENTO DE DATOS
# ---------------------------------------------------------------------------

def cargar_datos(
    csv_path: str = "inputs/dataset_logistico_lineas.csv",
    dim_path: str = "inputs/Packaging_Logistics_Data.csv",
    dim_path_old: str = "inputs/productos_con_dimensiones_2.csv",
    diagnostics: bool = False,
) -> pd.DataFrame:
    """
    Carga el dataset logÃ­stico y lo enriquece con dimensiones reales.

    Fuentes:
      - Packaging_Logistics_Data.csv       â†’ dimensiones precisas + densidad
      - productos_con_dimensiones_2(in).csv â†’ Cajas/Capa, Capas/Palet, BRUTO ZPA

    Filtro: excluye formatos de palet completo (1/4D, 1/2D, SD, KEG, MIX:)
    que tienen Altura_cm = altura del palet en lugar de la caja individual.
    """
    df_log = read_logistics_csv(csv_path)
    ingestion_metrics = df_log.attrs["ingestion_metrics"]
    if ingestion_metrics.final_dataframe_rows != len(df_log):
        raise ValueError(
            "Logistics CSV reconciliation mismatch before business filtering: "
            f"metrics={ingestion_metrics.final_dataframe_rows}, rows={len(df_log)}"
        )
    station_route = load_station_route()
    validate_picking_route(df_log, station_route)

    # â”€â”€ Nuevo fichero: dimensiones precisas + densidad â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    df_nuevo = pd.read_csv(dim_path, encoding="utf-8-sig", sep=";", decimal=",")

    # Excluir formatos de palet completo (tienen Altura_cm incorrecta)
    df_nuevo = df_nuevo[~df_nuevo["Número de material"].str.contains(
        r"1/4D|1/2D|SD\d|KEG|MIX:", na=False, regex=True
    )].copy()

    # Calcular estabilidad automÃ¡ticamente desde densidad
    df_nuevo["Estabilidad"] = df_nuevo["Densidad_kg_m3"].apply(densidad_a_estabilidad)

    # Normalizar clave de join
    df_nuevo["ARTICULO"] = pd.to_numeric(df_nuevo["Material"], errors="coerce").astype("Int64")

    # â”€â”€ CSV antiguo: Cajas/Capa, Capas/Palet, BRUTO ZPA â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    df_viejo = pd.read_csv(dim_path_old, encoding="utf-8-sig", sep=";", decimal=",")
    df_viejo["ARTICULO"] = pd.to_numeric(df_viejo["Material"], errors="coerce").astype("Int64")

    # Build one validated physical spec per article before joining order rows.
    df_dim, sku_report = build_sku_master(df_nuevo, df_viejo, route=station_route)
    if diagnostics:
        print(
            "SKU master validation: "
            f"candidates={sku_report.candidate_rows}, valid={sku_report.valid_specs}, "
            f"missing={len(sku_report.missing)}, conflicting={len(sku_report.conflicting)}, "
            f"unit_incompatible={len(sku_report.unit_incompatible)}"
        )

    # Normalizar clave logÃ­stico
    df_log["ARTICULO"] = pd.to_numeric(df_log["ARTICULO"], errors="coerce").astype("Int64")

    # â”€â”€ JOIN principal: logÃ­stico + dimensiones â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    df = df_log.merge(
        df_dim[[
            "ARTICULO", "SKU_PICK_UOM", "SKU_SPEC_VALID", "Grupo art.", "NUM_ZPA",
            "CAJAS_POR_CAPA_REFERENCE", "CAPAS_POR_PALET_REFERENCE", "BRUTO ZPA",
            "ALTO_CAJA_CM", "ANCHO_CAJA_CM", "LARGO_CAJA_CM", "CASE_WEIGHT_KG",
            "STATION_INDEX", "STATION_NAME", "ROUTE_SEQUENCE_VERSION", "MAX_LOAD_ABOVE_KG",
            "Densidad_kg_m3", "Estabilidad", "Familia_detectada",
        ]],
        on="ARTICULO",
        how="left",
    )
    df["SKU_SPEC_VALID"] = df["SKU_SPEC_VALID"].astype("boolean").fillna(False).astype(bool)
    df["STATION_INDEX"] = df["GRUPO_ART"].map(
        lambda key: station_for(key, station_route).station_index
        if pd.notna(key) else pd.NA
    )
    df["STATION_NAME"] = df["GRUPO_ART"].map(
        lambda key: station_for(key, station_route).station_name
        if pd.notna(key) else pd.NA
    )

    # Advertir SKUs sin dimensiones
    sin_dims = df[~df["SKU_SPEC_VALID"]]["ARTICULO"].dropna().unique()
    if diagnostics and len(sin_dims) > 0:
        print(f"ADVERTENCIA: {len(sin_dims)} SKUs sin dimensiones: {sin_dims[:5].tolist()}")

    # GeometrÃ­a real con fallback al logÃ­stico
    df["CAJAS_POR_CAPA_REAL"] = df["CAJAS_POR_CAPA_REFERENCE"]
    df["CAPAS_POR_PALET_REAL"] = df["CAPAS_POR_PALET_REFERENCE"]
    df["CAJAS_POR_CAPA_REAL"] = df["CAJAS_POR_CAPA_REAL"].fillna(0.0)
    df["CAPAS_POR_PALET_REAL"] = df["CAPAS_POR_PALET_REAL"].fillna(0.0)
    df["CAJAS_POR_PALET_REAL"] = df["CAJAS_POR_CAPA_REAL"] * df["CAPAS_POR_PALET_REAL"]

    # Compatibility field; the authoritative route field is STATION_INDEX.
    df["ORDEN_APILADO"] = df["STATION_INDEX"].fillna(0).astype(int)

    # AlÃ©rgenos: posiciones 327-338 del pasillo
    df["ES_ALERGENO"] = df["NUM_ZPA"].between(327, 338, inclusive="both")

    df.attrs["sku_validation_report"] = sku_report
    df.attrs["sku_master"] = df_dim
    df.attrs["station_route"] = station_route

    df = df[df["CAJAS_LINEA"] > 0].copy()
    return df


# ---------------------------------------------------------------------------
# REGLAS FÃSICAS
# ---------------------------------------------------------------------------

def pueden_compartir_capa(alto_a: float, alto_b: float) -> bool:
    if alto_a <= 0 or alto_b <= 0:
        return False
    return abs(alto_a - alto_b) <= TOLERANCIA_ALTO


def cajas_max_por_capa(ancho_cm: float, largo_cm: float) -> int:
    if ancho_cm <= 0 or largo_cm <= 0:
        return 0
    return int(PALET_ANCHO_CM / ancho_cm) * int(PALET_LARGO_CM / largo_cm)


def intervals_overlap_positive(a0, a1, b0, b1, eps=EPS_CM):
    return min(a1, b1) - max(a0, b0) > eps


def cuboids_overlap(a: dict, b: dict, eps=EPS_CM) -> bool:
    return (
        intervals_overlap_positive(
            a["x_cm"], a["x_cm"] + a["ancho_cm"],
            b["x_cm"], b["x_cm"] + b["ancho_cm"],
            eps,
        )
        and intervals_overlap_positive(
            a["y_cm"], a["y_cm"] + a["largo_cm"],
            b["y_cm"], b["y_cm"] + b["largo_cm"],
            eps,
        )
        and intervals_overlap_positive(
            a["z_cm"], a["z_cm"] + a["alto_cm"],
            b["z_cm"], b["z_cm"] + b["alto_cm"],
            eps,
        )
    )


def placement_has_collision(candidate: dict, placed: list[dict]) -> bool:
    return any(cuboids_overlap(candidate, other) for other in placed)


def soporte_real_caja(
    placed: list[dict],
    x0_cm: float, y0_cm: float,
    ancho_cm: float, largo_cm: float,
    base_z_cm: float,
    min_support_ratio: float = MIN_SUPPORT_RATIO,
) -> SupportResult:
    """Return exact support for one candidate footprint and one base plane."""
    return exact_support_result(
        x0_cm, y0_cm, ancho_cm, largo_cm, base_z_cm, placed,
        {
            "PALET_ANCHO_CM": PALET_ANCHO_CM,
            "PALET_LARGO_CM": PALET_LARGO_CM,
            "PALLET_BASE_HEIGHT_CM": PALLET_BASE_HEIGHT_CM,
            "MIN_SUPPORT_RATIO": min_support_ratio,
        },
    )


def actualizar_heightmap(
    heightmap: list,
    x0_cm: float, y0_cm: float,
    ancho_cm: float, largo_cm: float,
    alto_cm: float,
    altura_base: float,
) -> None:
    """Actualiza el heightmap tras colocar una caja en (x0, y0) con las dimensiones dadas."""
    ix0 = int(x0_cm / GRID_CM)
    iy0 = int(y0_cm / GRID_CM)
    ix1 = min(GRID_W, max(ix0 + 1, int((x0_cm + ancho_cm) / GRID_CM)))
    iy1 = min(GRID_L, max(iy0 + 1, int((y0_cm + largo_cm) / GRID_CM)))
    nueva_altura = altura_base + alto_cm
    for ix in range(ix0, ix1):
        for iy in range(iy0, iy1):
            heightmap[ix][iy] = nueva_altura


def buscar_posicion_optima(
    heightmap: list,
    *args,
    placed: list[dict] | None = None,
    max_base: float | None = None,
) -> tuple[float, float, float, float, float] | None:
    """
    Estrategia bottom-left-fill compacta con rotación de cajas.
    Prueba las dos orientaciones posibles (normal y rotada 90°).
    Si la caja es cuadrada, solo prueba una orientación.
    Devuelve (x0, y0, h_base, ancho_usado, largo_usado) o None.
    """
    if len(args) == 5 and placed is None and isinstance(args[0], list):
        placed, ancho_cm, largo_cm, alto_cm, altura_max = args
    elif len(args) == 4:
        ancho_cm, largo_cm, alto_cm, altura_max = args
    elif len(args) == 5:
        ancho_cm, largo_cm, alto_cm, altura_max = args[:4]
    else:
        raise TypeError("buscar_posicion_optima expects 4 or 5 positional arguments after heightmap")

    if ancho_cm <= 0 or largo_cm <= 0 or alto_cm <= 0:
        return None
    if placed is None:
        placed = []

    es_cuadrada = abs(ancho_cm - largo_cm) < 1e-6
    orientaciones = [(ancho_cm, largo_cm)]
    if not es_cuadrada:
        orientaciones.append((largo_cm, ancho_cm))

    mejor = None
    mejor_h     = float("inf")
    mejor_x     = float("inf")
    mejor_y     = float("inf")
    mejor_ancho = ancho_cm
    mejor_largo = largo_cm

    for w, d in orientaciones:
        candidatos: set[tuple[float, float]] = set()

        x_edges = {0.0}
        y_edges = {0.0}
        for box in placed:
            x_edges.update({
                float(box["x_cm"]),
                float(box["x_cm"]) + float(box["ancho_cm"]),
            })
            y_edges.update({
                float(box["y_cm"]),
                float(box["y_cm"]) + float(box["largo_cm"]),
            })

        for edge_x in x_edges:
            for x0 in (edge_x, edge_x - w):
                if x0 < -EPS_CM or x0 > PALET_ANCHO_CM - w + EPS_CM:
                    continue
                for edge_y in y_edges:
                    for y0 in (edge_y, edge_y - d):
                        if y0 < -EPS_CM or y0 > PALET_LARGO_CM - d + EPS_CM:
                            continue
                        candidatos.add((round(max(0.0, x0), 6), round(max(0.0, y0), 6)))

        n_cols = max(1, int(PALET_ANCHO_CM / w))
        n_rows = max(1, int(PALET_LARGO_CM / d))
        for col in range(n_cols):
            for row in range(n_rows):
                x0 = round(col * w, 6)
                y0 = round(row * d, 6)
                if x0 + w <= PALET_ANCHO_CM + 1e-6:
                    if y0 + d <= PALET_LARGO_CM + 1e-6:
                        candidatos.add((x0, y0))

        base_planes = {PALLET_BASE_HEIGHT_CM}
        for box in placed:
            base_planes.add(float(box["z_cm"]) + float(box["alto_cm"]))

        for x0, y0 in sorted(candidatos):
            for h_base in sorted(base_planes):
                if max_base is not None and h_base > max_base + EPS_CM:
                    continue
                if h_base + alto_cm > altura_max + EPS_CM:
                    continue

                support = soporte_real_caja(
                    placed, x0, y0, w, d, h_base,
                )
                if not support.supported:
                    continue

                candidate = {
                    "x_cm": x0,
                    "y_cm": y0,
                    "z_cm": h_base,
                    "ancho_cm": w,
                    "largo_cm": d,
                    "alto_cm": alto_cm,
                }
                if placement_has_collision(candidate, placed):
                    continue

                if (h_base < mejor_h - EPS_CM
                        or (abs(h_base - mejor_h) < EPS_CM and x0 < mejor_x - EPS_CM)
                        or (abs(h_base - mejor_h) < EPS_CM and abs(x0 - mejor_x) < EPS_CM
                            and y0 < mejor_y - EPS_CM)):
                    mejor_h     = h_base
                    mejor_x     = x0
                    mejor_y     = y0
                    mejor_ancho = w
                    mejor_largo = d
                    mejor = (x0, y0, h_base, w, d)

    return mejor
def posiciones_cajas_en_bloque(
    x0_cm: float,
    y0_cm: float,
    cajas: float,
    ancho_cm: float,
    largo_cm: float,
) -> list[tuple[float, float]]:
    """Devuelve las posiciones individuales de las cajas dentro de un bloque rectangular."""
    if cajas <= 0 or ancho_cm <= 0 or largo_cm <= 0:
        return []

    cajas_por_fila = max(int(PALET_LARGO_CM / largo_cm), 1)
    posiciones = []
    for idx in range(int(round(cajas))):
        col = idx // cajas_por_fila
        fila = idx % cajas_por_fila
        posiciones.append((x0_cm + col * ancho_cm, y0_cm + fila * largo_cm))
    return posiciones


def soporte_bloque_cajas(
    placed: list[dict],
    x0_cm: float,
    y0_cm: float,
    cajas: float,
    ancho_cm: float,
    largo_cm: float,
) -> tuple[bool, float]:
    """Validate each box in a block against exact support planes."""
    base_ref = None
    for x_cm, y_cm in posiciones_cajas_en_bloque(x0_cm, y0_cm, cajas, ancho_cm, largo_cm):
        candidatos = {PALLET_BASE_HEIGHT_CM}
        candidatos.update(
            float(box["z_cm"]) + float(box["alto_cm"])
            for box in placed
        )
        soportes = [
            soporte_real_caja(placed, x_cm, y_cm, ancho_cm, largo_cm, base)
            for base in sorted(candidatos)
        ]
        soporte = next((item for item in soportes if item.supported), None)
        if soporte is None:
            return False, 0.0
        if base_ref is None:
            base_ref = soporte.base_z_cm
        elif abs(soporte.base_z_cm - base_ref) > EPS_CM:
            return False, 0.0

    return True, base_ref if base_ref is not None else 0.0


def actualizar_heightmap_bloque(
    heightmap: list,
    x0_cm: float,
    y0_cm: float,
    cajas: float,
    ancho_cm: float,
    largo_cm: float,
    alto_cm: float,
    altura_base: float,
) -> None:
    """Actualiza el heightmap caja por caja para un bloque rectangular."""
    for x_cm, y_cm in posiciones_cajas_en_bloque(x0_cm, y0_cm, cajas, ancho_cm, largo_cm):
        actualizar_heightmap(
            heightmap,
            x_cm, y_cm,
            ancho_cm, largo_cm,
            alto_cm, altura_base,
        )


# ---------------------------------------------------------------------------
# ESTRUCTURAS DE DATOS
# ---------------------------------------------------------------------------

@dataclass
class LineaPedido:
    descripcion:          str
    articulo:             int
    grupo_art:            str
    orden_apilado:        int
    cajas_linea:          float
    cajas_por_palet_real: float
    cajas_por_capa_real:  float
    capas_por_palet_real: float
    es_palet_entero:      bool
    semipalet:            bool
    cajas_por_palet_csv:  float
    es_picking:           bool
    tipo_resto:           str
    palets_completos:     float
    peso_palet_bruto:     float
    alergeno:             bool
    alto_caja_cm:         float = 0.0
    ancho_caja_cm:        float = 0.0
    largo_caja_cm:        float = 0.0
    estabilidad:          str   = ""
    case_weight_kg:        float | None = None
    station_index:         int | None = None
    station_name:          str | None = None
    max_load_above_kg:     float | None = None

    @property
    def peso_caja(self) -> float:
        if self.case_weight_kg is not None and pd.notna(self.case_weight_kg) and self.case_weight_kg > 0:
            return float(self.case_weight_kg)
        if self.cajas_por_palet_real > 0 and self.peso_palet_bruto > 0:
            return self.peso_palet_bruto / self.cajas_por_palet_real
        return 0.0

    @property
    def tiene_dimensiones(self) -> bool:
        return self.alto_caja_cm > 0 and self.ancho_caja_cm > 0 and self.largo_caja_cm > 0


def fila_a_linea(row) -> LineaPedido:
    if bool(row.get("ES_PICKING", False)) and not bool(row.get("SKU_SPEC_VALID", False)):
        raise InvalidSKUContractError(
            row.get("ARTICULO", "unknown"),
            {
                "code": "MISSING_OR_INVALID_CANONICAL_SPEC",
                "message": "picking line has no validated per-pick-unit dimensions and weight",
            },
        )
    return LineaPedido(
        descripcion          = str(row["DESCRIPCION_FINAL"]),
        articulo             = int(row["ARTICULO"]),
        grupo_art            = str(row["Grupo art."]) if pd.notna(row["Grupo art."]) else "OTRO",
        orden_apilado        = int(row["ORDEN_APILADO"]),
        cajas_linea          = float(row["CAJAS_LINEA"]),
        cajas_por_palet_real = float(row["CAJAS_POR_PALET_REAL"]),
        cajas_por_capa_real  = float(row["CAJAS_POR_CAPA_REAL"]),
        capas_por_palet_real = float(row["CAPAS_POR_PALET_REAL"]),
        es_palet_entero      = bool(row["ES_PALET_ENTERO"]),
        semipalet            = bool(row["SEMIPALET"]),
        cajas_por_palet_csv  = float(row["CAJAS_POR_PALET"]),
        es_picking           = bool(row["ES_PICKING"]),
        tipo_resto           = str(row["TIPO_RESTO"]),
        palets_completos     = float(row["PALETS_COMPLETOS"]),
        peso_palet_bruto     = float(row["BRUTO ZPA"]) if pd.notna(row["BRUTO ZPA"]) else 0.0,
        alergeno             = bool(row["ES_ALERGENO"]),
        alto_caja_cm         = float(pd.to_numeric(row.get("ALTO_CAJA_CM"), errors="coerce")),
        ancho_caja_cm        = float(pd.to_numeric(row.get("ANCHO_CAJA_CM"), errors="coerce")),
        largo_caja_cm        = float(pd.to_numeric(row.get("LARGO_CAJA_CM"), errors="coerce")),
        estabilidad          = str(row.get("Estabilidad", "") or ""),
        case_weight_kg       = float(row["CASE_WEIGHT_KG"]) if pd.notna(row.get("CASE_WEIGHT_KG")) else None,
        station_index        = int(row["STATION_INDEX"]) if pd.notna(row.get("STATION_INDEX")) else None,
        station_name         = str(row["STATION_NAME"]) if pd.notna(row.get("STATION_NAME")) else None,
        max_load_above_kg    = float(row["MAX_LOAD_ABOVE_KG"]) if pd.notna(row.get("MAX_LOAD_ABOVE_KG")) else None,
    )


@dataclass
class SubLinea:
    descripcion:          str
    cajas:                float
    alergeno:             bool
    cajas_por_palet_real: float
    peso_caja:            float
    cajas_por_capa:       float
    capas_por_palet:      float
    grupo_art:            str
    alto_caja_cm:         float = 0.0
    ancho_caja_cm:        float = 0.0
    largo_caja_cm:        float = 0.0
    estabilidad:          str   = ""
    orden_apilado:        int   = 99
    station_index:        int   = 0
    station_name:         str   = ""
    max_load_above_kg:    float | None = None
    articulo:             int | None = None

    @property
    def fraccion(self) -> float:
        return self.cajas / self.cajas_por_palet_real

    @property
    def tiene_dimensiones(self) -> bool:
        return self.alto_caja_cm > 0 and self.ancho_caja_cm > 0 and self.largo_caja_cm > 0


@dataclass
class CapaFisica:
    numero_capa:    int
    altura_cm:      float
    productos:      list[dict] = field(default_factory=list)
    ocupacion_x_cm: float = 0.0
    peso_kg:        float = 0.0

    @property
    def ocupacion_pct(self) -> float:
        area = sum(p["ancho_cm"] * p["largo_cm"] * p["cajas"] for p in self.productos)
        return area / (PALET_ANCHO_CM * PALET_LARGO_CM)

    @property
    def esta_llena(self) -> bool:
        return self.ocupacion_x_cm >= PALET_ANCHO_CM * CAPA_LLENA_PCT

    def agregar_producto(self, desc, grupo, cajas, ancho, largo, peso_caja):
        self.productos.append({
            "descripcion": desc, "grupo_art": grupo,
            "cajas": cajas, "x_cm": self.ocupacion_x_cm,
            "ancho_cm": ancho, "largo_cm": largo,
        })
        filas = max(int(PALET_LARGO_CM / largo), 1) if largo > 0 else 1
        self.ocupacion_x_cm += ancho * (cajas / filas)
        self.peso_kg        += cajas * peso_caja


@dataclass
class PaletConformado:
    numero:          int
    alergeno:        bool  = False
    lineas:          list[dict] = field(default_factory=list)
    ocupacion:       float = 0.0
    peso_total:      float = 0.0
    peso_tara_kg:    float = PALLET_TARE_WEIGHT_KG
    capas:           list[CapaFisica] = field(default_factory=list)
    altura_total_cm: float = PALLET_BASE_HEIGHT_CM
    modo_3d:         bool  = False
    heightmap:       list  = field(
        default_factory=lambda: [[PALLET_BASE_HEIGHT_CM] * GRID_L for _ in range(GRID_W)]
    )
    cajas_3d:        list  = field(default_factory=list)
    layer_patterns:  list[dict] = field(default_factory=list)
    pallet_open_log: list[str] = field(default_factory=list)

    @property
    def peso_bruto_total_kg(self) -> float:
        return self.peso_tara_kg + self.peso_total

    def agregar(self, descripcion, cajas, cajas_por_palet_real,
                peso_caja, cajas_por_capa, capas_por_palet, grupo_art):
        self.lineas.append({
            "descripcion": descripcion, "cajas": cajas,
            "cajas_por_capa": cajas_por_capa, "capas_por_palet": capas_por_palet,
            "cajas_por_palet_real": cajas_por_palet_real,
            "grupo_art": grupo_art, "peso_caja": peso_caja,
        })
        self.ocupacion  += cajas / cajas_por_palet_real
        self.peso_total += cajas * peso_caja

    @property
    def descripciones_str(self) -> str:
        unicas = list(dict.fromkeys(l["descripcion"] for l in self.lineas))
        return " + ".join(unicas)

    @property
    def total_cajas(self) -> float:
        return sum(l["cajas"] for l in self.lineas)

    @property
    def n_capas(self) -> int:
        return len(self.capas)


# ---------------------------------------------------------------------------
# SEPARACIÃ“N EN GRUPOS
# ---------------------------------------------------------------------------

def separar_grupos(lineas):
    grupo_a, grupo_b, grupo_c = [], [], []
    for l in lineas:
        if l.es_picking:      grupo_b.append(l)
        elif l.semipalet:     grupo_c.append(l)
        elif l.es_palet_entero: grupo_a.append(l)
    return grupo_a, grupo_b, grupo_c


# ---------------------------------------------------------------------------
# CONFORMACIÃ“N 3D â€” IDEA C: CAPAS HOMOGÃ‰NEAS POR FAMILIA
# ---------------------------------------------------------------------------

def _execute_planned_placement(
    palet: PaletConformado,
    sl: SubLinea,
    planned,
    altura_max: float,
    max_gross_weight_kg: float,
) -> None:
    """Execute and revalidate one exact planned placement."""
    candidate = {
        "x_cm": planned.x_cm, "y_cm": planned.y_cm, "z_cm": planned.z_cm,
        "ancho_cm": planned.width_cm, "largo_cm": planned.length_cm,
        "alto_cm": planned.height_cm,
    }
    if planned.z_cm + planned.height_cm > altura_max + EPS_CM:
        raise ValueError("planned layer exceeds the configured total pallet height")
    if placement_has_collision(candidate, palet.cajas_3d):
        raise ValueError("planned layer contains an exact cuboid collision")
    support = soporte_real_caja(
        palet.cajas_3d, planned.x_cm, planned.y_cm,
        planned.width_cm, planned.length_cm, planned.z_cm,
    )
    if not support.supported:
        raise ValueError(
            f"planned layer has insufficient exact support ({support.support_ratio:.3f})"
        )
    projected_gross = palet.peso_bruto_total_kg + sl.peso_caja
    if projected_gross > max_gross_weight_kg + EPS_CM:
        raise ValueError(
            f"planned layer exceeds mixed-pallet gross limit: "
            f"projected={projected_gross:.3f} kg, limit={max_gross_weight_kg:.3f} kg"
        )

    actualizar_heightmap(
        palet.heightmap, planned.x_cm, planned.y_cm,
        planned.width_cm, planned.length_cm, planned.height_cm, planned.z_cm,
    )
    palet.cajas_3d.append({
        **candidate,
        "descripcion": sl.descripcion, "articulo": sl.articulo, "grupo_art": sl.grupo_art,
        "peso_caja": sl.peso_caja, "rotada": planned.rotated,
        "station_index": sl.station_index, "station_name": sl.station_name,
        "max_load_above_kg": sl.max_load_above_kg,
        "layer_id": planned.layer_id,
    })
    palet.altura_total_cm = max(palet.altura_total_cm, planned.z_cm + planned.height_cm)
    linea_existente = next(
        (line for line in palet.lineas
         if line.get("descripcion") == sl.descripcion
         and line.get("grupo_art") == sl.grupo_art),
        None,
    )
    if linea_existente is None:
        palet.lineas.append({
            "descripcion": sl.descripcion, "cajas": 1.0,
            "cajas_por_capa": sl.cajas_por_capa,
            "capas_por_palet": sl.capas_por_palet,
            "cajas_por_palet_real": sl.cajas_por_palet_real,
            "grupo_art": sl.grupo_art, "peso_caja": sl.peso_caja,
            "alto_caja_cm": sl.alto_caja_cm,
            "ancho_caja_cm": sl.ancho_caja_cm,
            "largo_caja_cm": sl.largo_caja_cm,
        })
    else:
        linea_existente["cajas"] += 1.0
    palet.ocupacion += 1.0 / max(sl.cajas_por_palet_real, 1)
    palet.peso_total += sl.peso_caja


def _try_homogeneous_layer(palet, sl, cajas_restantes, altura_max, max_gross_weight_kg, max_base, layer_id):
    """Find a fully revalidatable exact layer, or return None."""
    if cajas_restantes < 2 or not sl.tiene_dimensiones:
        return None
    available_weight = max_gross_weight_kg - palet.peso_bruto_total_kg
    if sl.peso_caja <= 0:
        return None
    max_by_weight = int((available_weight + EPS_CM) / sl.peso_caja)
    max_cases = min(int(cajas_restantes), max_by_weight)
    if max_cases < 2:
        return None
    planes = {PALLET_BASE_HEIGHT_CM}
    planes.update(
        box["z_cm"] + box["alto_cm"] for box in palet.cajas_3d
    )
    for base_z in sorted(planes):
        if max_base is not None and base_z > max_base + EPS_CM:
            continue
        pattern = select_best_homogeneous_pattern(
            article=sl.descripcion, station_index=sl.station_index,
            width_cm=sl.ancho_caja_cm, length_cm=sl.largo_caja_cm,
            height_cm=sl.alto_caja_cm, z_cm=base_z, layer_id=layer_id,
            max_cases=max_cases, placed=palet.cajas_3d,
        )
        if pattern is None or len(pattern.placements) < 2:
            continue
        # The pattern generator checks footprint geometry; the caller owns the
        # configured total-height contract and must reject an over-tall plan
        # before execution rather than raising from the execution gate.
        if pattern.top_z_cm > altura_max + EPS_CM:
            continue
        trial_boxes = list(palet.cajas_3d)
        feasible = True
        for planned in pattern.placements:
            candidate = {
                "x_cm": planned.x_cm, "y_cm": planned.y_cm,
                "z_cm": planned.z_cm, "ancho_cm": planned.width_cm,
                "largo_cm": planned.length_cm, "alto_cm": planned.height_cm,
            }
            if placement_has_collision(candidate, trial_boxes):
                feasible = False
                break
            if not soporte_real_caja(
                trial_boxes, planned.x_cm, planned.y_cm,
                planned.width_cm, planned.length_cm, planned.z_cm,
            ).supported:
                feasible = False
                break
            trial_boxes.append(candidate)
        if feasible:
            return pattern
    return None

def colocar_familia(
    palet: PaletConformado,
    sublineas_familia: list,
    altura_max: float,
    max_gross_weight_kg: float = MAX_MIXED_PALLET_GROSS_WEIGHT_KG,
) -> list:
    """
    Coloca todas las cajas de una familia en el palet respetando el heightmap.
    Las cajas se colocan una a una buscando la posiciÃ³n mÃ¡s baja disponible.
    Devuelve las sublÃ­neas que NO pudieron colocarse (palet lleno).
    """
    restantes = []

    for sl in sublineas_familia:
        cajas_restantes = sl.cajas
        cajas_por_capa_obj = int(sl.cajas_por_capa) if sl.cajas_por_capa > 0 else 0
        sku_base  = None
        sku_count = 0
        layer_id = 1 + len({round(box["z_cm"], 6) for box in palet.cajas_3d})

        while cajas_restantes > 1e-9:
            projected_gross = palet.peso_bruto_total_kg + sl.peso_caja
            if projected_gross > max_gross_weight_kg + EPS_CM:
                if not palet.cajas_3d:
                    raise ValueError(
                        f"Case {sl.descripcion} exceeds mixed-pallet gross limit: "
                        f"projected={projected_gross:.3f} kg, "
                        f"limit={max_gross_weight_kg:.3f} kg"
                    )
                restantes.append(SubLinea(
                    descripcion=sl.descripcion, cajas=cajas_restantes,
                    alergeno=sl.alergeno,
                    cajas_por_palet_real=sl.cajas_por_palet_real,
                    peso_caja=sl.peso_caja,
                    cajas_por_capa=sl.cajas_por_capa,
                    capas_por_palet=sl.capas_por_palet,
                    grupo_art=sl.grupo_art,
                    alto_caja_cm=sl.alto_caja_cm,
                    ancho_caja_cm=sl.ancho_caja_cm,
                    largo_caja_cm=sl.largo_caja_cm,
                    estabilidad=sl.estabilidad,
                    orden_apilado=sl.orden_apilado,
                    station_index=sl.station_index,
                    station_name=sl.station_name,
                    max_load_above_kg=sl.max_load_above_kg,
                    articulo=sl.articulo,
                ))
                break

            planned_layer = _try_homogeneous_layer(
                palet, sl, cajas_restantes, altura_max, max_gross_weight_kg,
                None if sku_base is None else sku_base + TOLERANCIA_ALTO,
                layer_id,
            )
            if planned_layer is not None:
                for planned in planned_layer.placements:
                    _execute_planned_placement(
                        palet, sl, planned, altura_max, max_gross_weight_kg
                    )
                    cajas_restantes -= 1.0
                palet.layer_patterns.append({
                    "layer_id": planned_layer.placements[0].layer_id,
                    "covered_area_cm2": planned_layer.covered_area_cm2,
                    "utilization": planned_layer.utilization,
                    "top_z_cm": planned_layer.top_z_cm,
                    "case_count": len(planned_layer.placements),
                })
                layer_id += 1
                sku_base = None
                sku_count = 0
                continue

            # CohesiÃ³n de capa: intentar completar la capa del SKU actual
            max_base = None
            if cajas_por_capa_obj > 0 and sku_base is not None and sku_count < cajas_por_capa_obj:
                max_base = sku_base + TOLERANCIA_ALTO

            pos = buscar_posicion_optima(
                palet.heightmap,
                sl.ancho_caja_cm, sl.largo_caja_cm,
                sl.alto_caja_cm, altura_max,
                placed=palet.cajas_3d,
                max_base=max_base,
            )

            if pos is None and max_base is not None:
                # Liberar capa del SKU y buscar sin restricciÃ³n de altura
                sku_base  = None
                sku_count = 0
                pos = buscar_posicion_optima(
                    palet.heightmap,
                    sl.ancho_caja_cm, sl.largo_caja_cm,
                    sl.alto_caja_cm, altura_max,
                    placed=palet.cajas_3d,
                )

            if pos is None:
                # Palet lleno â€” guardar cajas restantes de este SKU y salir
                restantes.append(SubLinea(
                    descripcion=sl.descripcion, cajas=cajas_restantes,
                    alergeno=sl.alergeno,
                    cajas_por_palet_real=sl.cajas_por_palet_real,
                    peso_caja=sl.peso_caja,
                    cajas_por_capa=sl.cajas_por_capa,
                    capas_por_palet=sl.capas_por_palet,
                    grupo_art=sl.grupo_art,
                    alto_caja_cm=sl.alto_caja_cm,
                    ancho_caja_cm=sl.ancho_caja_cm,
                    largo_caja_cm=sl.largo_caja_cm,
                    estabilidad=sl.estabilidad,
                    orden_apilado=sl.orden_apilado,
                    station_index=sl.station_index,
                    station_name=sl.station_name,
                    articulo=sl.articulo,
                ))
                break

            x0, y0, h_base, ancho_usado, largo_usado = pos

            # Actualizar cohesiÃ³n de capa
            if cajas_por_capa_obj > 0:
                if sku_base is None:
                    sku_base  = h_base
                    sku_count = 0
                sku_count += 1
                if sku_count >= cajas_por_capa_obj:
                    sku_base  = None
                    sku_count = 0

            # Colocar la caja en el heightmap
            actualizar_heightmap(
                palet.heightmap, x0, y0,
                ancho_usado, largo_usado,
                sl.alto_caja_cm, h_base,
            )

            palet.cajas_3d.append({
                "x_cm": round(x0, 6), "y_cm": round(y0, 6), "z_cm": round(h_base, 6),
                "ancho_cm": ancho_usado, "largo_cm": largo_usado,
                "alto_cm": sl.alto_caja_cm,
                "descripcion": sl.descripcion, "articulo": sl.articulo, "grupo_art": sl.grupo_art,
                "peso_caja": sl.peso_caja,
                "rotada": ancho_usado != sl.ancho_caja_cm,
                "station_index": sl.station_index,
                "station_name": sl.station_name,
                "max_load_above_kg": sl.max_load_above_kg,
            })

            nueva_altura = h_base + sl.alto_caja_cm
            if nueva_altura > palet.altura_total_cm:
                palet.altura_total_cm = nueva_altura

            linea_existente = next(
                (l for l in palet.lineas
                 if l.get("descripcion") == sl.descripcion
                 and l.get("grupo_art") == sl.grupo_art),
                None,
            )
            if linea_existente is None:
                palet.lineas.append({
                    "descripcion": sl.descripcion, "cajas": 1.0,
                    "cajas_por_capa": sl.cajas_por_capa,
                    "capas_por_palet": sl.capas_por_palet,
                    "cajas_por_palet_real": sl.cajas_por_palet_real,
                    "grupo_art": sl.grupo_art, "peso_caja": sl.peso_caja,
                    "alto_caja_cm": sl.alto_caja_cm,
                    "ancho_caja_cm": sl.ancho_caja_cm,
                    "largo_caja_cm": sl.largo_caja_cm,
                })
            else:
                linea_existente["cajas"] += 1.0

            palet.ocupacion  += 1.0 / max(sl.cajas_por_palet_real, 1)
            palet.peso_total += sl.peso_caja
            cajas_restantes  -= 1.0

    return restantes


def conformar_palets_3d(
    sublineas,
    numero_inicio=1,
    alergeno=False,
    altura_max=MAX_TOTAL_PALLET_HEIGHT_CM,
    max_gross_weight_kg=MAX_MIXED_PALLET_GROSS_WEIGHT_KG,
    operational_policy="single_active",
):
    """
    Algoritmo Idea C â€” Capas homogÃ©neas por familia.

    Agrupa las sublÃ­neas por orden_apilado y coloca cada grupo completo
    antes de pasar al siguiente (latas â†’ PET â†’ VNR â†’ VR).
    Si el palet se llena a mitad de un grupo, se cierra y se abre uno
    nuevo continuando con las cajas que no cupieron.
    """
    if operational_policy not in {"single_active", "multiple_open"}:
        raise ValueError("operational_policy must be 'single_active' or 'multiple_open'")
    palets = []
    palet_actual = PaletConformado(
        numero=numero_inicio, alergeno=alergeno, modo_3d=True,
    )
    palet_actual.altura_total_cm = PALLET_BASE_HEIGHT_CM

    # Group by route station while preserving input order within each station.
    grupos: dict[int, list] = {}
    for sl in sublineas:
        station = getattr(sl, "station_index", None)
        if station is None:
            raise ValueError(f"SubLinea {sl.descripcion} has no station mapping")
        grupos.setdefault(station, []).append(sl)

    # Process stations in route order; later stations cannot be processed first.
    for station in sorted(grupos.keys()):
        cola = list(grupos[station])

        while cola:
            if operational_policy == "single_active":
                restantes = colocar_familia(
                    palet_actual, cola, altura_max, max_gross_weight_kg
                )
                if restantes:
                    if not palet_actual.cajas_3d:
                        raise ValueError(
                            "no feasible placement exists on an empty pallet for "
                            f"{restantes[0].descripcion}: geometry, support, height, "
                            "or weight constraint"
                        )
                    palets.append(palet_actual)
                    palet_actual = PaletConformado(
                        numero=len(palets) + numero_inicio,
                        alergeno=alergeno, modo_3d=True,
                    )
                    palet_actual.altura_total_cm = PALLET_BASE_HEIGHT_CM
                    palet_actual.pallet_open_log.append(
                        "opened: no feasible placement remained in single_active pallet"
                    )
                    cola = restantes
                else:
                    cola = []
                continue

            # Multiple-open policy: choose from feasible existing pallets first.
            sl = cola.pop(0)
            feasible = []
            for candidate_pallet in palets + [palet_actual]:
                if candidate_pallet.cajas_3d and candidate_pallet.peso_bruto_total_kg + sl.peso_caja > max_gross_weight_kg + EPS_CM:
                    continue
                if buscar_posicion_optima(
                    candidate_pallet.heightmap, sl.ancho_caja_cm,
                    sl.largo_caja_cm, sl.alto_caja_cm, altura_max,
                    placed=candidate_pallet.cajas_3d,
                ) is not None:
                    feasible.append(candidate_pallet)
            selected = choose_best_feasible_pallet(palets + [palet_actual], feasible)
            if selected is None:
                if not palet_actual.cajas_3d and palet_actual.peso_bruto_total_kg + sl.peso_caja > max_gross_weight_kg + EPS_CM:
                    raise ValueError(f"Case {sl.descripcion} exceeds mixed-pallet gross limit")
                if palet_actual.lineas:
                    palets.append(palet_actual)
                palet_actual = PaletConformado(
                    numero=len(palets) + numero_inicio,
                    alergeno=alergeno, modo_3d=True,
                )
                palet_actual.altura_total_cm = PALLET_BASE_HEIGHT_CM
                palet_actual.pallet_open_log.append(
                    "opened: all accessible pallets failed hard feasibility "
                    "(collision/support/height/weight)"
                )
                selected = palet_actual
            restantes = colocar_familia(selected, [sl], altura_max, max_gross_weight_kg)
            if restantes:
                cola = restantes + cola

    if palet_actual.lineas:
        palets.append(palet_actual)

    return [p for p in palets if p.lineas]


# ---------------------------------------------------------------------------
# CONFORMACIÃ“N FRACCIÃ“N â€” FALLBACK
# ---------------------------------------------------------------------------

def conformar_palets(sublineas, numero_inicio=1, alergeno=False, peso_max=float("inf")):
    palets = []
    palet_actual = PaletConformado(numero=numero_inicio, alergeno=alergeno)
    palets.append(palet_actual)
    cola = list(sublineas)

    while cola:
        sl = cola.pop(0)
        cajas_restantes = sl.cajas

        while cajas_restantes > 1e-9:
            hueco_vol  = 1.0 - palet_actual.ocupacion
            hueco_peso = peso_max - palet_actual.peso_total

            if hueco_vol < 1e-9:
                palet_actual = PaletConformado(numero=len(palets)+numero_inicio, alergeno=alergeno)
                palets.append(palet_actual)
                continue

            cajas_por_vol  = hueco_vol * sl.cajas_por_palet_real
            cajas_por_peso = (hueco_peso / sl.peso_caja) if sl.peso_caja > 0 else float("inf")
            cajas_caben    = min(cajas_por_vol, cajas_por_peso)

            if cajas_caben < 1e-9:
                palet_actual = PaletConformado(numero=len(palets)+numero_inicio, alergeno=alergeno)
                palets.append(palet_actual)
                continue

            if cajas_restantes <= cajas_caben + 1e-9:
                palet_actual.agregar(
                    sl.descripcion, cajas_restantes, sl.cajas_por_palet_real,
                    sl.peso_caja, sl.cajas_por_capa, sl.capas_por_palet, sl.grupo_art,
                )
                cajas_restantes = 0
            else:
                palet_actual.agregar(
                    sl.descripcion, cajas_caben, sl.cajas_por_palet_real,
                    sl.peso_caja, sl.cajas_por_capa, sl.capas_por_palet, sl.grupo_art,
                )
                cajas_restantes -= cajas_caben
                palet_actual = PaletConformado(numero=len(palets)+numero_inicio, alergeno=alergeno)
                palets.append(palet_actual)

    return palets


# ---------------------------------------------------------------------------
# PROCESADOR PRINCIPAL
# ---------------------------------------------------------------------------

def procesar_pedido(
    pedido_id,
    lineas,
    peso_max_palet=MAX_MIXED_PALLET_GROSS_WEIGHT_KG,
    usar_3d=True,
):
    res = procesar_pedido_dict(pedido_id, lineas, peso_max_palet, usar_3d)
    sep = "=" * 62
    out = [
        sep,
        f"PEDIDO            : {res['pedido_id']}",
        f"PALETS_COMPLETOS  : {res['palets_completos']}",
        f"SEMIPALET         : {res['n_semipalet']}",
        f"PALETS_PICKING    : {res['n_picking_equiv']:.4f}",
        f"TOTAL_PALETS      : {res['total_palets']:.4f}",
        f"PALET_INCOMPLETO  : {res['palet_incompleto']:.4f}",
        f"ALERTA_75         : {'SI' if res['alerta_75'] else 'NO'}",
        sep,
    ]

    if res["palets_picking"]:
        for p in res["palets_picking"]:
            al = " *** ALERTA <75%" if p["alerta"]   else ""
            ae = " [ALERGENO]"      if p["alergeno"] else ""
            out.append("")
            out.append(
                f"  > Palet P{p['numero']}{ae}  --  "
                f"{p['ocupacion']*100:.1f}% ocupacion  |  "
                f"{p['altura_total_cm']:.0f} cm altura total  |  "
                f"{p['altura_carga_cm']:.0f} cm carga sobre base  |  "
                f"{p['total_cajas']:.0f} cajas  |  "
                f"{p['n_capas']} capas fisicas{al}"
            )
            out.append("  " + "-" * 58)

            if p["capas"]:
                altura_acum = PALLET_BASE_HEIGHT_CM
                for c in p["capas"]:
                    altura_acum += c["altura_cm"]
                    out.append(
                        f"  Capa {c['numero_capa']:2d} | "
                        f"alto={c['altura_cm']:.0f}cm | "
                        f"ocup={c['ocupacion_pct']*100:.0f}% | "
                        f"peso={c['peso_kg']:.0f}kg | "
                        f"h_acum={altura_acum:.0f}cm"
                    )
                    for pr in c["productos"]:
                        out.append(
                            f"         +-- {pr['descripcion'][:42]:42s} "
                            f"{pr['cajas']:5.0f} cj  "
                            f"{pr['ancho_cm']:.0f}x{pr['largo_cm']:.0f}cm"
                        )
            else:
                for l in p["lineas"]:
                    frac = l["cajas"] / l["cajas_por_palet_real"] * 100
                    out.append(
                        f"         +-- {l['descripcion'][:42]:42s} "
                        f"{l['cajas']:5.0f} cj  {frac:.1f}%"
                    )

    out.append("")
    out.append(sep)
    return "\n".join(out)


def procesar_pedido_dict(
    pedido_id,
    lineas,
    peso_max_palet=MAX_MIXED_PALLET_GROSS_WEIGHT_KG,
    usar_3d=True,
    operational_policy="single_active",
):
    missing_route = [
        str(linea.articulo)
        for linea in lineas
        if linea.es_picking and linea.station_index is None
    ]
    if missing_route:
        raise StationRouteError([{
            "code": "MISSING_ROUTE_MAPPING",
            "message": f"picking articles have no station_index: {missing_route}",
        }])
    grupo_a, grupo_b, grupo_c = separar_grupos(lineas)
    n_completos = sum(int(l.palets_completos) for l in grupo_a)
    n_semipalet = len(grupo_c)

    picking_normal = sorted(
        [l for l in grupo_b if not l.alergeno],
        key=lambda l: l.station_index if l.station_index is not None else 0,
    )
    picking_alerg  = sorted(
        [l for l in grupo_b if l.alergeno],
        key=lambda l: l.station_index if l.station_index is not None else 0,
    )

    def a_sublineas(grupo):
        return [SubLinea(
            descripcion=l.descripcion, cajas=l.cajas_linea, alergeno=l.alergeno,
            cajas_por_palet_real=l.cajas_por_palet_real, peso_caja=l.peso_caja,
            cajas_por_capa=l.cajas_por_capa_real, capas_por_palet=l.capas_por_palet_real,
            grupo_art=l.grupo_art, alto_caja_cm=l.alto_caja_cm,
            ancho_caja_cm=l.ancho_caja_cm, largo_caja_cm=l.largo_caja_cm,
            estabilidad=l.estabilidad, orden_apilado=l.orden_apilado,
            station_index=l.station_index if l.station_index is not None else 0,
            station_name=l.station_name or "",
            max_load_above_kg=l.max_load_above_kg,
            articulo=l.articulo,
        ) for l in grupo]

    def usar_3d_grupo(grupo):
        return usar_3d and all(l.tiene_dimensiones for l in grupo) and len(grupo) > 0

    pn = []
    if picking_normal:
        subs = a_sublineas(picking_normal)
        pn = conformar_palets_3d(
            subs, 1, False, MAX_TOTAL_PALLET_HEIGHT_CM,
            max_gross_weight_kg=peso_max_palet,
            operational_policy=operational_policy,
        ) if usar_3d_grupo(picking_normal) \
             else conformar_palets(subs, 1, False, peso_max_palet)

    pa = []
    if picking_alerg:
        subs = a_sublineas(picking_alerg)
        pa = conformar_palets_3d(
            subs, len(pn)+1, True, MAX_TOTAL_PALLET_HEIGHT_CM,
            max_gross_weight_kg=peso_max_palet,
            operational_policy=operational_policy,
        ) if usar_3d_grupo(picking_alerg) \
             else conformar_palets(subs, len(pn)+1, True, peso_max_palet)

    todos = pn + pa

    # En modo 3D recalcular ocupaciÃ³n como altura_real / altura_max
    # para que sea consistente y nunca supere 1.0
    for p in todos:
        if p.modo_3d and p.altura_total_cm > 0:
            altura_carga = p.altura_total_cm - PALLET_BASE_HEIGHT_CM
            if altura_carga > 0:
                p.ocupacion = min(round(altura_carga / MAX_CARGO_HEIGHT_CM, 4), 1.0)

    n_picking    = sum(p.ocupacion for p in todos)
    total_palets = n_completos + n_semipalet + n_picking
    palet_inc    = todos[-1].ocupacion if todos and abs(todos[-1].ocupacion - 1.0) > 1e-9 else 0.0
    alerta_75    = any(p.ocupacion < 0.75 - 1e-9 for p in todos)

    return {
        "pedido_id":        pedido_id,
        "palets_completos": n_completos,
        "n_semipalet":      n_semipalet,
        "n_picking_fisico": len(todos),
        "n_picking_equiv":  round(n_picking, 4),
        "total_palets":     round(total_palets, 4),
        "palet_incompleto": round(palet_inc, 4),
        "alerta_75":        alerta_75,
        "palets_picking": [{
            "numero":          p.numero,
            "ocupacion":       round(p.ocupacion, 4),
            "peso_total":      round(p.peso_bruto_total_kg, 1),
            "peso_carga_total": round(p.peso_total, 1),
            "peso_tara_kg":    round(p.peso_tara_kg, 1),
            "peso_bruto_total_kg": round(p.peso_bruto_total_kg, 1),
            "alerta":          p.ocupacion < 0.75 - 1e-9,
            "alergeno":        p.alergeno,
            "altura_total_cm": round(p.altura_total_cm, 1),
            "altura_carga_cm": round(max(0.0, p.altura_total_cm - PALLET_BASE_HEIGHT_CM), 1),
            "n_capas":         p.n_capas,
            "descripciones_str": p.descripciones_str,
            "total_cajas":     p.total_cajas,
            "lineas":          p.lineas,
            "cajas_3d":        p.cajas_3d,
            "capas": [{
                "numero_capa":   c.numero_capa,
                "altura_cm":     c.altura_cm,
                "ocupacion_pct": round(c.ocupacion_pct, 4),
                "peso_kg":       round(c.peso_kg, 1),
                "productos":     c.productos,
            } for c in p.capas],
        } for p in todos],
    }


def _layout_rectangular_por_capas(
    pallet_id: str,
    numero_material: str,
    familia_detectada: str,
    peso_bruto: float,
    cajas_total: int,
    cajas_por_capa: int,
    capas_por_palet: int,
    ancho_caja_cm: float,
    largo_caja_cm: float,
    alto_caja_cm: float,
    x_offset: float = 0.0,
    y_offset: float = 0.0,
    z_base: float = PALLET_BASE_HEIGHT_CM,
):
    filas = []
    if cajas_total <= 0 or cajas_por_capa <= 0 or capas_por_palet <= 0:
        return filas

    cajas_restantes = cajas_total
    box_id = 1
    pallet_total_height = z_base + capas_por_palet * alto_caja_cm
    for layer_id in range(1, capas_por_palet + 1):
        if cajas_restantes <= 0:
            break
        cajas_en_capa = min(cajas_por_capa, cajas_restantes)
        for idx in range(cajas_en_capa):
            col = idx % max(int(PALET_ANCHO_CM // max(ancho_caja_cm, 1e-9)), 1)
            row = idx // max(int(PALET_ANCHO_CM // max(ancho_caja_cm, 1e-9)), 1)
            x_min = x_offset + col * ancho_caja_cm
            y_min = y_offset + row * largo_caja_cm
            z_min = z_base + (layer_id - 1) * alto_caja_cm
            filas.append({
                "Pallet_ID": pallet_id,
                "Layer_ID": layer_id,
                "Box_ID": f"BOX-{box_id:03d}",
                "x_min": round(x_min, 3),
                "y_min": round(y_min, 3),
                "z_min": round(z_min, 3),
                "x_max": round(x_min + ancho_caja_cm, 3),
                "y_max": round(y_min + largo_caja_cm, 3),
                "z_max": round(z_min + alto_caja_cm, 3),
                "NÃºmero de material": numero_material,
                "Familia_detectada": familia_detectada,
                "Peso_bruto": round(peso_bruto, 3),
                "Z_Reference": "PALLET_TOTAL_COORDINATES",
                "Pallet_Total_Height_cm": round(pallet_total_height, 3),
                "Pallet_Cargo_Height_cm": round(max(0.0, pallet_total_height - PALLET_BASE_HEIGHT_CM), 3),
                "Placement_Status": "PLACED",
                "Placement_Warning": "",
            })
            box_id += 1
        cajas_restantes -= cajas_en_capa
    return filas


def exportar_pedido_a_csv_visualizacion(
    pedido_id,
    lineas,
    resultado_dict,
    ruta_salida: str | Path,
) -> Path:
    """
    Exporta un CSV compatible con el visualizador.

    Ajustes:
    - X/Y intercambiados para coincidir con el sistema del visualizador.
    - Z bajado 14.4 cm para que la primera capa apoye sobre la tarima.
    - Familias normalizadas a las claves de color del visualizador.
    """
    ruta_salida = Path(ruta_salida)
    raise_if_invalid_order_geometry(
        resultado_dict.get("palets_picking", []),
        {
            "PALET_ANCHO_CM": PALET_ANCHO_CM,
            "PALET_LARGO_CM": PALET_LARGO_CM,
            "PALLET_BASE_HEIGHT_CM": PALLET_BASE_HEIGHT_CM,
            "MAX_TOTAL_PALLET_HEIGHT_CM": MAX_TOTAL_PALLET_HEIGHT_CM,
            "MIN_SUPPORT_RATIO": MIN_SUPPORT_RATIO,
            "MAX_MIXED_PALLET_GROSS_WEIGHT_KG": MAX_MIXED_PALLET_GROSS_WEIGHT_KG,
            "PALLET_TARE_WEIGHT_KG": PALLET_TARE_WEIGHT_KG,
            "MIN_SUPPORT_RATIO": MIN_SUPPORT_RATIO,
        },
    )
    assert_release_ready(
        resultado_dict,
        [line for line in lineas if getattr(line, "es_picking", True)],
        {
            "PALET_ANCHO_CM": PALET_ANCHO_CM,
            "PALET_LARGO_CM": PALET_LARGO_CM,
            "PALLET_BASE_HEIGHT_CM": PALLET_BASE_HEIGHT_CM,
            "MAX_TOTAL_PALLET_HEIGHT_CM": MAX_TOTAL_PALLET_HEIGHT_CM,
            "MIN_SUPPORT_RATIO": MIN_SUPPORT_RATIO,
            "MAX_MIXED_PALLET_GROSS_WEIGHT_KG": MAX_MIXED_PALLET_GROSS_WEIGHT_KG,
            "PALLET_TARE_WEIGHT_KG": PALLET_TARE_WEIGHT_KG,
        },
    )
    filas = []
    box_counter = 1

    familia_map = {
        "PA70": "LATAS_330", "PA71": "LATAS_330", "PA72": "LATAS_330", "PA74": "LATAS_330",
        "PA75": "LATAS_500", "PA65": "LATAS_250", "PA60": "LATAS_200", "PA62": "LATAS_200", "PA64": "LATAS_200",
        "PA01": "VR", "PA04": "VR", "PA06": "VR", "PA07": "VR_300", "PA08": "VR_350", "PA09": "VR",
        "PA11": "VR_237", "PA14": "VNR", "PA15": "VNR_200", "PA16": "VNR_200", "PA17": "VNR_200",
        "PA21": "VNR", "PA25": "VNR", "PA26": "VNR",
        "PA34": "PET_500", "PA35": "PET_500", "PA46": "PET_500", "PA56": "PET_500",
        "PA38": "PET_1250", "PA39": "PET_1000", "PA40": "PET_1000", "PA44": "PET_1000",
        "PA41": "PET_1500", "PA42": "PET_1500", "PA43": "PET_1500", "PA45": "PET_1500",
        "PA37": "PET_1750", "PA50": "PET_2000", "PA52": "PET_2000", "PA54": "PET_2000", "PA55": "PET_2000",
        "PA86": "BIB", "PA87": "BIB", "PA88": "BIB", "PA89": "BIB",
    }

    def mapear_familia(codigo: str) -> str:
        return familia_map.get(str(codigo).strip(), "UNKNOWN")

    def siguiente_box_id() -> str:
        nonlocal box_counter
        box_id = f"BOX-{box_counter:03d}"
        box_counter += 1
        return box_id

    def transformar_coords(x_min, y_min, z_min, x_max, y_max, z_max):
        return (
            x_min, y_min, z_min, x_max, y_max, z_max,
        )

    for pallet_idx, pallet in enumerate(resultado_dict.get("palets_picking", []), start=1):
        pallet_id = f"PALLET_EXPORT_{pallet_idx:02d}"
        capas_por_altura = {}
        alturas_ordenadas = sorted({round(box["z_cm"], 3) for box in pallet.get("cajas_3d", [])})
        for idx, altura in enumerate(alturas_ordenadas, start=1):
            capas_por_altura[altura] = idx

        for box in pallet.get("cajas_3d", []):
            layer_id = capas_por_altura.get(round(box["z_cm"], 3))
            x_min, y_min, z_min, x_max, y_max, z_max = transformar_coords(
                box["x_cm"],
                box["y_cm"],
                box["z_cm"],
                box["x_cm"] + box["ancho_cm"],
                box["y_cm"] + box["largo_cm"],
                box["z_cm"] + box["alto_cm"],
            )
            filas.append({
                "Pallet_ID": pallet_id,
                "Layer_ID": layer_id,
                "Box_ID": siguiente_box_id(),
                "x_min": round(x_min, 3),
                "y_min": round(y_min, 3),
                "z_min": round(z_min, 3),
                "x_max": round(x_max, 3),
                "y_max": round(y_max, 3),
                "z_max": round(z_max, 3),
                "NÃºmero de material": box.get("descripcion", ""),
                "Familia_detectada": mapear_familia(box.get("grupo_art", "")),
                "Peso_bruto": round(box.get("peso_caja", 0.0), 3),
                "Case_Weight_kg": round(box.get("peso_caja", 0.0), 3),
                "Pallet_Cargo_Weight_kg": round(pallet.get("peso_carga_total", 0.0), 1),
                "Pallet_Tare_Weight_kg": round(pallet.get("peso_tara_kg", PALLET_TARE_WEIGHT_KG), 1),
                "Pallet_Gross_Weight_kg": round(pallet.get("peso_bruto_total_kg", pallet.get("peso_total", 0.0)), 1),
                "Z_Reference": "PALLET_TOTAL_COORDINATES",
                "Pallet_Total_Height_cm": round(pallet.get("altura_total_cm", PALLET_BASE_HEIGHT_CM), 1),
                "Pallet_Cargo_Height_cm": round(pallet.get("altura_carga_cm", 0.0), 1),
                "Placement_Status": "PLACED",
                "Placement_Warning": None,
            })

    def add_layout_rows(linea, pallet_id, cajas, cajas_por_capa, capas_por_palet):
        for row in _layout_rectangular_por_capas(
            pallet_id=pallet_id,
            numero_material=linea.descripcion,
            familia_detectada=mapear_familia(linea.grupo_art),
            peso_bruto=linea.peso_caja,
            cajas_total=cajas,
            cajas_por_capa=cajas_por_capa,
            capas_por_palet=capas_por_palet,
            ancho_caja_cm=linea.ancho_caja_cm,
            largo_caja_cm=linea.largo_caja_cm,
            alto_caja_cm=linea.alto_caja_cm,
        ):
            row["Box_ID"] = siguiente_box_id()
            row["x_min"], row["y_min"], row["z_min"], row["x_max"], row["y_max"], row["z_max"] = transformar_coords(
                row["x_min"], row["y_min"], row["z_min"], row["x_max"], row["y_max"], row["z_max"]
            )
            filas.append(row)

    for linea in lineas:
        if not getattr(linea, "tiene_dimensiones", False):
            continue

        if getattr(linea, "palets_completos", 0) > 0:
            for _ in range(int(linea.palets_completos)):
                pallet_id = f"PALLET_EXPORT_{len(set(r['Pallet_ID'] for r in filas)) + 1:02d}"
                cajas = int(round(linea.cajas_por_capa_real * linea.capas_por_palet_real))
                add_layout_rows(
                    linea,
                    pallet_id,
                    cajas,
                    int(round(linea.cajas_por_capa_real)),
                    int(round(linea.capas_por_palet_real)),
                )

        if getattr(linea, "semipalet", False):
            pallet_id = f"PALLET_EXPORT_{len(set(r['Pallet_ID'] for r in filas)) + 1:02d}"
            cajas = int(round(linea.cajas_linea))
            capas = max(1, int(round(min(linea.capas_por_palet_real, max(cajas / max(linea.cajas_por_capa_real, 1), 1)))))
            add_layout_rows(
                linea,
                pallet_id,
                cajas,
                max(1, int(round(linea.cajas_por_capa_real))),
                capas,
            )

    columnas = [
        "Pallet_ID", "Layer_ID", "Box_ID", "x_min", "y_min", "z_min",
        "x_max", "y_max", "z_max", "NÃºmero de material", "Familia_detectada",
        "Peso_bruto", "Case_Weight_kg", "Pallet_Cargo_Weight_kg",
        "Pallet_Tare_Weight_kg", "Pallet_Gross_Weight_kg", "Z_Reference", "Pallet_Total_Height_cm",
        "Pallet_Cargo_Height_cm", "Placement_Status", "Placement_Warning",
    ]

    import tempfile

    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", newline="", encoding="utf-8-sig", dir=ruta_salida.parent,
            prefix=f".{ruta_salida.name}.", suffix=".tmp", delete=False,
        ) as fh:
            temporary_path = Path(fh.name)
            writer = csv.DictWriter(fh, fieldnames=columnas)
            writer.writeheader()
            writer.writerows(filas)
            fh.flush()

        temporary_path.replace(ruta_salida)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()

    return ruta_salida











