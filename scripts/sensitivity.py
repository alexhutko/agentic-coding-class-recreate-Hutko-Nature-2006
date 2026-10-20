"""Source-location perturbations on profile A (Supplementary Figure 10)."""
import json
from pathlib import Path
import numpy as np
from obspy.taup import TauPyModel
from geometry import angular_distance,great_circle_point
from rays import make_tables,CMB,RADIUS
from migrate import load_traces,profiles,axis,CFG,mute

ROOT=Path(__file__).resolve().parents[1]


def calculate(dataset):
    events=load_traces(dataset);lat,lon,distance=profiles()['A'];depth=axis(CFG['grid_depth_km'])
    cases=['unchanged','40 km shallower','40 km deeper','40 km closer','40 km farther']
    values=np.zeros((5,2,len(depth),len(lat)));counts=np.zeros_like(values)
    endpoints=[0]+[e['depth_km'] for e,_,_,_ in events]+[e['depth_km']+shift for shift in [-40,40] for e,_,_,_ in events]
    da=np.arange(0,55.0001,.02);tables=make_tables(depth,endpoints,da);taup=TauPyModel('prem')
    centre_lat=float(np.mean(lat));centre_lon=float(np.mean(lon))
    for ie,(e,meta,t,waves) in enumerate(events):
        south=e['latitude']<=-25
        for ic,case in enumerate(cases):
            h=e['depth_km'];la=e['latitude'];lo=e['longitude'];table_id=ie+1
            if south and ic in [1,2]:
                h+=(-40 if ic==1 else 40);table_id=1+len(events)*ic+ie
            if south and ic in [3,4]:
                delta=angular_distance(la,lo,centre_lat,centre_lon)
                fraction=(40/RADIUS*180/np.pi)/delta*(1 if ic==3 else -1)
                la,lo=great_circle_point(la,lo,centre_lat,centre_lon,fraction)
            sd=angular_distance(la,lo,lat,lon)
            source=np.array([np.interp(sd,da,a,left=np.nan,right=np.nan) for a in tables[table_id]])
            for m,y in zip(meta,waves):
                rd=angular_distance(m['station_latitude'],m['station_longitude'],lat,lon)
                receiver=np.array([np.interp(rd,da,a,left=np.nan,right=np.nan) for a in tables[0]])
                tt=source+receiver
                reference={'S':m['predicted_S'],'ScS':m['predicted_ScS']}
                if south and ic:
                    delta=angular_distance(la,lo,m['station_latitude'],m['station_longitude'])
                    for a in taup.get_travel_times(h,delta,['S','ScS']):reference[a.name]=a.time
                for ir,ref in enumerate(['ScS','S']):
                    sample=tt-reference[ref]+m['deconvolved_'+ref]
                    valid=np.isfinite(sample)&(sample>=t[0])&(sample<=t[-1])
                    signal=y*mute(t,m['deconvolved_S'],CFG['mute_half_width_s'])
                    for name,pred in m['multiples'].items():
                        if name in ['sS','SS']:signal*=mute(t,pred+m['deconvolved_S']-m['predicted_S'],CFG['mute_half_width_s'])
                    values[ic,ir]+=np.where(valid,np.interp(np.nan_to_num(sample,nan=-1),t,signal,left=0,right=0),0)
                    counts[ic,ir]+=valid
    np.savez_compressed(ROOT/f'data/images/{dataset}_location_sensitivity.npz',distance_km=distance,
                        depth=depth,weighted=values/max(1,counts.max()),hitcount=counts,cases=cases)


if __name__=='__main__':
    import sys
    from concurrent.futures import ProcessPoolExecutor
    names=sys.argv[1:] or ['historical','modern_same','expanded']
    with ProcessPoolExecutor(max_workers=min(3,len(names))) as pool:
        list(pool.map(calculate,names))
