"""Additional numerical tests corresponding to documented supplements.

No synthetic is substituted for an observation. Simplified ray/Born tests are
saved separately and explicitly fall short of the published finite differences.
"""
import json
from pathlib import Path
import numpy as np
from obspy.taup import TauPyModel
from rays import CMB,leg_curves,velocity
from migrate import load_traces,axis,CFG,mute

ROOT=Path(__file__).resolve().parents[1]


def double_array(dataset):
    events=load_traces(dataset);depth=axis(CFG['grid_depth_km'])
    sums=np.zeros((len(events),2,2,len(depth)));counts=np.zeros_like(sums)
    for iz,z in enumerate(depth):
        _,curves=leg_curves(z,[0]+[e['depth_km'] for e,_,_,_ in events])
        for ie,(e,metas,t,waves) in enumerate(events):
            angle=curves[0][0]+curves[ie+1][0];time=curves[0][1]+curves[ie+1][1]
            for m,y in zip(metas,waves):
                tt=np.interp(m['distance_deg'],angle,time,left=np.nan,right=np.nan)
                if not np.isfinite(tt):continue
                ib=int(m['bounce_latitude']>=6)
                for ir,ref in enumerate(['ScS','S']):
                    sample=tt-m['predicted_'+ref]+m['deconvolved_'+ref]
                    if not t[0]<=sample<=t[-1]:continue
                    value=np.interp(sample,t,y)*mute(sample,m['deconvolved_S'],CFG['mute_half_width_s'])
                    sums[ie,ib,ir,iz]+=value;counts[ie,ib,ir,iz]+=1
    total=counts.sum(axis=0)
    mean=np.divide(sums.sum(axis=0),total,out=np.zeros_like(total),where=total>0)
    rng=np.random.default_rng(2006);bootstrap=[]
    for _ in range(300):
        ids=rng.integers(0,len(events),len(events));n=counts[ids].sum(axis=0)
        bootstrap.append(np.divide(sums[ids].sum(axis=0),n,out=np.full_like(n,np.nan),where=n>0))
    with np.errstate(all='ignore'):
        low,high=np.nanpercentile(bootstrap,[2.5,97.5],axis=0)
    np.savez_compressed(ROOT/f'data/images/{dataset}_double_array.npz',depth=depth,
                        mean=mean,low=low,high=high,hitcount=total,event_sums=sums,event_counts=counts)


def ray_synthetics():
    # Explicitly assumed 1-D impedance perturbations from the written legend.
    # This kinematic SH calculation has no refracted Scd branch or caustic
    # amplitude regularization, so is a partial attempt at S7b and Fig1 inset.
    model=TauPyModel('prem');source_depth=558.;distance=78.
    arrivals=model.get_ray_paths(source_depth,distance,['S','ScS'])
    phases={a.name:a for a in arrivals}
    t=np.arange(phases['S'].time-15,phases['ScS'].time+30,.1)
    gaussian=lambda centre:np.exp(-.5*((t-centre)/1.0)**2)
    z=np.arange(2310,2891.1,1)
    reductions=[0,.026,.05,.10]
    synthetics=[];models=[];table=[]
    for drop in reductions:
        v=velocity(z)*(1+.026*(z>=CMB-264))
        v*=1-drop*(z>=CMB-90)
        models.append(v)
        signal=gaussian(phases['S'].time)+.7*gaussian(phases['ScS'].time)
        for target,contrast in [(CMB-264,.026),(CMB-90,-drop)]:
            p,c=leg_curves(target,[source_depth,0]);theta=c[0][0]+c[1][0]
            travel=c[0][1]+c[1][1]
            time=float(np.interp(distance,theta,travel,left=np.nan,right=np.nan))
            rayp=float(np.interp(distance,theta,p))
            v1=float(velocity(target));v2=v1*(1+contrast)
            horizontal=rayp/(6371-target)
            q1=np.sqrt(complex(1/v1**2-horizontal**2));q2=np.sqrt(complex(1/v2**2-horizontal**2))
            # Displacement reflection coefficient from continuity of displacement
            # and shear traction. Increasing impedance gives a negative
            # precritical coefficient; this is NOT the positive refracted Scd.
            reflection=(v1*v1*q1-v2*v2*q2)/(v2*v2*q2+v1*v1*q1)
            from scipy.signal import hilbert
            pulse=gaussian(time)
            signal+=np.real(reflection)*pulse-np.imag(reflection)*np.imag(hilbert(pulse))
            table.append(dict(drop=drop,target_depth_km=target,time_s=time,coefficient_real=reflection.real,coefficient_imag=reflection.imag))
        synthetics.append(signal)
    out=ROOT/'data/validation';out.mkdir(exist_ok=True)
    np.savez_compressed(out/'ray_synthetics.npz',time=t-phases['S'].time,waves=synthetics,
                        depth=z,velocities=models,reductions=reductions,
                        ray_S_depth=phases['S'].path['depth'],ray_S_distance=phases['S'].path['dist'],
                        ray_ScS_depth=phases['ScS'].path['depth'],ray_ScS_distance=phases['ScS'].path['dist'])
    (out/'ray_synthetic_parameters.json').write_text(json.dumps(table,indent=2))
    distance_axis=np.linspace(0,1700,171)
    depths=np.arange(2310,2892,2)
    height=np.where(distance_axis<850,270,170)
    vs=velocity(depths)[:,None]*(1+.015*(depths[:,None]>=CMB-height[None,:]))
    np.savez_compressed(out/'step_model.npz',distance_km=distance_axis,depth=depths,velocity=vs,
                        discontinuity_height_km=height,velocity_jump=.015)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--dataset',default='all');p.add_argument('--synthetics-only',action='store_true')
    a=p.parse_args();ray_synthetics()
    if not a.synthetics_only:
        for name in (['historical','modern_same','expanded'] if a.dataset=='all' else [a.dataset]):
            print('Double array:',name,flush=True);double_array(name)
