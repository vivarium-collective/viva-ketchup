#!/usr/bin/env python3
"""Generate a self-contained HTML demo report for viva-ketchup.

Runs the *real* KETCHUP/IPOPT solver through the ``KetchupEstimator`` Step on
two K-FIT E. coli models (k-ecoli74, k-ecoli307), parses IPOPT's own iteration
log for a convergence trace, and renders an interactive report.

The solves are deliberately **bounded** (max_iter / max_cpu_time) so the demo
finishes quickly.  Reported solutions are therefore genuine but *partial* — the
IPOPT termination condition ('maxIterations'/'maxTimeLimit'/'optimal') is shown
honestly for each run.  Remove the bound (default options use max_iter 5000) to
drive a run to full convergence.
"""

from __future__ import annotations

import html
import json
import os
import re
import sys
import time
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))

from process_bigraph import allocate_core  # noqa: E402
from viva_ketchup import KetchupEstimator, KetchupDynamicEstimator  # noqa: E402
from viva_ketchup.composites import ketchup_baseline  # noqa: E402

OUT = HERE / "report.html"
WORKDIR = HERE / "_run"
WORKDIR.mkdir(exist_ok=True)

# Per-run IPOPT bound. Keep each solve fast but show a real descent.
DEMO_OPT = """tol 0.001
constr_viol_tol 0.001
compl_inf_tol 0.001
mu_strategy adaptive
max_iter {max_iter}
max_cpu_time {max_cpu}
output_file {logfile}
print_user_options no
print_timing_statistics no
"""

CONFIGS = [
    {
        "id": "ecoli74",
        "title": "k-ecoli74",
        "subtitle": "Core E. coli kinetic model — baseline fit",
        "description": "74-reaction core carbon-metabolism model (glycolysis, PPP, "
        "TCA). KETCHUP fits forward/reverse rate constants for every elementary "
        "step against measured steady-state fluxes.",
        "model_name": "k-ecoli74",
        "seed": 0,
        "max_iter": 1200,
        "max_cpu": 90,
        "accent": "#2563eb",
    },
    {
        "id": "ecoli307",
        "title": "k-ecoli307",
        "subtitle": "Genome-scale-derived kinetic model — baseline fit",
        "description": "307-reaction kinetic model — a much larger NLP "
        "(~2,500 rate constants). Demonstrates the wrapper scaling to a "
        "substantially bigger parameter-estimation problem.",
        "model_name": "k-ecoli307",
        "seed": 0,
        "max_iter": 1200,
        "max_cpu": 90,
        "accent": "#059669",
    },
    {
        "id": "ecoli74_ms",
        "title": "k-ecoli74 · multistart",
        "subtitle": "Same model, alternate random seed",
        "description": "Re-fits k-ecoli74 from a different initialisation seed "
        "(driven through the Step's `seed` input port). Different starting points "
        "explore different regions of the non-convex landscape.",
        "model_name": "k-ecoli74",
        "seed": 7,
        "max_iter": 1200,
        "max_cpu": 90,
        "accent": "#d97706",
    },
]


def parse_ipopt_log(logfile: Path):
    """Extract (iter, objective, inf_pr) rows from an IPOPT output log."""
    iters, obj, infpr = [], [], []
    if not logfile.is_file():
        return {"iter": iters, "objective": obj, "inf_pr": infpr}
    # Match only normal iteration rows; skip IPOPT restoration-phase rows
    # ("<n>r ...") whose objective is from a different (feasibility) subproblem.
    row = re.compile(r"^\s*(\d+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+")
    for line in logfile.read_text(errors="ignore").splitlines():
        m = row.match(line)
        if not m:
            continue
        try:
            it = int(m.group(1)); o = float(m.group(2)); ip = float(m.group(3))
        except ValueError:
            continue
        # skip duplicate iter headers / restoration repeats
        if iters and it == iters[-1]:
            continue
        iters.append(it); obj.append(o); infpr.append(ip)
    return {"iter": iters, "objective": obj, "inf_pr": infpr}


