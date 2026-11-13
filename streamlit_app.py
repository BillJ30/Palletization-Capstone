"""
Coca-Cola Mixed-Pallet Builder: web front end for the ICSO capstone engine.

Runs the palletisation engine in `palletization_engine/` on a real order
(or a hand-built one) and shows the plan, the KPIs and an interactive 3D
view of every mixed pallet. The engine code itself is unchanged; this file
only replaces the old Tkinter desktop window (order_ui.py).
"""

from __future__ import annotations

import gzip
import os
import random
import shutil
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent
ENGINE_DIR = ROOT / "palletization_engine"
DATASET = ENGINE_DIR / "inputs" / "dataset_logistico_lineas.csv"
DATASET_GZ = ENGINE_DIR / "inputs" / "dataset_logistico_lineas.csv.gz"
DEMO_ORDERS = ROOT / "app_data" / "demo_orders.csv"
FAST_ORDERS = ROOT / "app_data" / "fast_orders.csv"

# The engine reads its inputs with paths relative to its own folder.
sys.path.insert(0, str(ENGINE_DIR))
os.chdir(ENGINE_DIR)

PALLET_X, PALLET_Y, PALLET_BASE, PALLET_MAX = 120.0, 80.0, 14.4, 180.0

PALETTE = [
    "#E4572E", "#17BEBB", "#FFC914", "#2E86AB", "#76B041", "#9B5DE5",
    "#F15BB5", "#00BBF9", "#FB8B24", "#5F0F40", "#3A86FF", "#8AC926",
    "#FF595E", "#6A4C93", "#1982C4", "#C1666B",
]

st.set_page_config(
    page_title="Mixed-Pallet Builder | ICSO x Coca-Cola Capstone",
    page_icon="📦",
    layout="wide",
)


# ---------------------------------------------------------------- data ----
def _ensure_dataset() -> None:
    """The 95 MB order file is stored gzipped in the repo; unpack it once."""
    if DATASET.exists():
        return
    with gzip.open(DATASET_GZ, "rb") as src, open(DATASET, "wb") as dst:
        shutil.copyfileobj(src, dst)


@st.cache_resource(show_spinner="Loading 568k order lines and the SKU master (first visit only)...")
def load_engine():
    _ensure_dataset()
    from run_csv import cargar_base_datos

    df, peso_max = cargar_base_datos()

    picking = df[df["ES_PICKING"] == True]  # noqa: E712
    orders = (
        picking.groupby("PEDIDO")
        .agg(
            covered=("SKU_SPEC_VALID", "all"),
            products=("ARTICULO", "nunique"),
            picking_cases=("CAJAS_LINEA", "sum"),
            customer=("CLIENTE_HIST", "first"),
            date=("FECHA_PEDIDO", "first"),
        )
        .reset_index()
    )
    orders["PEDIDO"] = orders["PEDIDO"].astype(str)
    orders["customer"] = orders["customer"].map(_fix_text)
    runnable = orders[orders["covered"]].drop(columns="covered")

    skus = (
        df[df["SKU_SPEC_VALID"] == True]  # noqa: E712
        .drop_duplicates("ARTICULO")[["ARTICULO", "DESCRIPCION_FINAL", "ALTO_CAJA_CM",
                                      "ANCHO_CAJA_CM", "LARGO_CAJA_CM", "CASE_WEIGHT_KG",
                                      "STATION_NAME"]]
        .sort_values("DESCRIPCION_FINAL")
    )
    skus["label"] = skus["ARTICULO"].astype(int).astype(str) + "  |  " + skus["DESCRIPCION_FINAL"].astype(str)
    stats = {
        "lines": len(df),
        "orders": df["PEDIDO"].nunique(),
        "picking_orders": len(orders),
        "runnable_orders": len(runnable),
        "valid_skus": len(skus),
    }
    return df, peso_max, runnable, skus, stats


def _fix_text(value) -> str:
    """Some customer names were saved with a double encoding (e.g. 'INVERSIÃ“N')."""
    text = str(value)
    try:
        return text.encode("latin-1").decode("utf-8").replace("\xa0", " ").strip()
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text.replace("\xa0", " ").strip()


@st.cache_data
def load_fast_orders() -> list[str]:
    """Orders pre-timed to finish in a few seconds with 2+ mixed pallets."""
    if FAST_ORDERS.exists():
        return pd.read_csv(FAST_ORDERS, dtype={"order": str})["order"].tolist()
    return load_demo_orders()["order"].tolist()


