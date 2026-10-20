"""Readable SH displacement processing and event-wise source deconvolution.

Every accepted trace retains its un-deconvolved displacement, source wavelet,
phase picks, quality measures, and reason for acceptance. No imaging result is
used to select observations or tune the source wavelet.
"""
import argparse
import hashlib
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import warnings
import numpy as np
from scipy.signal import butter, sosfiltfilt
from scipy.fft import rfft, irfft, next_fast_len
from obspy import read, read_inventory, UTCDateTime, Stream
from obspy.geodetics import gps2dist_azimuth, locations2degrees
from obspy.taup import TauPyModel

ROOT=Path(__file__).resolve().parents[1]
CFG=json.loads((ROOT/'config.json').read_text())


def processing_fingerprint():
    paths=[Path(__file__),ROOT/'config.json',ROOT/'receiver_splitting.json']
    return hashlib.sha256(b''.join(p.read_bytes() for p in paths)).hexdigest()


def band_filter(x, frequency, sample_rate, kind='lowpass'):
    return sosfiltfilt(butter(CFG['filter_order'],frequency,btype=kind,fs=sample_rate,output='sos'),x)


def undo_splitting(north, east, dt, fast_deg, delay_s):
    """Undo a horizontal fast/slow layer, preserving the mean arrival time.

    Fast is delayed by dt_split/2; slow is advanced by dt_split/2.
    Inputs are displacement in metres. Padding prevents FFT wrap-around.
    """
    phi=np.deg2rad(fast_deg)
    fast=north*np.cos(phi)+east*np.sin(phi)
    slow=-north*np.sin(phi)+east*np.cos(phi)
    t=np.arange(len(north))*dt
    fast=np.interp(t-delay_s/2,t,fast,left=0,right=0)
    slow=np.interp(t+delay_s/2,t,slow,left=0,right=0)
    return fast*np.cos(phi)-slow*np.sin(phi),fast*np.sin(phi)+slow*np.cos(phi)


def deconvolve(signal, source, source_zero, dt, water_level):
    """Water-level spectral division: X W* / max(|W|², epsilon max |W|²)."""
    n=next_fast_len(len(signal)+len(source))
    wave=np.zeros(n)
    indices=(np.arange(len(source))-source_zero)%n
    wave[indices]=source
    w=rfft(wave); power=np.abs(w)**2
    spectrum=rfft(signal,n)*w.conj()/np.maximum(power,water_level*power.max())
    return band_filter(irfft(spectrum,n)[:len(signal)],CFG['lowpass_hz'],1/dt)


def moment_tensor(e):
    path=ROOT/f"data/catalog/details/{e['id']}.json"
    if not path.exists(): return None
    products=json.loads(path.read_text())['properties'].get('products',{})
    for product in products.get('moment-tensor',[]):
        p=product['properties']
        try:
            rr,tt,pp,rt,rp,tp=[float(p['tensor-'+k]) for k in ['mrr','mtt','mpp','mrt','mrp','mtp']]
            # USGS spherical (r,theta,phi) = (up,south,east); convert to N,E,D.
            return np.array([[tt,-tp,rt],[-tp,pp,-rp],[rt,-rp,rr]])
        except (KeyError,ValueError): pass
    return None


def sh_radiation(tensor, azimuth, takeoff):
    if tensor is None: return None
    a,i=np.deg2rad([azimuth,takeoff])
    direction=np.array([np.sin(i)*np.cos(a),np.sin(i)*np.sin(a),np.cos(i)])
    transverse=np.array([-np.sin(a),np.cos(a),0])
    scalar=np.sqrt(np.sum(tensor*tensor)/2)
    return float(transverse@tensor@direction/scalar)


def pick(t,x,predicted,half_width):
    indices=np.flatnonzero(np.abs(t-predicted)<=half_width)
    if not len(indices): raise ValueError('phase outside downloaded window')
    index=indices[np.argmax(np.abs(x[indices]))]
    if index==indices[0] or index==indices[-1]: raise ValueError('phase peak at search boundary')
    return float(t[index]),float(x[index])


