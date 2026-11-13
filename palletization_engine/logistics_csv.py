"""Strict ingestion for the logistics line CSV."""

from dataclasses import dataclass
import csv
import logging
from pathlib import Path

import pandas as pd


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class LogisticsReadMetrics:
    physical_records_read: int
    repaired_wrapped_records: int
    records_rejected: int
    final_dataframe_rows: int
    unique_numeric_orders: int


class MalformedLogisticsCSVError(ValueError):
    """Raised when one or more logistics records cannot match the header."""

    def __init__(self, path, header_count, rejected_lines, metrics):
        self.path = Path(path)
        self.header_count = header_count
        self.rejected_lines = tuple(rejected_lines)
        self.metrics = metrics
        details = "; ".join(
            f"line {line}: {reason}" for line, reason in self.rejected_lines[:10]
        )
        if len(self.rejected_lines) > 10:
            details += f"; ... ({len(self.rejected_lines)} rejected records)"
        super().__init__(
            f"Malformed logistics CSV {self.path}: expected {header_count} fields; "
            f"{details}"
        )


_NUMERIC_COLUMNS = (
    "PEDIDO", "MES_PEDIDO", "ARTICULO", "CAJAS_LINEA", "CAJAS_POR_CAPA",
    "CAPAS_POR_PALET", "CAJAS_POR_PALET", "PALETS_COMPLETOS", "CAJAS_RESTANTES",
    "CAPAS_COMPLETAS_RESTANTE", "CAJAS_EN_ULTIMA_CAPA_RESTANTE", "PESO_PALET_BRUTO",
)
_BOOLEAN_COLUMNS = ("ES_PALET_ENTERO", "SEMIPALET", "ES_PICKING")


def _dataframe_from_rows(header, rows):
    frame = pd.DataFrame(rows, columns=header)
    for column in _NUMERIC_COLUMNS:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in _BOOLEAN_COLUMNS:
        if column in frame.columns:
            frame[column] = frame[column].map({"True": True, "False": False})
    return frame


def read_logistics_csv(path, return_metrics=False):
    """Read and repair wrapped records, failing on any unrecoverable record.

    Metrics are always stored in ``DataFrame.attrs['ingestion_metrics']``. Set
    ``return_metrics=True`` to receive ``(dataframe, metrics)`` explicitly.
    """
    path = Path(path)
    rows = []
    rejected = []
    repaired = 0
    physical_records = 0

    with path.open("r", newline="", encoding="utf-8-sig") as stream:
        reader = csv.reader(stream, strict=True)
        try:
            header = next(reader)
        except StopIteration:
            raise MalformedLogisticsCSVError(
                path, 0, ((1, "missing header"),),
                LogisticsReadMetrics(0, 0, 1, 0, 0),
            )

        if not header or any(not name for name in header):
            raise MalformedLogisticsCSVError(
                path, len(header), ((1, "empty header name"),),
                LogisticsReadMetrics(0, 0, 1, 0, 0),
            )

        for row in reader:
            physical_records += 1
            line_number = reader.line_num
            if len(row) == 1 and "," in row[0]:
                try:
                    repaired_row = next(csv.reader([row[0]], strict=True))
                except (csv.Error, StopIteration) as exc:
                    rejected.append((line_number, f"second parse failed: {exc}"))
                    continue
                if len(repaired_row) == len(header):
                    row = repaired_row
                    repaired += 1

            if len(row) != len(header):
                rejected.append((
                    line_number,
                    f"found {len(row)} fields",
                ))
                continue
            rows.append(row)

    if rejected:
        metrics = LogisticsReadMetrics(
            physical_records, repaired, len(rejected), len(rows), 0,
        )
        raise MalformedLogisticsCSVError(path, len(header), rejected, metrics)

    frame = _dataframe_from_rows(header, rows)
    unique_orders = pd.to_numeric(frame["PEDIDO"], errors="coerce").nunique()
    metrics = LogisticsReadMetrics(
        physical_records, repaired, 0, len(frame), int(unique_orders),
    )
    frame.attrs["ingestion_metrics"] = metrics
    LOGGER.info(
        "Logistics CSV reconciliation: physical_records=%d repaired=%d "
        "rejected=%d dataframe_rows=%d unique_numeric_orders=%d",
        metrics.physical_records_read,
        metrics.repaired_wrapped_records,
        metrics.records_rejected,
        metrics.final_dataframe_rows,
        metrics.unique_numeric_orders,
    )
    if return_metrics:
        return frame, metrics
    return frame