@st.cache_data
def load_demo_orders() -> pd.DataFrame:
    if DEMO_ORDERS.exists():
        return pd.read_csv(DEMO_ORDERS, dtype={"order": str})
    return pd.DataFrame(columns=["order", "label"])


# ------------------------------------------------------------- engine ----
def run_existing(order_id: str):
    from run_csv import obtener_lineas_pedido, resolver_pedido

    df, peso_max, *_ = load_engine()
    result, text, _ = resolver_pedido(order_id, df=df, peso_max=peso_max, usar_3d=True)
    if result is None:
        return None
    lines = obtener_lineas_pedido(df, order_id)
    return {"label": order_id, "result": result, "text": text, "lines": lines}


def run_manual(rows: list[tuple[int, float]]):
    from run_csv import resolver_pedido_manual

    df, peso_max, *_ = load_engine()
    text_order = "\n".join(f"{sku},{cases}" for sku, cases in rows)
    result, text, _, lines = resolver_pedido_manual(text_order, df=df, peso_max=peso_max, usar_3d=True)
    if result is None:
        return None
    return {"label": "MANUAL", "result": result, "text": text, "lines": lines}


def export_csv_bytes(run) -> bytes | None:
    from run_csv import exportar_pedido

    try:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / f"outputs_visualizacion_{run['label']}.csv"
            exportar_pedido(run["label"], run["result"], run["lines"], output_path=path)
            return path.read_bytes()
    except Exception:
        return None


def dashboard_html(run) -> str:
    from solution_dashboard import render_solution_dashboard

    return render_solution_dashboard(run["result"], run["label"])


# ----------------------------------------------------------------- 3D ----
def _box_mesh(x0, y0, z0, dx, dy, dz):
    xs = [x0, x0 + dx, x0 + dx, x0, x0, x0 + dx, x0 + dx, x0]
    ys = [y0, y0, y0 + dy, y0 + dy, y0, y0, y0 + dy, y0 + dy]
    zs = [z0, z0, z0, z0, z0 + dz, z0 + dz, z0 + dz, z0 + dz]
    i = [0, 0, 4, 4, 0, 0, 3, 3, 0, 0, 1, 1]
    j = [1, 2, 5, 6, 1, 5, 2, 6, 3, 7, 2, 6]
    k = [2, 3, 6, 7, 5, 4, 6, 7, 7, 4, 6, 5]
    return xs, ys, zs, i, j, k


def _box_edges(x0, y0, z0, dx, dy, dz):
    x1, y1, z1 = x0 + dx, y0 + dy, z0 + dz
    pts = [
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1), (x0, y0, z1), None,
        (x1, y0, z0), (x1, y0, z1), None, (x1, y1, z0), (x1, y1, z1), None,
        (x0, y1, z0), (x0, y1, z1), None,
    ]
    ex, ey, ez = [], [], []
    for p in pts:
        if p is None:
            ex.append(None); ey.append(None); ez.append(None)
        else:
            ex.append(p[0]); ey.append(p[1]); ez.append(p[2])
    return ex, ey, ez


