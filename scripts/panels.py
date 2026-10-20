"""Explicit panel inventory, including unsuccessful attempts, written as JSON/CSV."""
import csv
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def inventory():
    rows=[]
    def add(panel,quantity,data,plot,status,note,documentation='Hutko2006 main text and supplementary legends'):
        rows.append(dict(panel=panel,quantity=quantity,documentation=documentation,
                         parameters='config.json; report/methods.tex',data_command=data,plot_command=plot,
                         status=status,note=note))
    migrate='python scripts/migrate.py --dataset DATASET'
    plot='python scripts/plot.py --dataset DATASET'
    acquire='python scripts/acquire.py; python scripts/process.py --workers 16'
    add('1 map','Event/station locations, ScS bounce points, profiles',acquire+'; '+migrate,plot,'partially reproduced','Independent archive geometry; approximate station membership and new profile endpoints.')
    add('1 ray inset','S and ScS paths','python scripts/experiments.py --synthetics-only',plot,'partially reproduced','Independent PREM rays for an illustrative 558 km, 78 degree case. The original numerical example is unspecified, so this is an illustrative counterpart, not a verified original-case reproduction.')
    add('1 triplication inset','Sbc and Scd branch geometry','No wavefield (schematic)',plot,'schematic redrawn','Conceptual reflected/turning branches only; no calculated Scd ray or triplication amplitude.')
    add('1 waveform inset','S, Scd+Sbc and ScS waveforms','python scripts/experiments.py --synthetics-only',plot,'partially reproduced','Independent kinematic S/reflection/ScS example; refracted Scd and full reflectivity amplitudes missing.')
    for group in ['a','b']:
        for profile in ['A','B']:
            add(f'2{group} {profile}',f'Signed migration amplitude, profile {profile}; ScS '+('retained' if group=='a' else 'censored'),migrate,plot,'partially reproduced','Independent PREM reconstruction; different trace selection and missing numerical receiver corrections prevent an exact repeat.')
    for model in ['PREM','UT','UCB','CIT']:
        add('3 '+model,'ScS-reference profile A in '+model,migrate if model=='PREM' else 'No numerical model; python scripts/tomography.py documents operator',plot,
            'partially reproduced' if model=='PREM' else 'not reproduced','PREM is computed independently.' if model=='PREM' else 'Written descriptions do not specify 3-D coefficients. No author/model output substituted.')
    add('4 upper','Folded slab and phase-boundary interpretation','No dynamical model (schematic)',plot,'schematic redrawn','Imposed conceptual geometry; never counted as a reproduced model result.')
    add('4 lower','Profile A migration image',migrate,plot,'partially reproduced','Saved independently generated profile, reused explicitly.')
    add('S1 map','Geometry, mechanisms, Fresnel ellipses',acquire+'; '+migrate,plot,'partially reproduced','Geometry generated; mechanism verification comes from USGS. Original Harvard beachballs and finite-frequency ellipse omitted.')
    for ref in ['ScS','S']:
        for group in ['North','Central','South','All','hitcount']:
            add(f'S2 {ref} {group}','Clustered profile or contributing ray count',migrate,plot,'partially reproduced','Clusters split at source latitudes -17 and -25 degrees (assumed); no original picks available.')
    for part,profiles in [('a','ABCDEF'),('b','UVWXYZ')]:
        for profile in profiles:
            for variant in ['ScS retained','ScS censored','S retained','S censored']:
                add(f'S3{part} {profile} {variant}','Parallel vertical migration section',migrate,plot,'partially reproduced','Six newly specified parallel corridors; published line coordinates are not digitized.')
    for part in 'abcd':
        for profile in 'ABCDEF':
            for model in ['PREM','UT','UCB','CIT']:
                variant={'a':'ScS retained','b':'ScS censored','c':'S reference, ScS retained','d':'S reference, ScS censored'}[part]
                add(f'S4{part} {profile} {model}','Velocity-model sensitivity: '+variant,migrate if model=='PREM' else 'Unavailable 3-D coefficients',plot,
                    'partially reproduced' if model=='PREM' else 'not reproduced','PREM counterpart in S3; tomography panels have no substituted arrays.')
    for part in 'abcd':
        for height in [400,350,300,250,200,100,0]:
            add(f'S5{part} {height}km','Horizontal migration amplitude' if part in 'ab' else 'Valid ray hitcount',migrate,plot,'partially reproduced','Seven explicitly chosen heights; slice levels are assumptions where captions give no numerical list.')
    for part in 'ab':
        for group in ['South','Central','North','All']:
            for kind in ['amplitude','hitcount']:
                add(f'S6{part} {group} {kind}','Two-point synthetic migration resolution','python scripts/validate.py --points --dataset DATASET',plot,'partially reproduced',
                    'Independent two-point tests on profiles A/B with source clusters and hitcounts. Points and profile endpoints explicitly assumed; no original synthetics used.')
    add('S7a','Observed deconvolved record section',acquire,plot,'partially reproduced','1993-05-24 event supplement shows all retained traces; published example date and station subset not fully matched.')
    for part,quantity in [('b','Layered-model synthetic waveforms'),('c','Layered shear velocity profiles')]:
        add('S7'+part,quantity,'python scripts/experiments.py --synthetics-only',plot,'partially reproduced','Written 2.6% jump at 264 km, negative jump at 90 km; 0,2.6,5,10% reductions. Kinematic reflectivity, not full-wave reflectivity.')
    for panel in ['S8 model','S9a']:
        add(panel,'Shear velocity step model','python scripts/experiments.py --synthetics-only',plot,'partially reproduced','1.5% Vs step at 170/270 km above CMB on assumed PREM background; horizontal step placed at profile midpoint.')
    for panel in ['S8 waveform 1','S8 waveform 2','S8 1D waveform','S9b North','S9b Central','S9b South','S9b All','S9c North','S9c Central','S9c South','S9c All']:
        add(panel,'Axisymmetric 2.5-D full-wave synthetics or their migration','Not generated: independent full-wave solver not implemented','No plot substituted','not reproduced','Published finite-difference numerical setup and exact source functions are incomplete; ray tests do not reproduce these panels.')
    for ref in ['ScS','S']:
        for case in ['unchanged','shallower','deeper','closer','farther']:
            add(f'S10 {ref} {case}','Profile A under 40 km source perturbations','python scripts/sensitivity.py DATASET',plot,'partially reproduced','Southern-source cluster only; closer/farther defined toward independently selected profile midpoint.')
    for ref in ['ScS','S']:
        for region in ['North','South']:
            add(f'S11 {ref} {region}','One-dimensional double-array depth stack','python scripts/experiments.py --dataset DATASET',plot,'partially reproduced','Actual independent reflection-time stack; 300 event bootstraps. Geographic split fixed at 6N.')
    add('S11 map','Double-array membership map',migrate,plot,'partially reproduced','Map in Figure 1, with bin rule explicitly specified; original polygons not digitized.')
    for panel in ['S12 globe','S12 A','S12 B','S12 C']:
        add(panel,'UT2 tomography geometry and Vs cross-sections','Unavailable numerical tomography coefficients','No plot substituted','not reproduced','No independent UT2 inversion can be performed from this paper alone; published reference discussed separately.')
    return rows


if __name__=='__main__':
    rows=inventory();out=ROOT/'report';out.mkdir(exist_ok=True)
    (out/'panels.json').write_text(json.dumps(rows,indent=2))
    with (out/'panels.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