def process_event(e):
    warnings.filterwarnings('ignore',category=UserWarning)
    output=ROOT/f"data/processed/{e['id']}.npz"
    fingerprint=processing_fingerprint()
    if output.exists():
        previous=np.load(output)
        if 'fingerprint' in previous and str(previous['fingerprint'])==fingerprint:
            return e['id'],'cached'
    directory=ROOT/f"data/raw/{e['id']}"
    output.parent.mkdir(parents=True,exist_ok=True)
    audit=[]; candidates=[]; model=TauPyModel('prem'); tensor=moment_tensor(e)
    dt=1/CFG['sample_rate_hz']; t=np.arange(520,1530+dt/2,dt)
    corrections_path=ROOT/'receiver_splitting.json'
    corrections=json.loads(corrections_path.read_text()) if corrections_path.exists() else {}
    for wavepath in sorted(directory.glob('*.mseed')):
        net=wavepath.stem.replace('_fallback','')
        invpath=directory/(net+'.xml')
        if not invpath.exists(): invpath=directory/(net+'_fallback.xml')
        try: stream=read(str(wavepath)); inv=read_inventory(str(invpath))
        except Exception as exc:
            audit.append(dict(id=net,accepted=False,reason=str(exc)));continue
        for sta in sorted(set(tr.stats.station for tr in stream)):
            record=dict(id=net+'.'+sta,accepted=False)
            try:
                station=inv.select(station=sta,time=UTCDateTime(e['time']))[0][0]
                distance=locations2degrees(e['latitude'],e['longitude'],station.latitude,station.longitude)
                if not 65<=distance<=85: raise ValueError('outside distance range')
                _,az,baz=gps2dist_azimuth(e['latitude'],e['longitude'],station.latitude,station.longitude)
                arrivals=model.get_ray_paths(e['depth_km'],distance,phase_list=['S','ScS','sS','SS','sScS'])
                phases={}
                for a in arrivals:
                    if a.name not in phases: phases[a.name]=a
                if 'S' not in phases or 'ScS' not in phases: raise ValueError('missing PREM reference phase')
                rad=[sh_radiation(tensor,az,phases[p].takeoff_angle) for p in ['S','ScS']]
                record.update(distance_deg=distance,radiation_S=rad[0],radiation_ScS=rad[1])
                if rad[0] is not None and (min(abs(v) for v in rad)<CFG['radiation_min'] or rad[0]*rad[1]<=0):
                    raise ValueError('unstable or weak SH radiation (<0.6)')
                # Pick a complete, gap-free three-component location. Coordinate
                # orientation and instrument epochs come from archive StationXML.
                choices=[]
                for loc in sorted(set(tr.stats.location for tr in stream.select(station=sta))):
                    sub=stream.select(station=sta,location=loc).copy()
                    if sub.get_gaps(): continue
                    sub.merge(method=0)
                    if len(sub)!=3: continue
                    if min(tr.stats.npts*tr.stats.delta for tr in sub)<1000: continue
                    choices.append(sub)
                if not choices: raise ValueError('no complete gap-free BH triplet')
                sub=choices[0]
                for tr in sub:
                    tr.detrend('linear');tr.taper(0.03)
                    nyquist=tr.stats.sampling_rate/2
                    pref=list(CFG['instrument_prefilter_hz'])
                    pref[-1]=min(pref[-1],0.95*nyquist); pref[-2]=min(pref[-2],0.8*nyquist)
                    tr.remove_response(inventory=inv,output='DISP',pre_filt=pref,water_level=60)
                sub.rotate(method='->ZNE',inventory=inv)
                n=sub.select(component='N')[0]; east=sub.select(component='E')[0]
                for tr in [n,east]:
                    tr.filter('highpass',freq=CFG['highpass_hz'],corners=4,zerophase=True)
                    tr.filter('lowpass',freq=2.0,corners=8,zerophase=True)
                north=np.interp(t,n.times()+float(n.stats.starttime-UTCDateTime(e['time'])),n.data)
                eastward=np.interp(t,east.times()+float(east.stats.starttime-UTCDateTime(e['time'])),east.data)
                correction=corrections.get(net+'.'+sta)
                if correction:
                    north,eastward=undo_splitting(north,eastward,dt,correction['fast_deg'],correction['delay_s'])
                b=np.deg2rad(baz)
                transverse=north*np.sin(b)-eastward*np.cos(b)
                filtered=band_filter(transverse,CFG['lowpass_hz'],1/dt)
                ts,amp_s=pick(t,filtered,phases['S'].time,CFG['phase_search_s'])
                # A common origin/path shift is estimated from S. The residual
                # ScS-S anomaly can be substantial in this fast mantle corridor.
                # Prevent the same pulse being selected twice without imposing
                # a fraction of the PREM separation as the picking window.
                expected=phases['ScS'].time+ts-phases['S'].time
                indices=np.flatnonzero((abs(t-expected)<=CFG['phase_search_s'])&(t>=ts+6))
                if len(indices)<3: raise ValueError('S/ScS insufficiently separated')
                j=indices[np.argmax(filtered[indices]*np.sign(amp_s))]
                if j in (indices[0],indices[-1]): raise ValueError('ScS peak at joint search boundary')
                tc,amp_c=float(t[j]),float(filtered[j])
                noise=filtered[(t>=ts-90)&(t<=ts-30)]
                rms=float(np.sqrt(np.mean(noise**2)))
                snr=min(abs(amp_s),abs(amp_c))/max(rms,1e-30)
                record.update(snr=snr)
                if snr<CFG['snr_min']: raise ValueError('S or ScS below peak/RMS SNR threshold')
                if amp_s*amp_c<=0: raise ValueError('opposite observed S and ScS polarity')
                path=phases['ScS'].path
                bounce_fraction=float(path['dist'][np.argmax(path['depth'])]/np.deg2rad(distance))
                from geometry import great_circle_point
                blat,blon=great_circle_point(e['latitude'],e['longitude'],station.latitude,station.longitude,bounce_fraction)
                meta=dict(record,location=sub[0].stats.location,station_latitude=station.latitude,
                          station_longitude=station.longitude,backazimuth=baz,azimuth=az,
                          predicted_S=phases['S'].time,predicted_ScS=phases['ScS'].time,
                          picked_S=ts,picked_ScS=tc,amplitude_S_m=amp_s,amplitude_ScS_m=amp_c,
                          bounce_latitude=float(blat),bounce_longitude=float(blon),
                          splitting_applied=bool(correction),radiation_verified=tensor is not None,
                          multiples={p:phases[p].time for p in ['sS','SS','sScS'] if p in phases})
                candidates.append((meta,transverse,filtered))
            except Exception as exc:
                record['reason']=str(exc)
            audit.append(record)
    # Some stations are archived under both a regional and a global network
    # code (for example PFO). Do not count colocated sensors twice.
    unique=[]
    for item in sorted(candidates,key=lambda item:(item[0]['id'].startswith(('II.','IU.')),item[0]['id'])):
        m=item[0]
        if any(abs(m['station_latitude']-u[0]['station_latitude'])<.02 and
               abs(m['station_longitude']-u[0]['station_longitude'])<.02 for u in unique):
            m.update(accepted=False,reason='colocated sensor already represented')
        else:unique.append(item)
    candidates=unique
    if len(candidates)<CFG['source_stations_min']:
        output.unlink(missing_ok=True)
        (output.with_suffix('.audit.json')).write_text(json.dumps(dict(event=e,traces=audit,
                  failure='fewer than three source-wavelet candidates'),indent=2))
        return e['id'], 'insufficient candidates '+str(len(candidates))
    # Align on measured ScS peaks and construct one source pulse per event.
    st=np.arange(*[CFG['source_window_s'][0],CFG['source_window_s'][1]+dt/2,dt])
    ranked=sorted(candidates,key=lambda x:x[0]['snr'],reverse=True)[:CFG['source_stations_max']]
    pulses=np.array([np.interp(st+m['picked_ScS'],t,x)/m['amplitude_ScS_m'] for m,x,_ in ranked])
    source=pulses.mean(axis=0)
    # Crop the primary ScS lobe at nearest zero crossings. This avoids treating
    # candidate D'' precursor energy as part of the earthquake source.
    centre=np.argmin(abs(st)); crossings=np.flatnonzero(source[:-1]*source[1:]<=0)
    left=max([0]+[int(v+1) for v in crossings if v<centre])
    right=min([len(st)-1]+[int(v) for v in crossings if v>=centre])
    crop=np.zeros_like(source); crop[left:right+1]=source[left:right+1]
    from scipy.signal.windows import tukey
    crop[left:right+1]*=tukey(right-left+1,alpha=0.25)
    source=crop
    used=[]; processed=[]; deconvolved=[]
    for meta,x,filtered in candidates:
        pulse=np.interp(st+meta['picked_ScS'],t,x)/meta['amplitude_ScS_m']
        corr=float(np.corrcoef(pulse,source)[0,1])
        meta['source_correlation']=corr
        if corr<CFG['correlation_min']:
            meta.update(accepted=False,reason='poor ScS/source correlation')
            continue
        y=deconvolve(x,source,centre,dt,CFG['water_level'])
        try:
            ps,as_=pick(t,y,meta['picked_S'],5)
            pc,ac=pick(t,y,meta['picked_ScS'],5)
        except ValueError:
            meta.update(accepted=False,reason='deconvolved phase peak at search boundary')
            continue
        if as_*ac<=0: continue
        meta.update(accepted=True,deconvolved_S=ps,deconvolved_ScS=pc,
                    deconvolved_S_amplitude=as_,reason='accepted')
        used.append(meta); processed.append(filtered/meta['amplitude_S_m']);deconvolved.append(y/as_)
    np.savez_compressed(output,t=t,processed=np.array(processed),deconvolved=np.array(deconvolved),
                        source_time=st,source=source,
                        metadata=json.dumps(used),event=json.dumps(e),
                        source_station_ids=json.dumps([m['id'] for m,_,_ in ranked]),fingerprint=fingerprint)
    # Include post-deconvolution decisions as well as early rejection reasons.
    (output.with_suffix('.audit.json')).write_text(json.dumps(dict(event=e,traces=audit,
                candidates=[m for m,_,_ in candidates],accepted=len(used)),indent=2))
    return e['id'],f'{len(used)} accepted / {len(audit)} stations'


def main():
    p=argparse.ArgumentParser();p.add_argument('--event');p.add_argument('--workers',type=int,default=4)
    args=p.parse_args();events=json.loads((ROOT/'data/events.json').read_text())
    if args.event: events=[e for e in events if e['id']==args.event]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for result in pool.map(process_event,events): print(*result,flush=True)


if __name__=='__main__': main()