def run_config(cfg: dict) -> dict:
    logfile = WORKDIR / f"{cfg['id']}_ipopt.log"
    if logfile.exists():
        logfile.unlink()
    optfile = WORKDIR / f"{cfg['id']}_ipopt.opt"
    optfile.write_text(DEMO_OPT.format(
        max_iter=cfg["max_iter"], max_cpu=cfg["max_cpu"], logfile=str(logfile)))

    step = KetchupEstimator(
        config={
            "model_name": cfg["model_name"],
            "seed": cfg["seed"],
            "solver_options": str(optfile),
            "output_dir": str(WORKDIR),
        },
        core=allocate_core(),
    )

    cwd = os.getcwd()
    os.chdir(WORKDIR)
    print(f"  running {cfg['id']} ({cfg['model_name']}, seed={cfg['seed']}) ...",
          flush=True)
    t0 = time.perf_counter()
    try:
        result = step.update({"seed": cfg["seed"]})
    finally:
        os.chdir(cwd)
    wall = time.perf_counter() - t0
    trace = parse_ipopt_log(logfile)
    print(f"    -> {result['status']} | SSE={result['sse']:.4g} | "
          f"{result['n_parameters']} params | {wall:.1f}s "
          f"| {len(trace['iter'])} iters logged", flush=True)
    return {"cfg": cfg, "result": result, "trace": trace, "wall": wall}


# ------------------------------------------------------ dynamic (time-series)
CONFIGS_DYNAMIC = [
    {
        "id": "fdh",
        "title": "FDH",
        "subtitle": "formate dehydrogenase — NADH production (Fig 2 benchmark)",
        "description": "KETCHUP's dynamic extension fits a custom Michaelis-Menten "
        "rate law to NADH(t) across 9 initial conditions (NAD⁺ × formate). "
        "Reproduces the paper's Fig 2 — fitted curve vs measured points.",
        "model_name": "FDH",
        "max_iter": 600,
        "max_cpu": 60,
        "max_panels": 9,
        "accent": "#0891b2",
    },
    {
        "id": "bdh",
        "title": "BDH",
        "subtitle": "2,3-butanediol dehydrogenase — NADH consumption",
        "description": "A reversible convenience-kinetics rate law (Haldane-"
        "constrained) fit to a separate cell-free assay where NADH is consumed "
        "(acetoin + NADH → 2,3-BD + NAD⁺) across many initial conditions.",
        "model_name": "BDH",
        "max_iter": 3000,
        "max_cpu": 150,
        "max_panels": 9,
        "accent": "#be185d",
    },
]


def run_dynamic(cfg: dict) -> dict:
    optfile = WORKDIR / f"{cfg['id']}_dyn_ipopt.opt"
    optfile.write_text(
        f"tol 0.001\nconstr_viol_tol 0.001\nmu_strategy adaptive\n"
        f"max_iter {cfg['max_iter']}\nmax_cpu_time {cfg['max_cpu']}\n"
        f"print_user_options no\n")
    step = KetchupDynamicEstimator(
        config={"model_name": cfg["model_name"], "seed": 0,
                "solver_options": str(optfile), "output_dir": str(WORKDIR)},
        core=allocate_core(),
    )
    cwd = os.getcwd()
    os.chdir(WORKDIR)
    print(f"  running dynamic {cfg['id']} ({cfg['model_name']}) ...", flush=True)
    t0 = time.perf_counter()
    try:
        result = step.update({"seed": 0})
    finally:
        os.chdir(cwd)
    wall = time.perf_counter() - t0
    print(f"    -> {result['status']} | SSE={result['sse']:.4g} | "
          f"{result['n_parameters']} params | {result['n_experiments']} datasets "
          f"| {wall:.1f}s", flush=True)
    return {"cfg": cfg, "result": result, "wall": wall}