def pallet_figure(boxes: list[dict], colours: dict[str, str], max_layer: int | None = None) -> go.Figure:
    fig = go.Figure()

    # Wooden pallet base
    bx, by, bz, i, j, k = _box_mesh(0, 0, 0, PALLET_X, PALLET_Y, PALLET_BASE)
    fig.add_trace(go.Mesh3d(x=bx, y=by, z=bz, i=i, j=j, k=k, color="#9C6B3F",
                            opacity=1, name="Wooden pallet", hoverinfo="name", flatshading=True))

    shown = [b for b in boxes if max_layer is None or int(b.get("layer_id", 1)) <= max_layer]
    by_product: dict[str, list[dict]] = {}
    for b in shown:
        by_product.setdefault(str(b.get("descripcion", "Unknown")), []).append(b)

    edge_x, edge_y, edge_z = [], [], []
    for product, items in by_product.items():
        X, Y, Z, I, J, K, hover = [], [], [], [], [], [], []
        for b in items:
            x0, y0, z0 = float(b["x_cm"]), float(b["y_cm"]), float(b["z_cm"])
            dx, dy, dz = float(b["ancho_cm"]), float(b["largo_cm"]), float(b["alto_cm"])
            xs, ys, zs, i, j, k = _box_mesh(x0, y0, z0, dx, dy, dz)
            off = len(X)
            X += xs; Y += ys; Z += zs
            I += [v + off for v in i]; J += [v + off for v in j]; K += [v + off for v in k]
            tip = (f"<b>{product}</b><br>SKU {b.get('articulo', '')} | layer {b.get('layer_id', '')}"
                   f"<br>{dx:.1f} x {dy:.1f} x {dz:.1f} cm, {float(b.get('peso_caja', 0)):.1f} kg"
                   f"<br>origin ({x0:.1f}, {y0:.1f}, {z0:.1f})"
                   f"{'<br>rotated 90°' if b.get('rotada') else ''}")
            hover += [tip] * 8
            ex, ey, ez = _box_edges(x0, y0, z0, dx, dy, dz)
            edge_x += ex; edge_y += ey; edge_z += ez
        fig.add_trace(go.Mesh3d(
            x=X, y=Y, z=Z, i=I, j=J, k=K, color=colours.get(product, "#888"), opacity=1,
            flatshading=True, name=f"{product} ({len(items)})", showlegend=True,
            hovertext=hover, hoverinfo="text",
            lighting=dict(ambient=0.55, diffuse=0.8, specular=0.1),
        ))

    fig.add_trace(go.Scatter3d(x=edge_x, y=edge_y, z=edge_z, mode="lines",
                               line=dict(color="rgba(20,20,20,0.55)", width=2),
                               hoverinfo="skip", showlegend=False))

    # Height limit frame at 180 cm
    hx = [0, PALLET_X, PALLET_X, 0, 0]
    hy = [0, 0, PALLET_Y, PALLET_Y, 0]
    fig.add_trace(go.Scatter3d(x=hx, y=hy, z=[PALLET_MAX] * 5, mode="lines",
                               line=dict(color="#D62828", width=3, dash="dash"),
                               name="180 cm height limit", hoverinfo="name"))

    fig.update_layout(
        height=640,
        margin=dict(l=0, r=0, t=10, b=0),
        legend=dict(orientation="h", yanchor="top", y=-0.02, x=0, font=dict(size=11)),
        scene=dict(
            xaxis=dict(title="x (cm)", range=[-5, PALLET_X + 5]),
            yaxis=dict(title="y (cm)", range=[-5, PALLET_Y + 5]),
            zaxis=dict(title="z (cm)", range=[0, PALLET_MAX + 5]),
            aspectmode="manual",
            aspectratio=dict(x=1.0, y=0.67, z=1.5),
            camera=dict(eye=dict(x=1.55, y=-1.75, z=0.75), center=dict(x=0, y=0, z=-0.05)),
        ),
    )
    return fig


def layer_table(boxes: list[dict]) -> pd.DataFrame:
    if not boxes:
        return pd.DataFrame()
    d = pd.DataFrame(boxes)
    d["top"] = d["z_cm"] + d["alto_cm"]
    d["footprint"] = d["ancho_cm"] * d["largo_cm"]
    out = (
        d.groupby("layer_id")
        .agg(cases=("descripcion", "size"),
             products=("descripcion", lambda s: ", ".join(sorted(set(map(str, s))))),
             base_z=("z_cm", "min"), top_z=("top", "max"),
             area=("footprint", "sum"), weight=("peso_caja", "sum"))
        .reset_index()
    )
    out["Footprint used"] = (out["area"] / (PALLET_X * PALLET_Y) * 100).clip(upper=100).round(1).astype(str) + "%"
    out = out.rename(columns={"layer_id": "Layer", "cases": "Cases", "products": "Products",
                              "base_z": "Base z (cm)", "top_z": "Top z (cm)", "weight": "Weight (kg)"})
    out["Base z (cm)"] = out["Base z (cm)"].round(1)
    out["Top z (cm)"] = out["Top z (cm)"].round(1)
    out["Weight (kg)"] = out["Weight (kg)"].round(1)
    return out[["Layer", "Cases", "Footprint used", "Base z (cm)", "Top z (cm)", "Weight (kg)", "Products"]]


# ----------------------------------------------------------------- UI ----
def header(stats):
    st.title("📦 Mixed-Pallet Builder")
    st.markdown(
        "MSc Business Analytics capstone (UCD Smurfit x ICSO Analytics) for a Coca-Cola bottler's "
        "warehouse. Pick a real customer order and the engine decides how the mixed (picking) cases "
        "are stacked onto 120 x 80 cm pallets, then checks every case for overlap, support, the "
        "180 cm height limit, the 1,000 kg weight limit and warehouse station order."
    )
    c = st.columns(4)
    c[0].metric("Order lines analysed", f"{stats['lines']:,}")
    c[1].metric("Customer orders", f"{stats['orders']:,}")
    c[2].metric("Orders with mixed picking", f"{stats['picking_orders']:,}")
    c[3].metric("Fully runnable orders", f"{stats['runnable_orders']:,}",
                help="Orders where every picking SKU has a validated physical spec "
                     "(case dimensions and weight). The rest have at least one SKU with "
                     "missing data, which the engine refuses to guess.")


