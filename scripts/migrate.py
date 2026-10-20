"""Kirchhoff diffraction stack of saved SH traces in spherical PREM.

The image is signed normalized amplitude, not a recovered velocity anomaly.
Each event/station contributes at t_pick(ref) + T(source,x)+T(x,receiver)-T(ref).
Both legs must go monotonically upward from x; no underside ray is admitted.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from geometry import angular_distance, great_circle_point
from rays import make_tables, CMB, RADIUS

ROOT=Path(__file__).resolve().parents[1]
CFG=json.loads((ROOT/'config.json').read_text())
VARIANTS=['ScS','ScS_muted','S','S_muted']


def axis(spec): return np.arange(spec[0],spec[1]+spec[2]/2,spec[2])


def load_traces(dataset):
    events=[]
    for path in sorted((ROOT/'data/processed').glob('*.npz')):
        f=np.load(path); e=json.loads(str(f['event'])); meta=json.loads(str(f['metadata']))
        if dataset=='historical' and not e['historical']: continue
        indices=[]
        for i,m in enumerate(meta):
            if dataset=='modern_same' and not e['historical']:
                a,b,c,d=CFG['same_region_bounce_bounds']
                if not (a<=m['bounce_latitude']<=b and c<=m['bounce_longitude']<=d): continue
            indices.append(i)
        if indices:
            events.append((e,[meta[i] for i in indices],f['t'],f['deconvolved'][indices]))
    return events


def mute(time,centre,half_width):
    """A symmetric raised-cosine notch, zero at the picked phase peak."""
    u=np.minimum(abs(time-centre)/half_width,1)
    return np.sin(np.pi*u/2)**2


def profiles():
    result={}
    for name,(a,b) in CFG['profiles'].items():
        delta=angular_distance(*a,*b)
        fraction=np.linspace(0,1,int(delta/0.2)+1)
        lat,lon=great_circle_point(*a,*b,fraction)
        result[name]=(lat,lon,fraction*np.deg2rad(delta)*(RADIUS-CMB))
    return result


def travel_tables(events,depths,dataset):
    # One common receiver-depth table; event depths are not rounded.
    endpoints=[0.0]+[e['depth_km'] for e,_,_,_ in events]
    distance=np.arange(0,55.0001,0.02)
    key=hashlib.sha256(np.asarray(endpoints+list(depths),dtype=float).tobytes()).hexdigest()[:16]
    path=ROOT/f'data/rays-{dataset}-{key}.npz'
    fingerprint=hashlib.sha256((ROOT/'scripts/rays.py').read_bytes()).hexdigest()
    if path.exists():
        f=np.load(path)
        if ('fingerprint' in f and str(f['fingerprint'])==fingerprint and
                np.array_equal(f['endpoints'],endpoints) and np.array_equal(f['depths'],depths)):
            return distance,f['tables']
    print('Integrating PREM ray tables for',len(endpoints),'endpoints',flush=True)
    table=make_tables(depths,endpoints,distance)
    np.savez_compressed(path,depths=depths,endpoints=endpoints,distance=distance,tables=table,fingerprint=fingerprint)
    return distance,table


def event_stack(job):
    """Checkpoint one event so a terminated job can resume without lost stacks."""
    e,metas,t,waves,source_table,receiver_table,distance,depths,flatlat,flatlon,path=job
    if path.exists():return str(path)
    shape=(4,len(depths),len(flatlat))
    event_sum=np.zeros(shape,dtype=np.float32); event_count=np.zeros(shape,dtype=np.uint16)
    sd=angular_distance(e['latitude'],e['longitude'],flatlat,flatlon)
    source_times=np.array([np.interp(sd,distance,source_table[k],left=np.nan,right=np.nan) for k in range(len(depths))])
    for meta,y in zip(metas,waves):
        rd=angular_distance(meta['station_latitude'],meta['station_longitude'],flatlat,flatlon)
        receiver_times=np.array([np.interp(rd,distance,receiver_table[k],left=np.nan,right=np.nan) for k in range(len(depths))])
        scattering_time=source_times+receiver_times
        # Measured phase times, rather than catalog origin errors, establish
        # the reference datum. Direct S and surface multiples are censored.
        suppressed=y.copy()
        suppressed*=mute(t,meta['deconvolved_S'],CFG['mute_half_width_s'])
        for name,pred in meta['multiples'].items():
            if name in ('sS','SS'):
                suppressed*=mute(t,pred+meta['deconvolved_S']-meta['predicted_S'],CFG['mute_half_width_s'])
        censored=suppressed*mute(t,meta['deconvolved_ScS'],CFG['mute_half_width_s'])
        for iv,name in enumerate(VARIANTS):
            ref='ScS' if name.startswith('ScS') else 'S'
            time=scattering_time-meta['predicted_'+ref]+meta['deconvolved_'+ref]
            valid=np.isfinite(time)&(time>=t[0])&(time<=t[-1])
            samples=np.interp(np.nan_to_num(time,nan=-1),t,censored if 'muted' in name else suppressed,left=0,right=0)
            event_sum[iv]+=np.where(valid,samples,0)
            event_count[iv]+=valid

    temporary=path.with_suffix('.tmp.npz')
    np.savez(temporary,event_sum=event_sum,event_count=event_count)
    temporary.replace(path)
    return str(path)


def calculate(dataset):
    events=load_traces(dataset)
    if not events: raise RuntimeError('No accepted traces for '+dataset)
    lat=axis(CFG['expanded_grid_latitude'] if dataset=='expanded' else CFG['grid_latitude'])
    lon=axis(CFG['expanded_grid_longitude'] if dataset=='expanded' else CFG['grid_longitude'])
    depths=axis(CFG['grid_depth_km']); xx,yy=np.meshgrid(lon,lat)
    flatlat,flatlon=yy.ravel(),xx.ravel()
    distance,tables=travel_tables(events,depths,dataset)
    shape=(4,len(depths),len(flatlat))
    total=np.zeros(shape,dtype=np.float32); hits=np.zeros(shape,dtype=np.uint16)
    event_hits=np.zeros(shape,dtype=np.uint16)
    profile_indices={}
    for name,(plat,plon,s) in profiles().items():
        i=np.clip(np.rint((plat-lat[0])/(lat[1]-lat[0])).astype(int),0,len(lat)-1)
        j=np.clip(np.rint((plon-lon[0])/(lon[1]-lon[0])).astype(int),0,len(lon)-1)
        profile_indices[name]=i*len(lon)+j
    per_event={name:[] for name in profile_indices}
    trace_catalog=[]
    cache=ROOT/'.cache/migration';cache.mkdir(parents=True,exist_ok=True)
    implementation=(ROOT/'scripts/migrate.py').read_bytes()+(ROOT/'scripts/rays.py').read_bytes()+(ROOT/'config.json').read_bytes()
    jobs=[]
    for ie,(e,metas,t,waves) in enumerate(events):
        key=hashlib.sha256(implementation+(ROOT/f"data/processed/{e['id']}.npz").read_bytes()).hexdigest()[:16]
        path=cache/f"{dataset}-{e['id']}-{key}.npz"
        jobs.append((e,metas,t,waves,tables[ie+1],tables[0],distance,depths,flatlat,flatlon,path))
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=3) as pool:
        for event,path in zip(events,pool.map(event_stack,jobs)):
            e,metas,_,_=event
            with np.load(path) as f:
                event_sum=f['event_sum'];event_count=f['event_count']
            total+=event_sum;hits+=event_count;event_hits+=event_count>0
            for name,ind in profile_indices.items():
                per_event[name].append(event_sum[:,:,ind])
            trace_catalog.extend(dict(m,event_id=e['id'],event_time=e['time'],historical=e['historical']) for m in metas)
            print(dataset,e['id'],len(metas),'traces',flush=True)
    # Report both the arithmetic mean and a hitcount-weighted mean. Weighting
    # by N(x)/max N(x) makes the latter equal sum/max N, suppressing low coverage.
    mean=np.divide(total,hits,out=np.zeros_like(total),where=hits>0)
    weighted=total/max(1,int(hits.max()))
    out=ROOT/f'data/images/{dataset}.npz';out.parent.mkdir(parents=True,exist_ok=True)
    gridshape=(4,len(depths),len(lat),len(lon))
    np.savez_compressed(out,latitude=lat,longitude=lon,depth=depths,
                        mean=mean.reshape(gridshape),weighted=weighted.reshape(gridshape),
                        hitcount=hits.reshape(gridshape),event_count=event_hits.reshape(gridshape),
                        variants=np.array(VARIANTS),n_traces=len(trace_catalog),
                        events=json.dumps([e for e,_,_,_ in events]))
    for name,(plat,plon,s) in profiles().items():
        ind=profile_indices[name]
        np.savez_compressed(out.with_name(dataset+'_profile'+name+'.npz'),latitude=plat,longitude=plon,
                distance_km=s,depth=depths,weighted=weighted[:,:,ind],mean=mean[:,:,ind],
                hitcount=hits[:,:,ind],event_count=event_hits[:,:,ind],
                per_event=np.array(per_event[name]),events=json.dumps([e for e,_,_,_ in events]))
    out.with_suffix('.traces.json').write_text(json.dumps(trace_catalog,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dataset',choices=['historical','modern_same','expanded','all'],default='all')
    args=p.parse_args()
    if args.dataset=='all':
        # Dataset-level parallelism saves minutes without changing any stack.
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=3) as pool:
            list(pool.map(calculate,['historical','modern_same','expanded']))
    else:calculate(args.dataset)