def _panel_label(cond: dict) -> str:
    """Short initial-condition label for a Fig-2 panel."""
    bits = []
    for k in ("nad", "formate", "actn", "23bdo"):
        if k in cond and cond[k]:
            nice = {"nad": "NAD⁺", "formate": "formate",
                    "actn": "acetoin", "23bdo": "2,3-BD"}[k]
            bits.append(f"{cond[k]:g} {nice}")
    return ", ".join(bits)


# ----------------------------------------------------------------------- HTML
def _fmt(x, n=4):
    try:
        return f"{float(x):.{n}g}"
    except (TypeError, ValueError):
        return str(x)


def json_tree(obj, depth=0):
    """Collapsible color-coded JSON tree."""
    ind = "  " * depth
    if isinstance(obj, dict):
        if not obj:
            return '<span class="muted">{}</span>'
        items = []
        for k, v in obj.items():
            items.append(
                f'{ind}  <span class="jk">"{html.escape(str(k))}"</span>: '
                + json_tree(v, depth + 1))
        collapsed = " collapsed" if depth >= 2 else ""
        inner = ",\n".join(items)
        return (f'<span class="tog{collapsed}">{{</span><div class="blk">\n'
                f'{inner}\n{ind}</div>}}')
    if isinstance(obj, list):
        if len(obj) <= 8 and all(isinstance(x, (int, float, str, bool)) for x in obj):
            return "[" + ", ".join(json_tree(x, depth + 1) for x in obj) + "]"
        items = [f"{ind}  " + json_tree(x, depth + 1) for x in obj]
        return "[<div class=\"blk\">\n" + ",\n".join(items) + f"\n{ind}</div>]"
    if isinstance(obj, bool):
        return f'<span class="jb">{str(obj).lower()}</span>'
    if obj is None:
        return '<span class="muted">null</span>'
    if isinstance(obj, (int, float)):
        return f'<span class="jn">{_fmt(obj, 6)}</span>'
    return f'<span class="js">"{html.escape(str(obj))}"</span>'


def _viz_core():
    core = allocate_core()
    try:
        core.register_process("KetchupEstimator", KetchupEstimator)
    except Exception:
        try:
            core.register_link("KetchupEstimator", KetchupEstimator)
        except Exception:
            pass
    return core


def bigraph_fragment(doc, idx):
    try:
        from bigraph_viz2 import emit_html
        return emit_html(doc, height="460px", inspector=True,
                         dedupe=(idx > 0), id=f"bigraph_{idx}", core=_viz_core())
    except Exception as exc:  # pragma: no cover
        return f'<p class="muted">bigraph-viz2 unavailable: {html.escape(str(exc))}</p>'


