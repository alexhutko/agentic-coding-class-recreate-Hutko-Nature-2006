"""Independent limiting cases and synthetic point-scatterer resolution tests."""
import json
from pathlib import Path
import sys
import numpy as np
from scipy.signal import fftconvolve
from obspy.taup import TauPyModel
from geometry import angular_distance
from rays import reflection_time,leg_curves,CMB,velocity
from process import deconvolve,undo_splitting,CFG

ROOT=Path(__file__).resolve().parents[1]


def checks():
    model=TauPyModel('prem'); travel=[]
    for h in [218,400,610]:
        for d in [65,75,85]:
            ours=reflection_time(CMB,h,d)
            taup=model.get_travel_times(h,d,['ScS'])[0].time
            travel.append(dict(depth_km=h,distance_deg=d,ours_s=ours,taup_s=taup,error_s=ours-taup))
    p,curves=leg_curves(2650,[0,218])
    for angle,time in curves:
        assert np.all(np.diff(angle)>0) and np.all(np.diff(time)>0)
    assert max(abs(r['error_s']) for r in travel)<0.02
    # A zero-distance radial ray integrates dz / Vs independently of p sampling.
    from scipy.integrate import quad
    integral=quad(lambda z:1/float(velocity(z)),218,2650,points=[400,670,2200],limit=500)[0]
    assert abs(curves[1][1][0]-integral)<0.01
    # Closed-form straight chords in a constant-velocity spherical shell.
    pc,cc=leg_curves(2650,[0],constant_speed=7.0)
    b=pc*7;rt=6371-2650
    exact_t=(np.sqrt(6371**2-b*b)-np.sqrt(rt**2-b*b))/7
    exact_a=np.rad2deg(np.arccos(b/6371)-np.arccos(b/rt))
    constant_time_error=float(np.max(abs(exact_t-cc[0][1])))
    constant_angle_error=float(np.max(abs(exact_a-cc[0][0])))
    assert constant_time_error<.02 and constant_angle_error<.002
    from tomography import perturbation
    assert np.isclose(perturbation(np.array([10.,20.]),np.array([.01,.01])),-.3)
    dt=0.2;t=np.arange(0,160,dt); st=np.arange(-8,8+dt/2,dt)
    source=np.exp(-st**2/2)
    spikes=np.zeros_like(t);spikes[150]=1;spikes[400]=-.3
    signal=fftconvolve(spikes,source,mode='full')[len(st)//2:len(st)//2+len(t)]
    recovered=deconvolve(signal,source,len(st)//2,dt,1e-4)
    peak1=np.argmax(recovered);peak2=np.argmin(recovered)
    assert abs(peak1-150)<=1 and abs(peak2-400)<=1
    ratio=recovered[peak2]/recovered[peak1]
    assert abs(ratio+.3)<0.01
    zero=deconvolve(np.zeros_like(t),source,len(st)//2,dt,1e-4)
    assert np.max(abs(zero))==0
    n,e=undo_splitting(signal,0*signal,dt,90,0)
    assert np.allclose(n,signal) and np.allclose(e,0)
    n1,e1=undo_splitting(signal,.3*signal,dt,40,1.2)
    n2,e2=undo_splitting(n1,e1,dt,40,-1.2)
    splitting_error=np.linalg.norm(n2-signal)/np.linalg.norm(signal)
    assert splitting_error<0.03
    directory=ROOT/'data/validation';directory.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(directory/'deconvolution.npz',time=t,input=signal,output=recovered,
                        source_time=st,source=source,spikes=spikes)
    result=dict(travel_times=travel,radial_error_s=float(curves[1][1][0]-integral),
                deconvolution_amplitude_ratio=float(ratio),splitting_round_trip_error=float(splitting_error),
                max_taup_error_s=max(abs(r['error_s']) for r in travel),
                constant_shell_time_error_s=constant_time_error,
                constant_shell_angle_error_deg=constant_angle_error,passed=True)
    (directory/'checks.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2),flush=True)


def point_test(dataset):
    """Born impulse test on actual dataset geometry; no observed amplitudes.

    Assumed points at 40% and 70% along our profile A, depths 2611 and 2711 km,
    giving 100 km vertical separation. Endpoints are independently specified.
    Gaussian pulse width 1s is a test signal, not an earthquake model.
    """
    from migrate import load_traces,profiles,axis
    from rays import make_tables
    events=load_traces(dataset)
    if not events:return
    depths=axis(CFG['grid_depth_km'])
    from geometry import great_circle_point
    a,b=CFG['profiles']['A']
    point_lat,point_lon=great_circle_point(*a,*b,np.array([.4,.7]))
    points=np.column_stack([point_lat,point_lon,[2611,2711]])
    da=np.arange(0,55.0001,.02)
    endpoints=[0]+[e['depth_km'] for e,_,_,_ in events]
    tables=make_tables(depths,endpoints,da)
    ptables=make_tables(points[:,2],endpoints,da)
    saved={'depth':depths,'points':points,
           'event_latitude':np.array([e['latitude'] for e,_,_,_ in events])}
    for name,(plat,plon,s) in profiles().items():
        source_images=[];source_counts=[]
        for ie,(e,meta,_,_) in enumerate(events):
            subtotal=np.zeros((len(depths),len(plat)));counts=np.zeros_like(subtotal)
            ds=angular_distance(e['latitude'],e['longitude'],plat,plon)
            ts=np.array([np.interp(ds,da,tables[ie+1,k],right=np.nan) for k in range(len(depths))])
            for m in meta:
                dr=angular_distance(m['station_latitude'],m['station_longitude'],plat,plon)
                tr=np.array([np.interp(dr,da,tables[0,k],right=np.nan) for k in range(len(depths))])
                time=ts+tr
                valid=np.isfinite(time)
                for ip,(la,lo,z) in enumerate(points):
                    sdist=angular_distance(e['latitude'],e['longitude'],la,lo)
                    rdist=angular_distance(m['station_latitude'],m['station_longitude'],la,lo)
                    arrival=np.interp(sdist,da,ptables[ie+1,ip],right=np.nan)+np.interp(rdist,da,ptables[0,ip],right=np.nan)
                    if np.isfinite(arrival):subtotal+=np.where(valid,np.exp(-.5*(time-arrival)**2),0)
                counts+=valid
            source_images.append(subtotal);source_counts.append(counts)
        saved.update({name+'_distance_km':s,name+'_latitude':plat,name+'_longitude':plon,
                      name+'_per_event':np.array(source_images),name+'_counts':np.array(source_counts)})
    # Preserve aggregate A keys for the quantitative validation summary.
    counts=saved['A_counts'].sum(axis=0)
    saved.update(distance_km=saved['A_distance_km'],latitude=saved['A_latitude'],
                 longitude=saved['A_longitude'],hitcount=counts,
                 image=saved['A_per_event'].sum(axis=0)/max(1,counts.max()))
    name='points.npz' if dataset=='historical' else f'points_{dataset}.npz'
    np.savez_compressed(ROOT/'data/validation'/name,**saved)



if __name__=='__main__':
    import argparse
    from concurrent.futures import ProcessPoolExecutor
    parser=argparse.ArgumentParser()
    parser.add_argument('--points',action='store_true')
    parser.add_argument('--dataset',choices=['historical','modern_same','expanded','all'],default='all')
    args=parser.parse_args();checks()
    if args.points:
        names=['historical','modern_same','expanded'] if args.dataset=='all' else [args.dataset]
        with ProcessPoolExecutor(max_workers=min(3,len(names))) as pool:
            list(pool.map(point_test,names))
