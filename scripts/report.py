"""Generate the LaTeX report and complete per-dataset event supplements."""
import json
from pathlib import Path
import numpy as np
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'report'


def tex(s):
    replacements={'\\':r'\textbackslash{}','_':r'\_','%':r'\%','&':r'\&','#':r'\#','$':r'\$','{':r'\{','}':r'\}'}
    return ''.join(replacements.get(c,c) for c in str(s)).replace('°',r'$^\circ$').replace('–','--').replace('—','---').replace('≥',r'$\geq$').replace('δ',r'$\delta$')


PREAMBLE=r'''\documentclass[10pt]{article}
\usepackage[margin=0.75in]{geometry}
\usepackage[T1]{fontenc}
\usepackage{graphicx,amsmath,amssymb,booktabs,longtable,array,xcolor}
\usepackage[colorlinks=true,linkcolor=blue,urlcolor=blue]{hyperref}
\setlength{\parskip}{5pt}
\setlength{\parindent}{0pt}
\setlength{\emergencystretch}{2em}
\newcommand{\Dpp}{D$^{\prime\prime}$}
\begin{document}
'''


def figure(path,caption,width='.96',height=None):
    opts=f'width={width}\\linewidth'
    if height:opts+=f',height={height}\\textheight,keepaspectratio'
    return '\\begin{figure}[p]\\centering\n\\includegraphics['+opts+']{'+path+'}\n\\caption{'+caption+'}\\end{figure}\n'


def supplements(events,comparisons):
    for dataset in ['historical','modern_same','expanded']:
        records=json.loads((ROOT/f'data/images/{dataset}.traces.json').read_text())
        subset=[e for e in events if dataset!='historical' or e['historical']]
        counts={e['id']:sum(m['event_id']==e['id'] for m in records) for e in subset}
        body=PREAMBLE.replace('[margin=0.75in]','[landscape,margin=0.55in]')+'\\title{Event and waveform supplement: '+tex(dataset)+'}\\author{Independent archive reanalysis}\\date{13 October 2026}\\maketitle\n'
        body+=r'''Each event below is a USGS catalog record. Counts refer to traces actually
used in this dataset's images, not all downloaded stations. An asterisk flags a
historical catalog value outside the published magnitude/depth bounds. Both
processed displacement and processed plus source-deconvolved waveforms are shown
for every used trace. Event pages with zero used traces give rejection summaries.
Records retain at least 80 s before S and 65 s after ScS so noise can be assessed.
The blue vertical line marks ScS; red dots mark S. The displacement and deconvolved
curves are each normalized to their own S peak. Display clipping at twice that
amplitude does not alter stored data. SNR is a peak-to-pre-S-RMS ratio.
Receiver splitting corrections have not been applied because the complete original station/path
correction set was not recovered. Phase selection is automatic and requires expert review.
\begingroup\small\setlength{\tabcolsep}{3pt}
\begin{longtable}{llllrrr}
\toprule USGS ID & UTC date/time & Latitude & Longitude & Depth km & Mag/type & Used\\\midrule\endhead
'''
        for e in subset:
            body+=f"{tex(e['id'])}{'*' if e['catalog_exception'] else ''} & {e['time'][:10]} {e['time'][11:19]} & {e['latitude']:.3f} & {e['longitude']:.3f} & {e['depth_km']:.1f} & {e['magnitude']:.1f}/{tex(e['magnitude_type'])} & {counts[e['id']]} \\\\\n"
        body+=r'\bottomrule\end{longtable}\endgroup'+'\n'
        if dataset=='historical':
            body+=r'The printed historical date 1999-08-30 is inferred to mean 1998-08-30: USGS event usp0008u3b matches the printed latitude and longitude exactly and its depth within 0.5 km. The year correction is an explicit identification assumption; its preferred magnitude of 5.7 is flagged as a historical catalog exception.'+'\n'
        for e in subset:
            path=f'figures/{dataset}/events/{e["id"]}.pdf'
            n=len(PdfReader(ROOT/path).pages)
            for page in range(1,n+1):
                body+='\\clearpage\\noindent\\textbf{'+tex(e['id'])+': '+str(counts[e['id']])+' used traces; page '+str(page)+'/'+str(n)+'}\\par\n'
                body+='\\includegraphics[page='+str(page)+',width=\\linewidth,height=.91\\textheight,keepaspectratio]{'+path+'}\n'
        body+='\\end{document}\n'
        (OUT/f'supplement-{dataset}.tex').write_text(body)


