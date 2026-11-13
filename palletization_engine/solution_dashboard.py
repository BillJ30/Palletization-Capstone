"""Generate a local HTML dashboard from an already computed solution."""

from collections import Counter
from html import escape
from pathlib import Path

from pallet_validation import rectangle_union_area


def _fmt(value, decimals=1):
    try:
        return f"{float(value):.{decimals}f}"
    except (TypeError, ValueError):
        return "-"


def _layer_cards(boxes):
    layers = []
    for layer_number, z in enumerate(sorted({round(box.get("z_cm", 14.4), 6) for box in boxes}), 1):
        layer_boxes = [box for box in boxes if abs(float(box.get("z_cm", 0)) - z) <= 1e-6]
        rectangles = [
            (float(box.get("x_cm", 0)), float(box.get("y_cm", 0)),
             float(box.get("x_cm", 0)) + float(box.get("ancho_cm", 0)),
             float(box.get("y_cm", 0)) + float(box.get("largo_cm", 0)))
            for box in layer_boxes
        ]
        covered_area = rectangle_union_area(rectangles)
        utilization = min(100.0, covered_area / (120.0 * 80.0) * 100.0)
        mix = Counter(box.get("descripcion", "Unknown") for box in layer_boxes)
        total = max(1, len(layer_boxes))
        mix_rows = "".join(
            f"<div class=\"mix-row\"><div class=\"mix-label\"><span>{escape(str(name))}</span><strong>{count} cases</strong></div>"
            f"<div class=\"mix-track\"><div class=\"mix-fill\" style=\"width:{count / total * 100:.2f}%\"></div></div></div>"
            for name, count in mix.items()
        )
        top = max((float(box.get("z_cm", z)) + float(box.get("alto_cm", 0)) for box in layer_boxes), default=z)
        layers.append(f"""
        <div class="layer-card">
          <div class="layer-number"><span>Layer</span><strong>{layer_number}</strong></div>
          <div class="layer-main">
            <div class="layer-heading"><h3>Layer {layer_number}</h3><strong>{len(layer_boxes)} cases</strong></div>
            <div class="layer-meta"><span>Base z: {_fmt(z)} cm</span><span>Top z: {_fmt(top)} cm</span><span>Exact footprint filled: {_fmt(utilization)}%</span></div>
            <div class="layer-track"><div class="layer-fill" style="width:{utilization:.2f}%"></div></div>
            <div class="mix-list">{mix_rows}</div>
          </div>
        </div>
        """)
    return "".join(layers) or '<p class="caption">No layer records available.</p>'


def _pallet_card(pallet, index):
    boxes = pallet.get("cajas_3d", [])
    max_top = max((box.get("z_cm", 14.4) + box.get("alto_cm", 0) for box in boxes), default=14.4)
    cargo_height = max(0.0, max_top - 14.4)
    return f"""
    <section class="pallet-card">
      <div class="pallet-heading">
        <div><span class="eyebrow">PALLET {index}</span><h2>{escape(str(pallet.get('descripciones_str', 'Pallet')))}</h2></div>
        <div class="pallet-number">{len(boxes)} cases</div>
      </div>
      <div class="pallet-stats">
        <div><span>Reported utilization</span><strong>{_fmt(float(pallet.get('ocupacion', 0))*100, 1)}%</strong></div>
        <div><span>Total height</span><strong>{_fmt(pallet.get('altura_total_cm', 14.4))} cm</strong></div>
        <div><span>Cargo above base</span><strong>{_fmt(pallet.get('altura_carga_cm', 0))} cm</strong></div>
        <div><span>Gross weight</span><strong>{_fmt(pallet.get('peso_bruto_total_kg', pallet.get('peso_total', 0)))} kg</strong></div>
      </div>
      <div class="layers"><h3>Created layers</h3>{_layer_cards(boxes)}</div>
    </section>
    """


def render_solution_dashboard(result, order_label="Order"):
    pallets = result.get("palets_picking", [])
    all_boxes = [box for pallet in pallets for box in pallet.get("cajas_3d", [])]
    max_top = max((box.get("z_cm", 14.4) + box.get("alto_cm", 0) for box in all_boxes), default=14.4)
    gross = sum(float(pallet.get("peso_bruto_total_kg", pallet.get("peso_total", 0))) for pallet in pallets)
    cases = len(all_boxes)
    cards = "".join(_pallet_card(pallet, index) for index, pallet in enumerate(pallets, 1))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pallet solution - {escape(str(order_label))}</title>
