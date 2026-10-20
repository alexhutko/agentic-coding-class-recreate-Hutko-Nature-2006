"""Numerical comparisons to quantities stated in the publication's text.

No reference plot is digitized and no reference amplitude array is available.
Peak statistics are descriptive, not blind proof of a discontinuity or slab.
"""
import json
from pathlib import Path
import numpy as np
from rays import CMB

ROOT=Path(__file__).resolve().parents[1]


def metrics(dataset):
    f=np.load(ROOT/f'data/images/{dataset}.npz')
    traces=json.loads((ROOT/f'data/images/{dataset}.traces.json').read_text())
    events={e['id']:e for e in json.loads(str(f['events']))}
    clusters={'South':0,'Central':0,'North':0}
    for trace in traces:
        latitude=events[trace['event_id']]['latitude']
        clusters['South' if latitude<=-25 else 'Central' if latitude<=-17 else 'North']+=1
    d=np.load(ROOT/f'data/images/{dataset}_double_array.npz')
    height=CMB-d['depth'];valid=(height>=100)&(height<=400)
    peaks=[]
    for ib,bin_name in enumerate(['South','North']):
        for ir,phase in enumerate(['ScS','S']):
            inds=np.flatnonzero(valid&(d['hitcount'][ib,ir]>=3))
            if not len(inds):continue
            k=inds[np.argmax(d['mean'][ib,ir,inds])]
            peaks.append(dict(bin=bin_name,reference=phase,height_km=float(height[k]),
                    amplitude=float(d['mean'][ib,ir,k]),bootstrap_low=float(d['low'][ib,ir,k]),
                    bootstrap_high=float(d['high'][ib,ir,k]),
                    positive_95_percent=bool(d['low'][ib,ir,k]>0),
                    warning='Maximum searched over 100–400 km; confidence is pointwise, not selection-adjusted.'))
    residuals=np.array([(m['deconvolved_ScS']-m['deconvolved_S'])-(m['predicted_ScS']-m['predicted_S']) for m in traces])
    lat=np.array([m['bounce_latitude'] for m in traces])
    slope=float(np.polyfit(lat,residuals,1)[0]) if len(traces)>1 else None
    index=np.argmin(abs(f['depth']-2650))
    covered=(f['hitcount'][0,index]>=20)&(f['event_count'][0,index]>=3)
    # Area is on a spherical shell at depth 2650 km, not Earth's surface.
    dl=np.deg2rad(float(f['latitude'][1]-f['latitude'][0]));do=np.deg2rad(float(f['longitude'][1]-f['longitude'][0]))
    area=(6371-2650)**2*dl*do*np.cos(np.deg2rad(f['latitude']))[:,None]
    result=dict(dataset=dataset,n_traces=len(traces),n_events=len(set(m['event_id'] for m in traces)),
                source_cluster_trace_counts=clusters,
                historical_traces=sum(m['historical'] for m in traces),
                published_n_traces=270,published_n_events=15,reference_height_ranges_km={'South':[160,190],'North':[250,290]},
                double_array_peaks=peaks,ScS_minus_S_residual_median_s=float(np.median(residuals)),
                residual_slope_s_per_latitude_deg=slope,coverage_area_km2=float(np.sum(area*covered)),
                coverage_rule='At least 20 valid trace paths from 3 events at 2650 km; illumination, not resolution.',
                fully_comparable_to_original=False,
                uncorrected_receiver_splitting_traces=sum(not m['splitting_applied'] for m in traces),
                unverified_radiation_traces=sum(not m['radiation_verified'] for m in traces))
    for phase in ['ScS','S']:
        p=[r for r in peaks if r['reference']==phase]
        if len(p)==2:
            step=p[1]['height_km']-p[0]['height_km']
            result[phase+'_descriptive_peak_offset_km']=step
            result[phase+'_offset_difference_from_published_100_km']=step-100
    return result


if __name__=='__main__':
    def membership(name):
        records=json.loads((ROOT/f'data/images/{name}.traces.json').read_text())
        return {(m['event_id'],m['id']) for m in records}
    historical=membership('historical')
    assert historical<=membership('modern_same'), 'Same-region expansion lost historical traces'
    assert historical<=membership('expanded'), 'Wider expansion lost historical traces'
    results=[metrics(x) for x in ['historical','modern_same','expanded']]
    (ROOT/'data/comparison.json').write_text(json.dumps(results,indent=2))
    print(json.dumps(results,indent=2))