def build_dynamic_section(dr, base_idx, plot_scripts) -> str:
    """Fig-2-style grid of NADH(t) fit panels for one dynamic run."""
    cfg, res = dr["cfg"], dr["result"]
    acc = cfg["accent"]
    keys = list(res["nadh_fit"].keys())[: cfg["max_panels"]]

    cards = [
        ("Status", res["status"]),
        ("Total SSE", _fmt(res["sse"], 4)),
        ("Parameters", f'{res["n_parameters"]}'),
        ("Datasets fit", f'{res["n_experiments"]}'),
        ("Solve time", f'{dr["wall"]:.1f} s'),
    ]
    card_html = "".join(
        f'<div class="card"><div class="cv" style="color:{acc}">'
        f'{html.escape(str(v))}</div><div class="cl">{k}</div></div>'
        for k, v in cards)

    panels = []
    for j, key in enumerate(keys):
        pid = f"dyn_{cfg['id']}_{j}"
        cond = res["initial_conditions"].get(key, {})
        label = _panel_label(cond) or key
        plot_scripts.append(f"""
        Plotly.newPlot('{pid}', [
          {{x: {json.dumps([round(t,3) for t in res['data_time'][key]])},
            y: {json.dumps([round(v,4) for v in res['data_nadh'][key]])},
            mode:'markers', name:'measured',
            marker:{{color:'#dc2626', size:5, opacity:0.75}}}},
          {{x: {json.dumps([round(t,3) for t in res['nadh_time'][key]])},
            y: {json.dumps([round(v,4) for v in res['nadh_fit'][key]])},
            mode:'lines', name:'KETCHUP fit', line:{{color:'{acc}', width:2}}}}
        ], {{margin:{{t:24,r:8,l:42,b:30}}, height:210, showlegend:false,
            title:{{text:'{html.escape(label)}', font:{{size:11}}, x:0.5}},
            xaxis:{{title:{{text:'time (min)', font:{{size:10}}}}}},
            yaxis:{{title:{{text:'NADH (mM)', font:{{size:10}}}}}}}},
            {{displayModeBar:false}});""")
        panels.append(f'<div class="dpanel"><div id="{pid}"></div></div>')

    kp_view = {k: round(v, 4) for k, v in list(res["kinetic_parameters"].items())}
    return f"""
    <section id="{cfg['id']}">
      <div class="shead" style="border-color:{acc}">
        <h2>{html.escape(cfg['title'])} · time-series fit</h2>
        <p class="sub">{html.escape(cfg['subtitle'])}</p>
      </div>
      <p class="desc">{html.escape(cfg['description'])}</p>
      <div class="cards">{card_html}</div>
      <div class="panel"><h3>NADH(t): KETCHUP fit (line) vs measured (points)</h3>
        <div class="dgrid">{''.join(panels)}</div></div>
      <div class="panel"><h3>Fitted kinetic parameters</h3>
        <pre class="tree">{json_tree(kp_view)}</pre></div>
    </section>"""