def sidebar(runnable: pd.DataFrame, skus: pd.DataFrame):
    st.sidebar.header("Choose an order")
    mode = st.sidebar.radio("Mode", ["Real order", "Build your own order"], label_visibility="collapsed")

    if mode == "Real order":
        demos = load_demo_orders()
        options = ["(type an order number below)"] + [f"{r.order}  |  {r.label}" for r in demos.itertuples()]
        if "order_input" not in st.session_state:
            st.session_state.order_input = demos["order"].iloc[0] if len(demos) else ""
        pick = st.sidebar.selectbox("Showcase orders", options, index=1 if len(demos) else 0)
        if pick != options[0] and st.session_state.get("_last_pick") != pick:
            st.session_state.order_input = pick.split("|")[0].strip()
        st.session_state._last_pick = pick

        if st.sidebar.button("🎲 Random runnable order", width="stretch"):
            st.session_state.order_input = random.choice(load_fast_orders())
            st.session_state._last_pick = pick

        order_id = st.sidebar.text_input("Order number", key="order_input").strip()
        info = runnable[runnable["PEDIDO"] == order_id]
        if len(info):
            r = info.iloc[0]
            st.sidebar.caption(f"{r.customer} | {str(r.date)[:10]} | {int(r.products)} picking SKUs, "
                               f"{int(r.picking_cases)} picking cases")
        elif order_id:
            st.sidebar.warning("Not in the runnable list: this order is missing, has no mixed "
                               "picking, or includes a SKU without validated dimensions.")
        st.sidebar.caption("Most orders build in a few seconds. A few very fragmented ones "
                           "can take a couple of minutes.")
        go_btn = st.sidebar.button("Build pallets", type="primary", width="stretch")
        return ("existing", order_id) if go_btn else None

    st.sidebar.caption("Add products and case quantities. Only SKUs with validated case "
                       "dimensions and weights are listed.")
    labels = skus["label"].tolist()
    picks = []
    for word in ("COCACOLA", "FANTA", "SPRITE"):
        match = [l for l in labels
                 if l.split("|", 1)[1].strip().startswith(word) and "LATA33" in l]
        if match:
            picks.append(match[0])
    picks = picks or labels[:3]
    default = pd.DataFrame({"Cases": [60, 40, 30][: len(picks)], "Product": picks})
    if "manual_df" not in st.session_state:
        st.session_state.manual_df = default
    edited = st.sidebar.data_editor(
        st.session_state.manual_df,
        num_rows="dynamic",
        width="stretch",
        column_config={
            "Cases": st.column_config.NumberColumn("Cases", min_value=1, max_value=2000, step=1,
                                                   required=True, width="small"),
            "Product": st.column_config.SelectboxColumn("Product", options=labels, required=True, width="large"),
        },
        key="manual_editor",
    )
    go_btn = st.sidebar.button("Build pallets", type="primary", width="stretch")
    if not go_btn:
        return None
    rows = []
    for r in edited.dropna().itertuples():
        rows.append((int(str(r.Product).split("|")[0].strip()), float(r.Cases)))
    return ("manual", rows)


