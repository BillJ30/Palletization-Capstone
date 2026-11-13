"""
Reusable order runner for CLI and UI usage.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from palet_conformador import (
    cargar_datos,
    exportar_pedido_a_csv_visualizacion,
    fila_a_linea,
    InvalidSKUContractError,
    procesar_pedido,
    procesar_pedido_dict,
)
from weight_config import MAX_MIXED_PALLET_GROSS_WEIGHT_KG


class ManualOrderValidationError(ValueError):
    """All invalid materials found while parsing one manual order."""

    def __init__(self, invalid_materials):
        self.invalid_materials = tuple(sorted(invalid_materials, key=lambda item: item["article"]))
        details = "; ".join(
            f"{item['article']}: {item['reason']}" for item in self.invalid_materials
        )
        super().__init__(f"Invalid manual materials: {details}")


def cargar_base_datos():
    df = cargar_datos(
        csv_path="inputs/dataset_logistico_lineas.csv",
        dim_path="inputs/Packaging_Logistics_Data.csv",
    )
    peso_max = MAX_MIXED_PALLET_GROSS_WEIGHT_KG
    return df, peso_max


def _resolver_material_lookup(df):
    if "ARTICULO" not in df.columns:
        raise ValueError("Expected ARTICULO column in base dataframe.")
    lookup = df.sort_values(by=["ARTICULO"]).drop_duplicates(subset=["ARTICULO"], keep="first").copy()
    lookup["ARTICULO"] = pd.to_numeric(lookup["ARTICULO"], errors="coerce").astype("Int64")
    return lookup.set_index("ARTICULO", drop=False)


def construir_pedido_manual(texto_pedido: str, df=None, skip_invalid_materials=None):
    if df is None:
        df, _ = cargar_base_datos()
    lookup = _resolver_material_lookup(df)

    lineas = []
    invalid_materials = []
    skip_invalid_materials = {int(article) for article in (skip_invalid_materials or ())}
    for raw_line in texto_pedido.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "," in line:
            parts = [p.strip() for p in line.split(",")]
        elif ";" in line:
            parts = [p.strip() for p in line.split(";")]
        else:
            parts = line.split()
        if len(parts) < 2:
            raise ValueError(f"Invalid line: {raw_line!r}. Use 'material, cases'.")

        articulo = int(float(parts[0]))
        cajas = float(parts[1])
        if articulo not in lookup.index:
            invalid_materials.append({
                "article": articulo,
                "reason": "not found in the loaded product master",
            })
            continue

        row = lookup.loc[articulo]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]
        if not bool(row.get("SKU_SPEC_VALID", False)):
            invalid_materials.append({
                "article": articulo,
                "reason": "missing or incompatible validated physical SKU specification",
            })
            continue

        manual = {
            "DESCRIPCION_FINAL": row.get("DESCRIPCION_FINAL", row.get("Número de material", str(articulo))),
            "ARTICULO": articulo,
            "CASE_WEIGHT_KG": row.get("CASE_WEIGHT_KG"),
            "STATION_INDEX": row.get("STATION_INDEX"),
            "STATION_NAME": row.get("STATION_NAME", ""),
            "Grupo art.": row.get("Grupo art.", "OTRO"),
            "ORDEN_APILADO": row.get("ORDEN_APILADO", 99),
            "CAJAS_LINEA": cajas,
            "CAJAS_POR_PALET_REAL": row.get("CAJAS_POR_PALET_REAL", row.get("CAJAS_POR_PALET", 1)),
            "CAJAS_POR_CAPA_REAL": row.get("CAJAS_POR_CAPA_REAL", row.get("Cajas/Capa", 1)),
            "CAPAS_POR_PALET_REAL": row.get("CAPAS_POR_PALET_REAL", row.get("Capas/Palet", 1)),
            "ES_PALET_ENTERO": False,
            "SEMIPALET": False,
            "CAJAS_POR_PALET": row.get("CAJAS_POR_PALET", row.get("CAJAS_POR_PALET_REAL", 1)),
            "ES_PICKING": True,
            "TIPO_RESTO": "MANUAL",
            "PALETS_COMPLETOS": 0,
            "BRUTO ZPA": row.get("BRUTO ZPA", row.get("Peso bruto", 0.0)),
            "ES_ALERGENO": bool(row.get("ES_ALERGENO", False)),
            "ALTO_CAJA_CM": row.get("ALTO_CAJA_CM", row.get("Altura_cm", 0.0)),
            "ANCHO_CAJA_CM": row.get("ANCHO_CAJA_CM", row.get("Ancho_cm", 0.0)),
            "LARGO_CAJA_CM": row.get("LARGO_CAJA_CM", row.get("Longitud_cm", 0.0)),
            "Estabilidad": row.get("Estabilidad", ""),
        }
        lineas.append(manual)

    if invalid_materials:
        unique_invalid = {item["article"]: item for item in invalid_materials}
        unresolved = [item for article, item in unique_invalid.items()
                      if article not in skip_invalid_materials]
        if unresolved:
            raise ManualOrderValidationError(unresolved)
    return lineas


def resolver_pedido(pedido_id, df=None, peso_max: float | None = None, usar_3d: bool = True):
    pedido_id = str(pedido_id).strip()
    if df is None or peso_max is None:
        df, peso_max = cargar_base_datos()

    df_ped = df[df["PEDIDO"].astype(str) == pedido_id]
    if df_ped.empty:
        return None, None, peso_max

    lineas = [fila_a_linea(row) for _, row in df_ped.iterrows()]
    resultado = procesar_pedido_dict(pedido_id, lineas, peso_max, usar_3d=usar_3d)
    texto = procesar_pedido(pedido_id, lineas, peso_max, usar_3d=usar_3d)
    return resultado, texto, peso_max


def exportar_pedido(pedido_id, resultado, lineas, output_path: str | Path | None = None):
    pedido_id = str(pedido_id).strip()
    if output_path is None:
        output_path = Path(f"outputs_visualizacion_{pedido_id}.csv")
    return exportar_pedido_a_csv_visualizacion(
        pedido_id=pedido_id,
        lineas=lineas,
        resultado_dict=resultado,
        ruta_salida=output_path,
    )


def obtener_lineas_pedido(df, pedido_id):
    pedido_id = str(pedido_id).strip()
    df_ped = df[df["PEDIDO"].astype(str) == pedido_id]
    if df_ped.empty:
        return []
    return [fila_a_linea(row) for _, row in df_ped.iterrows()]


def resolver_pedido_manual(
    texto_pedido, df=None, peso_max: float | None = None,
    usar_3d: bool = True, skip_invalid_materials=None,
):
    if df is None or peso_max is None:
        df, peso_max = cargar_base_datos()
    lineas_dict = construir_pedido_manual(
        texto_pedido, df=df, skip_invalid_materials=skip_invalid_materials
    )
    if not lineas_dict:
        return None, None, peso_max, []

    from palet_conformador import LineaPedido

    lineas = [LineaPedido(
        descripcion=str(x["DESCRIPCION_FINAL"]),
        articulo=int(x["ARTICULO"]),
        grupo_art=str(x["Grupo art."]),
        orden_apilado=int(x["ORDEN_APILADO"]),
        cajas_linea=float(x["CAJAS_LINEA"]),
        cajas_por_palet_real=float(x["CAJAS_POR_PALET_REAL"]),
        cajas_por_capa_real=float(x["CAJAS_POR_CAPA_REAL"]),
        capas_por_palet_real=float(x["CAPAS_POR_PALET_REAL"]),
        es_palet_entero=bool(x["ES_PALET_ENTERO"]),
        semipalet=bool(x["SEMIPALET"]),
        cajas_por_palet_csv=float(x["CAJAS_POR_PALET"]),
        es_picking=bool(x["ES_PICKING"]),
        tipo_resto=str(x["TIPO_RESTO"]),
        palets_completos=float(x["PALETS_COMPLETOS"]),
        peso_palet_bruto=float(x["BRUTO ZPA"]),
        alergeno=bool(x["ES_ALERGENO"]),
        alto_caja_cm=float(x["ALTO_CAJA_CM"]),
        ancho_caja_cm=float(x["ANCHO_CAJA_CM"]),
        largo_caja_cm=float(x["LARGO_CAJA_CM"]),
        estabilidad=str(x["Estabilidad"]),
        case_weight_kg=float(x["CASE_WEIGHT_KG"]),
        station_index=int(x["STATION_INDEX"]),
        station_name=str(x["STATION_NAME"]),
    ) for x in lineas_dict]

    resultado = procesar_pedido_dict("MANUAL", lineas, peso_max, usar_3d=usar_3d)
    texto = procesar_pedido("MANUAL", lineas, peso_max, usar_3d=usar_3d)
    return resultado, texto, peso_max, lineas


def main():
    df, peso_max = cargar_base_datos()
    print(f"Peso maximo palet: {peso_max:.1f} kg")
    print()

    pedido_prueba = 8656033953
    pedido_id = str(pedido_prueba)
    print(f"Probando pedido: {pedido_id}")
    print("=" * 60)

    resultado, texto, _ = resolver_pedido(pedido_id, df=df, peso_max=peso_max, usar_3d=True)
    if resultado is None:
        print(f"Pedido {pedido_id} no encontrado.")
        return

    print(texto)
    lineas = obtener_lineas_pedido(df, pedido_id)
    salida = exportar_pedido(pedido_id, resultado, lineas)
    print(f"CSV exportado en: {salida}")


if __name__ == "__main__":
    main()