def build_html(runs, dyn_runs=None) -> str:
    dyn_runs = dyn_runs or []
    nav = "".join(
        f'<a href="#{r["cfg"]["id"]}">{html.escape(r["cfg"]["title"])}</a>'
        for r in runs)
    nav += "".join(
        f'<a href="#{d["cfg"]["id"]}">{html.escape(d["cfg"]["title"])} (t)</a>'
        for d in dyn_runs)

    # one composite document for the architecture diagram
    arch_doc = ketchup_baseline(model_name="k-ecoli74", seed=0)
    arch_frag = bigraph_fragment(arch_doc, 0)

    sections = []
    plot_scripts = []
    for i, r in enumerate(runs):
        cfg, res, trace = r["cfg"], r["result"], r["trace"]
        acc = cfg["accent"]

        # solver-truthful summary numbers from the real IPOPT log
        final_obj = trace["objective"][-1] if trace["objective"] else float("nan")
        final_infpr = trace["inf_pr"][-1] if trace["inf_pr"] else float("nan")

        # metrics
        cards = [
            ("Status", res["status"]),
            ("IPOPT objective", _fmt(final_obj, 5)),
            ("Primal infeas.", _fmt(final_infpr, 3)),
            ("Parameters", f'{res["n_parameters"]:,}'),
            ("Fluxes fit", f'{len(res["fluxes"]):,}'),
            ("Solve time", f'{r["wall"]:.1f} s'),
            ("IPOPT iters", f'{len(trace["iter"]):,}'),
        ]
        card_html = "".join(
            f'<div class="card"><div class="cv" style="color:{acc}">'
            f'{html.escape(str(v))}</div><div class="cl">{k}</div></div>'
            for k, v in cards)

        # charts: convergence (obj + inf_pr, log y), top fluxes, kf histogram
        conv_id = f"conv_{i}"; flux_id = f"flux_{i}"; hist_id = f"hist_{i}"
        plot_scripts.append(f"""
        Plotly.newPlot('{conv_id}', [
          {{x: {json.dumps(trace['iter'])}, y: {json.dumps(trace['objective'])},
            name:'objective', mode:'lines', line:{{color:'{acc}',width:2}}}},
          {{x: {json.dumps(trace['iter'])}, y: {json.dumps(trace['inf_pr'])},
            name:'primal infeas.', mode:'lines', yaxis:'y2',
            line:{{color:'#94a3b8',width:1.5,dash:'dot'}}}}
        ], {{margin:{{t:10,r:50,l:55,b:40}}, height:300,
            xaxis:{{title:'IPOPT iteration'}},
            yaxis:{{title:'objective', type:'log'}},
            yaxis2:{{title:'inf_pr', overlaying:'y', side:'right', type:'log',
                     showgrid:false}},
            legend:{{orientation:'h', y:1.15}}}}, {{displayModeBar:false}});""")

        fluxes = sorted(res["fluxes"].items(), key=lambda kv: abs(kv[1]),
                        reverse=True)[:20]
        plot_scripts.append(f"""
        Plotly.newPlot('{flux_id}', [{{
          x: {json.dumps([k for k, _ in fluxes])},
          y: {json.dumps([round(v, 4) for _, v in fluxes])},
          type:'bar', marker:{{color:'{acc}'}}
        }}], {{margin:{{t:10,r:10,l:55,b:80}}, height:300,
            yaxis:{{title:'fitted rate'}}, xaxis:{{tickangle:-45}}}},
            {{displayModeBar:false}});""")

        import math
        kf_vals = [math.log10(v) for v in res["kf"].values() if v and v > 0]
        kr_vals = [math.log10(v) for v in res["kr"].values() if v and v > 0]
        plot_scripts.append(f"""
        Plotly.newPlot('{hist_id}', [
          {{x: {json.dumps([round(v,3) for v in kf_vals])}, type:'histogram',
            name:'log10 kf', opacity:0.7, marker:{{color:'{acc}'}}, nbinsx:30}},
          {{x: {json.dumps([round(v,3) for v in kr_vals])}, type:'histogram',
            name:'log10 kr', opacity:0.55, marker:{{color:'#64748b'}}, nbinsx:30}}
        ], {{barmode:'overlay', margin:{{t:10,r:10,l:55,b:40}}, height:300,
            xaxis:{{title:'log10(rate constant)'}}, yaxis:{{title:'count'}},
            legend:{{orientation:'h', y:1.15}}}}, {{displayModeBar:false}});""")

        # PBG result document tree (trimmed: maps shown as counts + first items)
        doc_view = {
            "step": "KetchupEstimator",
            "model_name": cfg["model_name"],
            "seed": cfg["seed"],
            "outputs": {
                "status": res["status"],
                "ipopt_objective_final": round(final_obj, 4),
                "primal_infeasibility_final": round(final_infpr, 4),
                "model_error_snapshot": round(res["sse"], 4),
                "solve_time": round(res["solve_time"], 3),
                "n_parameters": res["n_parameters"],
                "kf": {**dict(list(res["kf"].items())[:3]),
                       "...": f'{len(res["kf"])} total'},
                "fluxes": {**{k: round(v, 4)
                              for k, v in list(res["fluxes"].items())[:3]},
                           "...": f'{len(res["fluxes"])} total'},
            },
        }

        sections.append(f"""
        <section id="{cfg['id']}">
          <div class="shead" style="border-color:{acc}">
            <h2>{html.escape(cfg['title'])}</h2>
            <p class="sub">{html.escape(cfg['subtitle'])}</p>
          </div>
          <p class="desc">{html.escape(cfg['description'])}</p>
          <div class="cards">{card_html}</div>
          <div class="grid2">
            <div class="panel"><h3>IPOPT convergence</h3><div id="{conv_id}"></div></div>
            <div class="panel"><h3>Parameter distribution</h3><div id="{hist_id}"></div></div>
          </div>
          <div class="panel"><h3>Top fitted fluxes (|rate|)</h3><div id="{flux_id}"></div></div>
          <div class="panel"><h3>Result document</h3>
            <pre class="tree">{json_tree(doc_view)}</pre></div>
        </section>""")

    dyn_sections = [build_dynamic_section(d, i, plot_scripts)
                    for i, d in enumerate(dyn_runs)]

    runtime_total = (sum(r["wall"] for r in runs)
                     + sum(d["wall"] for d in dyn_runs))
    generated = time.strftime("%Y-%m-%d %H:%M")

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>viva-ketchup — KETCHUP demo report</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
:root {{ --bg:#f8fafc; --fg:#0f172a; --mut:#64748b; --line:#e2e8f0; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  background:var(--bg); color:var(--fg); line-height:1.5; }}
header.top {{ position:sticky; top:0; z-index:20; background:#fff;
  border-bottom:1px solid var(--line); padding:14px 28px;
  display:flex; align-items:baseline; gap:18px; flex-wrap:wrap; }}
header.top h1 {{ font-size:18px; margin:0; }}
header.top .tag {{ font-size:12px; color:var(--mut); }}
nav {{ margin-left:auto; display:flex; gap:14px; flex-wrap:wrap; }}
nav a {{ font-size:13px; color:#334155; text-decoration:none; padding:4px 8px;
  border-radius:6px; }}
nav a:hover {{ background:#eef2ff; color:#1e3a8a; }}
main {{ max-width:1080px; margin:0 auto; padding:28px; }}
.lead {{ background:#fff; border:1px solid var(--line); border-radius:12px;
  padding:22px 26px; margin-bottom:26px; }}
.lead h2 {{ margin:0 0 8px; font-size:22px; }}
.lead p {{ margin:6px 0; color:#334155; }}
.lead code {{ background:#f1f5f9; padding:1px 6px; border-radius:5px; font-size:13px; }}
.note {{ font-size:13px; color:var(--mut); border-left:3px solid #cbd5e1;
  padding:6px 12px; margin-top:12px; background:#f8fafc; }}
section {{ background:#fff; border:1px solid var(--line); border-radius:12px;
  padding:24px 26px; margin-bottom:26px; }}
.shead {{ border-left:4px solid; padding-left:14px; margin-bottom:6px; }}
.shead h2 {{ margin:0; font-size:20px; }}
.sub {{ margin:2px 0 0; color:var(--mut); font-size:14px; }}
.desc {{ color:#334155; font-size:14px; margin:10px 0 18px; }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
  gap:12px; margin-bottom:20px; }}
.card {{ background:#f8fafc; border:1px solid var(--line); border-radius:10px;
  padding:14px 16px; text-align:center; }}
.cv {{ font-size:20px; font-weight:650; }}
.cl {{ font-size:12px; color:var(--mut); margin-top:3px; }}
.grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:18px; }}
@media (max-width:760px) {{ .grid2 {{ grid-template-columns:1fr; }} }}
.panel {{ border:1px solid var(--line); border-radius:10px; padding:14px 16px;
  margin-bottom:18px; }}
.panel h3 {{ margin:0 0 10px; font-size:14px; color:#334155; font-weight:600; }}
pre.tree {{ font-family:'SF Mono',Menlo,Consolas,monospace; font-size:12.5px;
  background:#fbfdff; border:1px solid var(--line); border-radius:8px;
  padding:14px; overflow:auto; margin:0; }}
.jk {{ color:#7c3aed; }} .js {{ color:#059669; }} .jn {{ color:#2563eb; }}
.jb {{ color:#d97706; }} .muted {{ color:#94a3b8; }}
.tog {{ cursor:pointer; }} .tog::before {{ content:'▾ '; color:#94a3b8; }}
.tog.collapsed::before {{ content:'▸ '; }}
.tog.collapsed + .blk {{ display:none; }}
.blk {{ display:block; }}
.dgrid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:10px; }}
@media (max-width:760px) {{ .dgrid {{ grid-template-columns:1fr; }} }}
.dpanel {{ border:1px solid var(--line); border-radius:8px; padding:4px; }}
.parthead {{ margin:34px 0 18px; padding:6px 0 4px; border-bottom:2px solid #cbd5e1; }}
.parthead h2 {{ margin:0; font-size:16px; color:#475569; letter-spacing:0.04em;
  text-transform:uppercase; }}
footer {{ text-align:center; color:var(--mut); font-size:12px; padding:30px; }}
</style></head><body>
<header class="top">
  <h1>🧪 viva-ketchup</h1>
  <span class="tag">real KETCHUP / IPOPT bridge · process-bigraph Step</span>
  <nav>{nav}</nav>
</header>
<main>
  <div class="lead">
    <h2>KETCHUP kinetic parameter estimation, wrapped as a process-bigraph Step</h2>
    <p><a href="https://github.com/maranasgroup/KETCHUP">KETCHUP</a> (Maranas group)
      fits the kinetic parameters of a metabolic network by solving one IPOPT
      nonlinear program so the model reproduces measured steady-state fluxes and
      metabolite concentrations. <code>KetchupEstimator</code> bridges the genuine
      <code>ktools</code> solver — its <code>update()</code> builds the real Pyomo
      model and calls IPOPT; nothing here is reimplemented or mocked.</p>
    <p>Two capabilities are shown. <b>Part I — steady-state</b>: large-scale
      flux fitting on two K-FIT <i>E. coli</i> models (<code>k-ecoli74</code>,
      <code>k-ecoli307</code>) plus a seed-driven multistart. <b>Part II —
      time-series</b>: the dynamic KETCHUP extension (Hu, Jilani, Olson &amp;
      Maranas, <i>PLOS Comput Biol</i> 2025) fitting cell-free enzyme kinetics
      (FDH, BDH) to NADH-vs-time data — reproducing the paper's Fig 2 via a
      second Step, <code>KetchupDynamicEstimator</code>.</p>
    <div class="note">Solves are bounded (max_iter / max_cpu_time) so the demo
      finishes in ~{runtime_total:.0f}s total — reported solutions are genuine but
      <b>partial</b>, and each run's IPOPT termination condition is shown as-is.
      The objective <i>rises</i> while primal infeasibility <i>falls</i>: IPOPT is
      driving a random initial guess onto the steady-state manifold (satisfying
      every rate-law constraint), trading apparent error for feasibility. Charts
      show only normal iterations (restoration-phase sub-iterations are excluded).
      The default options (max_iter 5000) drive a run to full convergence.</div>
  </div>

  <section id="architecture">
    <div class="shead" style="border-color:#7c3aed">
      <h2>Architecture</h2>
      <p class="sub">The <code>ketchup_baseline</code> composite — Step → result
        stores → emitter</p>
    </div>
    <div class="panel">{arch_frag}</div>
  </section>

  <div class="parthead"><h2>Part I · Steady-state flux estimation</h2></div>
  {''.join(sections)}

  <div class="parthead"><h2>Part II · Time-series (dynamic) estimation</h2></div>
  {''.join(dyn_sections)}

  <footer>Generated {generated} · {len(runs)} steady-state + {len(dyn_runs)} dynamic
    real IPOPT runs · total solver wall-time {runtime_total:.1f}s · viva-ketchup v0.1.0</footer>
</main>
<script>
document.querySelectorAll('.tog').forEach(function(t){{
  t.addEventListener('click', function(){{ t.classList.toggle('collapsed'); }});
}});
{''.join(plot_scripts)}
</script>
</body></html>"""


def main():
    print("Part I: steady-state KETCHUP/IPOPT estimations (bounded) ...")
    runs = [run_config(cfg) for cfg in CONFIGS]
    print("Part II: dynamic (time-series) KETCHUP/IPOPT estimations ...")
    dyn_runs = [run_dynamic(cfg) for cfg in CONFIGS_DYNAMIC]
    print("Rendering report ...")
    OUT.write_text(build_html(runs, dyn_runs))
    print(f"Wrote {OUT}")
    webbrowser.open("file://" + str(OUT))


if __name__ == "__main__":
    main()