def show_result(run):
    res = run["result"]
    pallets = res.get("palets_picking", [])

    title = "Your custom order" if run["label"] == "MANUAL" else f"Order {run['label']}"
    st.subheader(title)
    if "seconds" in run:
        st.caption(f"Built and validated in {run['seconds']:.1f} s")
    c = st.columns(5)
    c[0].metric("Full single-SKU pallets", int(res.get("palets_completos", 0)),
                help="Lines big enough to ship as whole pallets straight from stock.")
    c[1].metric("Half pallets", int(res.get("n_semipalet", 0)))
    c[2].metric("Mixed pallets built", len(pallets),
                help="Pallets this engine builds from the leftover picking cases.")
    c[3].metric("Total pallet equivalents", f"{float(res.get('total_palets', 0)):.2f}")
    low = [p for p in pallets if p.get("ocupacion", 0) < 0.75]
    c[4].metric("Pallets under 75% full", len(low))

    if not pallets:
        st.info("This order ships entirely as full or half pallets, so there is nothing to mix. "
                "Try another order to see the 3D builder in action.")
    else:
        products = sorted({str(b.get("descripcion")) for p in pallets for b in p.get("cajas_3d", [])})
        colours = {p: PALETTE[n % len(PALETTE)] for n, p in enumerate(products)}

        tabs = st.tabs([f"Pallet {n}  ({len(p.get('cajas_3d', []))} cases)" for n, p in enumerate(pallets, 1)])
        for tab, (n, p) in zip(tabs, enumerate(pallets, 1)):
            with tab:
                boxes = p.get("cajas_3d", [])
                left, right = st.columns([3, 2])
                with right:
                    m = st.columns(2)
                    m[0].metric("Volume used", f"{float(p.get('ocupacion', 0)) * 100:.1f}%")
                    m[1].metric("Gross weight", f"{float(p.get('peso_bruto_total_kg', p.get('peso_total', 0))):.0f} kg")
                    m = st.columns(2)
                    m[0].metric("Total height", f"{float(p.get('altura_total_cm', 0)):.1f} cm")
                    m[1].metric("Cases", len(boxes))
                    layers = sorted({int(b.get("layer_id", 1)) for b in boxes}) or [1]
                    max_layer = layers[-1]
                    if len(layers) > 1:
                        max_layer = st.slider("Show layers up to", layers[0], layers[-1], layers[-1],
                                              key=f"layer_{run['label']}_{n}")
                    st.markdown("**Layers (bottom to top)**")
                    st.dataframe(layer_table(boxes), hide_index=True, width="stretch")
                with left:
                    st.plotly_chart(pallet_figure(boxes, colours, max_layer), width="stretch",
                                    key=f"fig_{run['label']}_{n}")

    d1, d2, _ = st.columns([1, 1, 2])
    csv_bytes = export_csv_bytes(run) if pallets else None
    if csv_bytes:
        d1.download_button("⬇️ Placement CSV", csv_bytes, f"outputs_visualizacion_{run['label']}.csv",
                           "text/csv", width="stretch")
    d2.download_button("⬇️ HTML dashboard", dashboard_html(run), f"dashboard_{run['label']}.html",
                       "text/html", width="stretch")
    with st.expander("Engine log (raw planner output)"):
        st.code(run["text"] or "", language=None)


def about():
    with st.expander("How the engine works"):
        st.markdown(
            """
1. **Split the order.** Lines large enough for whole or half pallets ship as they are. The leftover
   *picking* cases are what needs mixing.
2. **Sort by warehouse route.** Picking cases are ordered by station, which also gives a sensible
   heavy-and-stable-first stacking order. Allergen products are kept apart.
3. **Plan compact layers.** For each SKU the planner tests normal and rotated orientations, rows,
   columns and shelf combinations, and keeps the pattern with the most cases and least wasted area.
4. **Validate every case exactly.** Inside the 120 x 80 cm footprint, no overlaps, at least 70% of the
   base supported by the cases below, top at or under 180 cm, pallet under 1,000 kg.
5. **Fall back case by case** when a full layer does not fit, then open a new pallet when nothing valid remains.
6. **Audit before export.** An independent check re-verifies counts, bounds, overlaps, support,
   height, weight and station order. If anything fails, nothing is exported.

On the benchmark order the final system used **5 pallets versus 6** for the ICSO baseline, placing
300/300 cases with zero overlaps. The code ships with 61 passing unit tests.
            """
        )


def main():
    df, peso_max, runnable, skus, stats = load_engine()
    header(stats)
    about()
    request = sidebar(runnable, skus)

    if request:
        kind, payload = request
        try:
            started = time.perf_counter()
            with st.spinner("Building and validating pallets..."):
                if kind == "existing":
                    if not payload:
                        st.warning("Enter an order number.")
                        return
                    run = run_existing(payload)
                    if run is None:
                        st.error(f"Order {payload} was not found in the dataset.")
                        return
                else:
                    if not payload:
                        st.warning("Add at least one product.")
                        return
                    run = run_manual(payload)
                    if run is None:
                        st.error("No valid products in the manual order.")
                        return
            run["seconds"] = time.perf_counter() - started
            st.session_state.run = run
        except Exception as exc:  # engine refuses orders with unvalidated SKUs, etc.
            st.session_state.pop("run", None)
            st.error(f"The engine rejected this order: {exc}")
            st.caption("This usually means a SKU in the order has no validated case dimensions or "
                       "weight. The engine is built to stop rather than guess. Try a showcase order "
                       "or the random button, which only pick fully covered orders.")
            return

    if "run" in st.session_state:
        show_result(st.session_state.run)
    else:
        st.info("👈 Pick a showcase order (or build your own) and press **Build pallets**.")


main()
