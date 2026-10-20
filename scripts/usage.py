"""Compile usage.pdf without inventing provider telemetry or billing details."""
import json
from pathlib import Path
import subprocess
import time
import re
import os

ROOT=Path(__file__).resolve().parents[1]


def escape(s):return str(s).replace('_',r'\_').replace('%',r'\%').replace('&',r'\&')


def main():
    for variable,directory in [('TEXMFVAR','.cache/texmf-var'),('TEXMFCONFIG','.config/texmf'),('TEXMFCACHE','.cache/texmf-cache')]:
        os.environ[variable]=str(ROOT/directory)
    goal_path=ROOT/'logs/agent-usage-snapshot.json'
    goal=json.loads(goal_path.read_text()) if goal_path.exists() else {'tokensUsed':0,'timeUsedSeconds':0,'note':'No orchestrator snapshot supplied.'}
    total=goal.get('tokensUsed',0);elapsed=goal.get('timeUsedSeconds',0)/3600
    records=[]
    for p in sorted((ROOT/'logs').glob('run-*.json')):
        r=json.loads(p.read_text())
        for stage in r['stages']:records.append((p.stem,stage))
    cpu=sum(s['cpu_seconds'] for _,s in records)/3600
    wall=sum(s['wall_seconds'] for _,s in records)/3600
    peak=max([s['peak_tree_rss_gb'] for _,s in records]+[0])
    early=[]
    for path in sorted((ROOT/'logs').glob('*.time')):
        content=path.read_text()
        user=re.search(r'User time \(seconds\): ([\d.]+)',content)
        system=re.search(r'System time \(seconds\): ([\d.]+)',content)
        elapsed_match=re.search(r'Elapsed .*: ([\d:.]+)\s*\n',content)
        if user and system and elapsed_match:
            parts=[float(v) for v in elapsed_match[1].split(':')]
            seconds=sum(v*60**i for i,v in enumerate(reversed(parts)))
            early.append(dict(log=path.name,wall_seconds=seconds,
                              cpu_seconds=float(user[1])+float(system[1])))
    data_bytes=sum(p.stat().st_size for p in (ROOT/'data').rglob('*') if p.is_file())
    tex=r'''\documentclass[11pt]{article}
\usepackage[margin=0.8in]{geometry}
\usepackage[T1]{fontenc}
\usepackage{booktabs,longtable,amsmath}
\usepackage[colorlinks=true,urlcolor=blue]{hyperref}
\begin{document}
\title{Usage and resource accounting: independent Hutko reanalysis}
\author{Measured local execution and explicit remote-usage scenarios}
\date{13 October 2026}\maketitle
\section{What is observed}
'''
    tex+=f"The orchestration goal counter reported {total:,} tokens at the saved snapshot, after {elapsed:.2f} hours of goal elapsed time. The exact snapshot is in \\texttt{{logs/agent-usage-snapshot.json}}. This is an orchestration counter, not a billing export. It does not separate input, cached input, output, hidden reasoning, or tool billing; the short setup before goal creation and subsequent reporting tokens are not included. No exact provider charge can be recovered from it.\n"
    tex+=r'''The code itself makes no model API calls. Its normal execution therefore consumes
zero inference tokens. Remote tokens belong to research, implementation, debugging,
and writing by the assistant, not to subsequent scientific reruns. The counter
is more defensible than estimating tokens from source-code characters, but its
billing semantics are not exposed here. No claim of an exact dollar bill is made.
\section{Dollar estimates with explicit assumptions}
Official pricing distinguishes input, cached input, and output; it also depends
on model, context length, and service tier
(\url{https://developers.openai.com/api/docs/pricing}, consulted 13 October 2026).
The exact billed model/tier, cache fraction, and account plan for this session are
not available. The following rate scenarios are illustrative API equivalents,
not assertions about the user's charge. Let $N$ be the saved counter. Treating
80--95\% of $N$ as input and 5--20\% as output gives
\[
C = \frac{N_i[(1-f_c)r_i+f_c r_c]+N_o r_o}{10^6}.
\]
Here $f_c$ is the cached fraction of input. We show zero caching as a conservative
simple scenario; subscriptions, cache discounts, tool fees, and context premiums
can change the amount substantially.
\begin{center}\begin{tabular}{lrrr}\toprule
Illustrative rates per million tokens & Input USD & Output USD & Estimated USD range\\\midrule
'''
    costs=[]
    for label,ri,ro in [('Low',1,5),('Middle',2,10),('High',10,50)]:
        low=total*(.95*ri+.05*ro)/1e6;high=total*(.8*ri+.2*ro)/1e6
        costs.append(dict(label=label,input_rate=ri,output_rate=ro,low_usd=low,high_usd=high))
        tex+=f'{label} & {ri:.2f} & {ro:.2f} & {low:.2f}--{high:.2f} \\\\\n'
    tex+=r'''\bottomrule\end{tabular}\end{center}
The token split is an assumption, not a measurement. The rate scenarios span
published API price scales but do not identify the model that ran this task.
An account usage/billing export is required for an actual charge.

\section{Remote computing: scenarios rather than telemetry}
No remote GPU count, active inference time, processor power, or memory measurement
is exposed to this task. Elapsed assistant work includes local computations and
network waits, and cannot be equated to GPU active time. A rough planning envelope
is therefore parameterized by 1--8 accelerators, 10--100\% active duty, 300--1000 W
per active accelerator, and 20--160 GB memory per accelerator. These are explicitly
assumed engineering scenarios, not provider-specific measurements or inferred
model architecture. Host CPU scenarios use 1--16 active cores and 32--512 GB host
memory. Memory reservation is not the same as memory actually touched.
'''
    tex+=f"Applied to {elapsed:.2f} hours of elapsed work, these assumptions span {elapsed*.1:.2f}--{elapsed*8:.2f} GPU-hours, {elapsed*.1:.2f}--{elapsed*16:.2f} CPU-hours, 20--1280 GB accelerator memory, and 32--512 GB host memory. Accelerator energy alone spans {elapsed*.1*.3:.3f}--{elapsed*8*1:.3f} kWh. Cooling, networking, shared-server allocation, and model training are excluded. These wide ranges should not be cited as measured energy for this project.\n"
    tex+=r'''\section{Actual local execution}
The build runner samples process-tree resident memory every 0.5 s and measures
child-process user plus system CPU time. CPU-hours sum across cores; wall time
does not. Summed RSS can count shared pages more than once. Peak memory is a
sampled upper accounting measure, not an exact unique-working-set measurement.
The machine exposes 96 logical CPUs and approximately 810 GB total RAM; this
capacity is not the amount used by the calculation. The processing uses up to
16 worker processes, each with one BLAS thread. Migration is vectorized, with three workers per independent dataset
and up to nine event workers. Local GPU use is zero GPU-hours.
'''
    tex+=f"Across the instrumented build stages retained in the logs, local use totals {cpu:.3f} CPU-hours and {wall:.3f} summed stage wall-hours. The maximum sampled process-tree RSS is {peak:.3f} GB. The data directory contains {data_bytes/1e9:.3f} GB, including raw archive records. Multiple recorded builds are counted as actual repeated work, not combined into an estimate for a single rerun. Interactive development commands, the earlier installation/download commands, and final usage-document compilation are not fully included in these totals. GNU time logs for early commands are preserved separately.\n"
    tex+=r'''\begin{longtable}{lrrrr}\toprule
Stage & Wall s & CPU s & Peak tree GB & Exit\\\midrule\endhead
'''
    for run,s in records:
        tex+=f"{escape(s['name'])} & {s['wall_seconds']:.1f} & {s['cpu_seconds']:.1f} & {s['peak_tree_rss_gb']:.3f} & {s['returncode']} \\\\\n"
    early_cpu=sum(s['cpu_seconds'] for s in early)/3600
    early_wall=sum(s['wall_seconds'] for s in early)/3600
    tex+=r'\bottomrule\end{longtable}'+'\n'
    tex+=f"Separate early GNU time logs (acquisition, an earlier preprocessing run, and the historical pilot migration) add {early_cpu:.3f} CPU-hours and {early_wall:.3f} wall-hours. These commands predate the stage runner and do not overlap its recorded commands. Together the two measurement sources account for at least {cpu+early_cpu:.3f} CPU-hours; unmetered development commands make this a lower bound on all local work. GNU time's maximum RSS is not a sum across simultaneous children, so it is not substituted for the process-tree peak above.\n"
    tex+=r'''No local power meter or reliable package-energy counter was available. For a
rough 100--500 W allocated-node envelope, multiply the actual stage wall-hours
by 0.1--0.5 kW. This is a power-allocation assumption, especially on a shared
96-core machine, not a measured marginal draw. CPU time alone does not determine
energy. At an assumed electricity rate of USD 0.10--0.30/kWh:
'''
    tex+=f"the instrumented stages imply {wall*.1:.4f}--{wall*.5:.4f} kWh and USD {wall*.1*.1:.4f}--{wall*.5*.3:.4f} in electricity. Hardware amortization and archive service costs are excluded.\n"
    tex+=r'''\section{How to measure another run}
Run \texttt{bash rebuild.sh}. Each stage produces a JSON record with wall seconds,
CPU seconds, peak process-tree RSS, and return status. For a fresh numerical run,
remove generated processed/image/validation outputs while retaining the raw archive
cache, as documented in the README. Hardware power should be measured separately
with a node power meter or available energy counters. Update the agent token
snapshot only from genuine orchestration or billing telemetry; do not replace
unknown values with asserted measurements.
\end{document}
'''
    (ROOT/'usage.tex').write_text(tex)
    (ROOT/'logs/usage-summary.json').write_text(json.dumps(dict(goal_snapshot=goal,
            measured_local_cpu_hours=cpu,measured_stage_wall_hours=wall,
            peak_tree_rss_gb=peak,local_gpu_hours=0,data_gb=data_bytes/1e9,
            early_gnu_time_commands=early,accounted_cpu_hours=cpu+early_cpu,
            cost_scenarios=costs,remote_usage_measured=False,local_power_measured=False),indent=2))
    for _ in range(2):
        with (ROOT/'logs/usage-latex.log').open('w') as out:
            subprocess.run(['pdflatex','-interaction=nonstopmode','-halt-on-error','usage.tex'],cwd=ROOT,stdout=out,stderr=subprocess.STDOUT,check=True)


if __name__=='__main__':main()