def main():
    comparisons=json.loads((ROOT/'data/comparison.json').read_text())
    checks=json.loads((ROOT/'data/validation/checks.json').read_text())
    panels=json.loads((OUT/'panels.json').read_text())
    events=json.loads((ROOT/'data/events.json').read_text())
    body=PREAMBLE+r'''\title{Independent diffraction-stack reanalysis of the Cocos Plate lowermost mantle}
\author{Python implementation and public-archive reconstruction of Hutko et al. (2006)}
\date{13 October 2026}\maketitle
\begin{abstract}
We implement spherical single-scattering migration of transverse S--ScS waveforms
and repeat it with historical and later public-archive observations. Event information
comes from USGS; station responses and waveforms come from EarthScope, NCEDC, and
SCEDC. The reconstruction produces independent numerical images but does not
establish a repeat of the published 100 km discontinuity step. Differences in
event and station membership, phase selection, and unavailable receiver splitting
corrections limit comparison. PREM migration, two reference phases, phase censorship,
source deconvolution, double-array stacks, and point/source-location tests are
implemented. Three-dimensional tomography corrections and published full-wave
synthetic panels remain incomplete. We distinguish calculations from interpretations
and give a panel-level record of both successful computations and failed attempts.
\end{abstract}
\section{Scope and principal results}
The main publication is \href{https://doi.org/10.1038/nature04757}{Hutko et al. (2006),
Nature 441, 333--336}. The four comparison sets are (1) the published reference,
(2) independently processed historical observations, (3) an expanded event set
in the same Cocos imaging region, and (4) expanded observations and a wider image
domain. The published reference is visually distinguished from generated results;
it contributes no amplitudes, model grid values, or digitized input data.

\begin{center}\begin{tabular}{lrrrr}\toprule
Dataset & Used events & Used traces & Historical traces & Covered area (km$^2$)\\\midrule
Published & 15 & 270 & 270 & not tabulated\\
'''
    for c in comparisons:
        body+=f"{tex(c['dataset'])} & {c['n_events']} & {c['n_traces']} & {c['historical_traces']} & {c['coverage_area_km2']:.0f} \\\\\n"
    body+=r'''\bottomrule\end{tabular}\end{center}
Covered area is measured on the spherical shell at 2650 km depth, using at least
20 valid paths from three events. It is an illumination measure. Limited azimuthal
coverage can still produce broad migration smiles even where this count is high.
The expanded same-region subset includes every retained historical observation;
its bounce-point bounds apply only to newly added observations; the wider subset retains all accepted paths. Both use the
same magnitude, depth, distance, filtering, and automated quality criteria.
The historical source clusters contain 4 southern, 53 central, and 23 northern
traces under our stated latitude-bin assumption, compared with the published
54, 180, and 36. Southern illumination is especially depleted. Consequently,
failure to recover the step in this reconstruction is not a falsification of
the published interpretation with its more complete, differently processed data.

The publication reports an approximately 100 km vertical offset, a southeast
reflector 160--190 km above the CMB, and a northwest reflector 250--290 km above
the CMB. We compare those written scales with independently calculated stacks.
We do not infer agreement from using a similar colour scale. The automated peaks
below are maxima searched over 100--400 km height and may represent sidelobes or
noise. They are not estimates of a slab boundary unless their waveform coherence,
location, and uncertainty warrant that interpretation.
The published display extends above a weighted stack value of 17. Our display
uses a sum divided by the maximum hitcount, with colour saturation at 0.15.
The written specification does not uniquely define the original weight
normalization, so these amplitude scales are not directly comparable. We retain
both mean amplitude and hitcounts to make alternative normalizations explicit.
\begin{center}\begin{tabular}{llrrrr}\toprule
Dataset & Reference & South peak km & North peak km & Offset km & Offset minus 100 km\\\midrule
'''
    for c in comparisons:
        for ref in ['ScS','S']:
            peaks={p['bin']:p for p in c['double_array_peaks'] if p['reference']==ref}
            if len(peaks)==2:
                step=peaks['North']['height_km']-peaks['South']['height_km']
                body+=f"{tex(c['dataset'])} & {ref} & {peaks['South']['height_km']:.0f} & {peaks['North']['height_km']:.0f} & {step:.0f} & {step-100:.0f} \\\\\n"
    body+=r'\bottomrule\end{tabular}\end{center}'+'\n'
    peaks=[p for c in comparisons for p in c['double_array_peaks']]
    positive=sum(p['positive_95_percent'] for p in peaks)
    body+=f"Only {positive} of {len(peaks)} selected maxima have a positive lower pointwise 95\\% event-bootstrap bound. Several maxima lie at 391 km, near the upper edge of the search interval. The historical S-reference offset of roughly 90 km is therefore not evidence that the published 100 km step has been reproduced: it is reference-dependent and lacks a positively resolved peak pair.\n"
    body+='The median measured minus PREM ScS--S residuals are '+', '.join(tex(c['dataset'])+f" {c['ScS_minus_S_residual_median_s']:.2f} s" for c in comparisons)+'. The fitted residual-versus-bounce-latitude slopes are '+', '.join(tex(c['dataset'])+f" {c['residual_slope_s_per_latitude_deg']:.3f} s/degree" for c in comparisons)+r'''. These fits describe this accepted sample; they do not isolate lower-mantle velocity from phase-picking and path effects.

\input{report/methods.tex}
\section{Validation and numerical efficiency}
'''
    body+=f"Across nine source-depth/distance cases, independently integrated ScS times differ from TauP by at most {checks['max_taup_error_s']:.5f} s. A homogeneous spherical-shell test has maximum travel-time error {checks['constant_shell_time_error_s']:.5f} s and angular error {checks['constant_shell_angle_error_deg']:.6f} degrees, including nearly grazing rays. The zero-distance integral differs from independent radial quadrature by {checks['radial_error_s']:.2e} s.\n"
    body+=f"A known negative impulse of amplitude -0.3 relative to a positive impulse is recovered with ratio {checks['deconvolution_amplitude_ratio']:.5f}; both peak times agree within one 0.2 s sample. Zero input remains zero. A splitting correction followed by its inverse has relative error {checks['splitting_round_trip_error']:.2e} for the chosen integer-shift test. The tomography segment operator gives the expected -0.3 s perturbation for a 1\% anomaly over 30 s reference travel time.\n"
    body+=r'''These checks validate units, signs, elementary timing, and indexing. They do not
validate automatic picks on interfering real phases or the omitted receiver
corrections. The point-scatterer test uses the same kinematics for synthesis and
migration, so it is an operator/illumination check rather than independent
validation of the Born approximation. The initial near-grazing quadrature failed
the homogeneous-shell test; the final variable transformation and 16-point rule
resolve that failure. All validation assertions are rerun by the rebuild command.

Runtime improvements are confined to substantial costs: six concurrent archive
requests, event-level preprocessing workers, vectorized radial quadrature,
travel-time tables, parallel independent datasets/events, restartable event checkpoints,
and reuse of response and waveform downloads. Plain functions
and NumPy arrays keep the seismological calculations readable. No GPU is used.
The separate \texttt{usage.pdf} reports measured local CPU time, wall time, and
process-tree memory alongside explicit assumptions for unobserved remote usage.
An earlier long foreground build was terminated by the execution environment
(exit 143) during the wider migration. Event checkpoints and event-level
parallelism were then added. The historical and same-region weighted amplitudes,
means, trace counts, and event counts were bit-for-bit identical to the saved
serial results before the final dataset-membership correction (\texttt{logs/parallel-consistency.json}). The final documented
rebuild reruns numerical checks and figure generation before compiling the PDFs;
its stage outcomes are retained in \texttt{logs/latest-run.json}. A final membership
audit found that the same-region filter had excluded six historical traces. The
filter was corrected to retain the entire historical subset, then that dataset
and its figures were regenerated.

\section{Figures and comparison with the published reference}
The generated sections have no vertical exaggeration and retain signed amplitudes.
White regions fail the stated coverage threshold. Sidelobes and broad negative
regions should not be interpreted automatically as low-velocity material. The
receiver-correction omission, altered source wavelets, and strict use of current
USGS radiation coefficients remove some originally contributing paths and can
change the balance between northern and southern illumination. A failed or
unstable peak is retained as a failed comparison, not replaced by a synthetic
reflector. The four figure sets follow; published panels are reference images
only and are not counted as reproduced results.
'''
    # Published figures are included directly from the paper PDF for comparison,
    # in bordered boxes. No extraction file feeds any calculation.
    body+=r'''\clearpage\subsection*{Set 1: published reference only}
The definitive original panels and captions are at
\url{https://www.nature.com/articles/nature04757}. The reference plate below is
cropped from the published PDF solely for visual comparison. It is not generated
by this implementation. Copyright Nature Publishing Group (2006).
\begin{figure}[p]\centering
\fcolorbox{red}{white}{\includegraphics[page=2,trim=55 145 345 305,clip,width=.46\linewidth]{references/hutko2006.pdf}}
\fcolorbox{red}{white}{\includegraphics[page=2,trim=320 105 80 350,clip,width=.46\linewidth]{references/hutko2006.pdf}}
\caption{PUBLISHED REFERENCE ONLY: manuscript Figures 2 and 3. Red borders distinguish published images from every computed image in this report. Neither image supplies numerical input.}
\end{figure}
\begin{figure}[p]\centering
\fcolorbox{red}{white}{\includegraphics[page=1,trim=320 155 65 400,clip,width=.46\linewidth]{references/hutko2006.pdf}}
\fcolorbox{red}{white}{\includegraphics[page=3,trim=330 115 75 450,clip,width=.46\linewidth]{references/hutko2006.pdf}}
\caption{PUBLISHED REFERENCE ONLY: manuscript Figures 1 and 4. Figure 4 includes an interpretive slab schematic. These red-bordered published panels are visually distinct from the three independently generated dataset series.}
\end{figure}
'''
    for i,dataset in enumerate(['historical','modern_same','expanded'],2):
        body+='\\clearpage\\subsection*{Set '+str(i)+': '+tex(dataset)+'}\n'
        if dataset=='expanded':
            body+='The wider calculation covers 10 degrees S--25 degrees N and 110--70 degrees W. Profiles A and B are retained for direct comparison; the horizontal slices in supplementary Figure 5 show the additional imaged region, with the same coverage threshold.\n'
        for number in range(1,5):
            caption={1:'Independently retrieved event and station geometry and calculated ScS bounce points. The two selected section directions are shown. Coastlines are Natural Earth geographic context.',
                     2:'Independent PREM migration. Top: ScS retained; bottom: ScS censored. Left: profile A; right: profile B. Both use ScS as reference and suppress S. Colour is the signed S-normalized stack weighted by relative hitcount, saturated at plus/minus 0.15. White regions fail the 20-trace/three-event display rule.',
                     3:'Velocity-model comparison attempt. Only PREM is calculated. Blank, explicitly labelled UT, UCB and CIT panels identify unreproduced results; they are not filled with surrogate models.',
                     4:'Upper: an explicitly labelled conceptual schematic, with an imposed step and no calculated flow or temperature field. Lower: the independent observational profile A. The schematic is not evidence for a fold.'}[number]
            body+=figure(f'figures/{dataset}/figure{number}.pdf',tex(dataset)+f'; manuscript Figure {number} counterpart: '+caption)
    body+='\\clearpage\\section{Supplementary calculations}\n'
    body+=figure('figures/validation.pdf','Synthetic deconvolution consistency test. The input consists of two known signed impulses convolved with the displayed wavelet. This is a validation signal, not Earth data.')
    body+=figure('figures/figure1-rays.pdf','Independently calculated S and ScS paths for a 558 km source at 78 degrees. This is a numerical ray diagram; the publication does not specify the exact illustrative source used in its inset.')
    body+=figure('figures/figure1-triplication-schematic.pdf','Redrawn conceptual companion to the Figure 1 triplication inset. The curves only distinguish reflection above the jump from turning below it. They do not satisfy a calculated ray equation and are not reproduced numerical results.')
    body+=figure('figures/supplement7bc.pdf','Partial attempt at supplementary Figure 7b,c: local SH reflection coefficients and explicitly assumed layered velocity profiles. There is no refracted Scd branch or full-wave reflectivity calculation; these curves cannot reproduce the published triplication amplitudes.')
    body+=figure('figures/step-model.pdf','Numerical input-model illustration for supplementary Figures 8 and 9a. The stated 170/270 km heights and 1.5 percent jump are imposed on PREM. No full-wave propagation has been performed.')
    for dataset in ['historical','modern_same','expanded']:
        for stem in ['supplement2','supplement3a','supplement3b','supplement5','supplement6','supplement10','supplement11']:
            body+=figure(f'figures/{dataset}/{stem}.pdf',tex(dataset)+'; independent '+stem.replace('supplement','supplementary figure ')+' counterpart. Definitions, assumptions, and panel status are given in the panel record. All numerical values come from saved arrays.',height='.87')
    body+=r'''\clearpage\section{Panel-by-panel provenance and status}
The complete machine-readable records are \texttt{report/panels.csv} and
\texttt{report/panels.json}. Every row gives its quantity, documentation,
parameters, data command, plot command, status, and limitation. The listing below
includes every identified main and supplementary subpanel. The same status applies
to each of the three generated dataset series unless a row explicitly names
a separate schematic or unavailable calculation. Point-source resolution and
source-location sensitivity are recomputed for each dataset geometry. In command strings,
\texttt{DATASET} means \texttt{historical}, \texttt{modern\_same}, or
\texttt{expanded}. Parameters are fixed in \texttt{config.json} and described
in the methods; no image-based tuning is used. ``Partially reproduced'' means
independently generated but incomplete in inputs, method, or comparison, not a
copied or digitized result. ``Not reproduced'' has no substituted numerical plot.

Command key (run from the project root):
\begin{center}\begin{tabular}{ll}
A & \texttt{python scripts/acquire.py}\\
  & \texttt{python scripts/process.py --workers 16}\\
M & \texttt{python scripts/migrate.py --dataset DATASET}\\
E & \texttt{python scripts/experiments.py --dataset DATASET}\\
V & \texttt{python scripts/validate.py --points --dataset DATASET}\\
L & \texttt{python scripts/sensitivity.py DATASET}\\
P & \texttt{python scripts/plot.py --dataset DATASET}\\
\end{tabular}\end{center}
 All E-only input-model and
ray examples can be generated with \texttt{--synthetics-only}. Rows sharing
a command still have separate entries in the accompanying complete CSV.
\small
\begin{longtable}{p{.23\linewidth}p{.25\linewidth}p{.19\linewidth}p{.22\linewidth}}
\toprule Panel & Quantity & Status & Data / plot commands\\\midrule\endhead
'''
    for r in panels:
        command=r['data_command']
        if 'migrate.py' in command:key='A, M / P'
        elif 'acquire.py' in command:key='A / P'
        elif 'experiments.py' in command:key='E / P'
        elif 'validate.py' in command:key='V / P'
        elif 'sensitivity.py' in command:key='L / P'
        elif r['status']=='schematic redrawn':key='schematic / P'
        else:key='unavailable / no substitute'
        body+=tex(r['panel'])+' & '+tex(r['quantity'])+' & '+tex(r['status'])+' & '+tex(key)+r' \\'+'\n'
    body+=r'''\bottomrule\end{longtable}\normalsize
The ledger documentation is Hutko et al.'s main text and supplementary captions,
with the processing papers cited above. Important family-specific differences
are: independently selected parallel profile coordinates in S3/S4; assumed slice
heights in S5; assumed point coordinates and profile endpoints in S6; incomplete station
matching in S7a; no 2.5-D waveform solver in S8/S9; and no UT2 numerical tomography
in S12. PREM S4 counterparts are displayed in S3 rather than duplicated under
four different model headings. The full per-row explanatory notes are in the CSV.

\section{Rebuilding, availability, and interpretation}
From the project root, run \texttt{bash scripts/bootstrap.sh} once, then
\texttt{bash rebuild.sh --online}. With the downloaded archive cache present,
\texttt{bash rebuild.sh} runs without acquisition. Both procedures regenerate
numerical figures and compile this report plus one event supplement per dataset.
The build exits on a failed validation or LaTeX command. Execution logs and
resource measurements are in \texttt{logs/}. The \texttt{README.md} documents
fresh-output removal, file formats, exclusions, and publication commands.

The calculations do not independently establish the published step or the folded
slab interpretation. The retained signal population and omitted receiver corrections
are sufficient reasons to expect differences, but do not prove which discrepancy
dominates. A stronger reconstruction requires confirming the inferred historical
event membership, recovering station-specific splitting values, and verifying phase
and wavelet selections, followed by full-wave tests. Expanded sampling adds useful
observations but does not by itself remove these systematic uncertainties.

\section*{References}
Hutko, A. R., Lay, T., Garnero, E. J., and Revenaugh, J. (2006).
Seismic detection of folded, subducted lithosphere at the core--mantle boundary.
Nature 441, 333--336. \url{https://doi.org/10.1038/nature04757}.

Lay, T., Garnero, E. J., and Russell, S. A. (2004). Lateral variation of the
D$^{\prime\prime}$ discontinuity beneath the Cocos Plate.
\url{https://doi.org/10.1029/2004GL020300}.

Thomas, C., Garnero, E. J., and Lay, T. (2004). High-resolution imaging of lowermost
mantle structure under the Cocos plate. \url{https://doi.org/10.1029/2004JB003013}.

Avants, M., Lay, T., Russell, S. A., and Garnero, E. J. (2006). Shear velocity
variation within the D$^{\prime\prime}$ region beneath the central Pacific.
\url{https://doi.org/10.1029/2004JB003270}.

Avants, M., Lay, T., and Garnero, E. J. (2006). A new probe of ULVZ S-wave
velocity structure: Array stacking of ScS waveforms.
\url{https://doi.org/10.1029/2005GL024989}.

Polet, J., and Kanamori, H. (2002). Anisotropy beneath California: shear wave
splitting measurements using a dense broadband array.
\url{https://doi.org/10.1046/j.1365-246X.2002.01630.x}.

Dziewonski, A. M., and Anderson, D. L. (1981). Preliminary reference Earth model.
Physics of the Earth and Planetary Interiors 25, 297--356.
\url{https://doi.org/10.1016/0031-9201(81)90046-7}.
\end{document}
'''
    (OUT/'report.tex').write_text(body)
    supplements(events,comparisons)


if __name__=='__main__':main()