<style>
:root {{ --ink:#1e2a2f; --muted:#6c7b80; --paper:#f4f1eb; --card:#fffdf8; --line:#ddd6ca; --accent:#176b87; }}
* {{ box-sizing:border-box; }} body {{ margin:0; color:var(--ink); background:var(--paper); font:15px/1.45 Segoe UI,system-ui,sans-serif; }}
main {{ max-width:1240px; margin:0 auto; padding:40px 24px 64px; }} header {{ display:flex; justify-content:space-between; gap:24px; align-items:end; margin-bottom:26px; }}
.eyebrow {{ color:var(--accent); font-size:11px; font-weight:700; letter-spacing:.14em; text-transform:uppercase; }} h1,h2,h3,p {{ margin-top:0; }} h1 {{ font:700 clamp(30px,5vw,54px)/1.0 Georgia,serif; margin:8px 0; }} h2 {{ margin:5px 0 0; font:700 23px Georgia,serif; }} h3 {{ font-size:14px; margin-bottom:10px; }} .subtitle,.caption {{ color:var(--muted); }}
.contract {{ text-align:right; color:var(--muted); font-size:13px; }} .kpis {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:18px; }} .kpi,.notice,.pallet-card {{ background:var(--card); border:1px solid var(--line); border-radius:16px; }} .kpi {{ padding:18px; }} .kpi span,.pallet-stats span {{ display:block; color:var(--muted); font-size:12px; }} .kpi strong {{ display:block; font:700 28px Georgia,serif; margin-top:5px; }}
.notice {{ padding:13px 16px; margin-bottom:18px; }} .pallet-card {{ padding:22px; margin-top:18px; }} .pallet-heading,.pallet-stats {{ display:flex; gap:18px; }} .pallet-heading {{ justify-content:space-between; align-items:start; }} .pallet-number {{ color:var(--accent); font-weight:700; }} .pallet-stats {{ border-top:1px solid var(--line); border-bottom:1px solid var(--line); padding:13px 0; margin:18px 0; flex-wrap:wrap; }} .pallet-stats>div {{ min-width:145px; flex:1; }} .pallet-stats strong {{ display:block; margin-top:3px; }}
.layers {{ margin-top:6px; }} .layer-card {{ display:flex; gap:15px; padding:14px 0; border-top:1px solid var(--line); }} .layer-number {{ width:58px; height:58px; flex:none; border-radius:50%; background:#dfece8; display:flex; flex-direction:column; align-items:center; justify-content:center; color:var(--accent); }} .layer-number span {{ font-size:10px; text-transform:uppercase; letter-spacing:.08em; }} .layer-number strong {{ font:700 24px Georgia,serif; }} .layer-main {{ flex:1; }} .layer-heading,.layer-meta,.mix-label {{ display:flex; justify-content:space-between; gap:10px; }} .layer-heading h3 {{ margin:0; font:700 18px Georgia,serif; }} .layer-meta {{ color:var(--muted); font-size:12px; margin:6px 0 8px; flex-wrap:wrap; }} .layer-track,.mix-track {{ height:9px; background:#e9e4db; border-radius:20px; overflow:hidden; }} .layer-fill {{ height:100%; background:var(--accent); border-radius:20px; }} .mix-list {{ margin-top:12px; display:grid; gap:8px; }} .mix-label {{ font-size:12px; margin-bottom:3px; }} .mix-label strong {{ color:var(--muted); font-weight:500; }} .mix-fill {{ height:100%; background:#d47b28; border-radius:20px; }}
@media(max-width:760px) {{ header {{ display:block; }} .contract {{ text-align:left; margin-top:16px; }} .kpis {{ grid-template-columns:repeat(2,1fr); }} .layer-card {{ gap:10px; }} .layer-meta {{ display:block; }} .layer-meta span {{ display:block; }} }}
</style></head><body><main>
<header><div><div class="eyebrow">Pallet solution dashboard</div><h1>{escape(str(order_label))}</h1><p class="subtitle">A clear view of the validated solution produced by the palletization engine.</p></div><div class="contract">Footprint: 120 x 80 cm<br>Base: 14.4 cm<br>Total height limit: 180 cm</div></header>
<div class="kpis"><div class="kpi"><span>Physical pallets</span><strong>{len(pallets)}</strong></div><div class="kpi"><span>Placed cases</span><strong>{cases}</strong></div><div class="kpi"><span>Highest top z</span><strong>{_fmt(max_top)} cm</strong></div><div class="kpi"><span>Total gross weight</span><strong>{_fmt(gross)} kg</strong></div></div>
{cards if cards else '<div class="notice">No picking pallets were produced.</div>'}
<p class="caption">Layers are listed from the pallet base upward. Each mix bar represents the number of cases of that product in the layer.</p>
</main></body></html>"""


def write_solution_dashboard(result, output_path, order_label="Order"):
    output_path = Path(output_path)
    output_path.write_text(render_solution_dashboard(result, order_label), encoding="utf-8")
    return output_path
