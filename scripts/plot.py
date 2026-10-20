"""Plot saved numerical outputs only; never load published images as data."""
import argparse
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Polygon
from scipy.ndimage import map_coordinates
from geometry import great_circle_point,angular_distance
from rays import CMB,RADIUS
from migrate import CFG,profiles

ROOT=Path(__file__).resolve().parents[1]
FIG=ROOT/'figures';FIG.mkdir(exist_ok=True)
plt.rcParams.update({'font.size':9,'axes.spines.top':False,'axes.spines.right':False,
                     'savefig.bbox':'tight','pdf.fonttype':42})


def load_saved(path):
    # NPZ access decompresses on every lookup. Load once before plotting many
    # stations or slices; this avoids minutes of repeated decompression.
    with np.load(path) as archive:
        return {key:archive[key] for key in archive.files}


def coverage_mask(f,iv=0):
    return (f['hitcount'][iv]>=CFG['coverage_min_traces'])&(f['event_count'][iv]>=CFG['coverage_min_events'])


def section(ax,s,depth,image,title,mask=None,scale=.15):
    a=np.ma.masked_where(~mask,image) if mask is not None else image
    im=ax.pcolormesh(s,CMB-depth,a,cmap='RdBu_r',vmin=-scale,vmax=scale,shading='nearest',rasterized=True)
    ax.axhline(0,color='k',lw=.5);ax.set_ylim(-20,580)
    ax.set_aspect('equal');ax.set_title(title,loc='left',fontsize=9)
    ax.set_xlabel('Distance at CMB (km)');ax.set_ylabel('Height above CMB (km)')
    return im


def main_figures(dataset):
    f=load_saved(ROOT/f'data/images/{dataset}.npz')
    traces=json.loads((ROOT/f'data/images/{dataset}.traces.json').read_text())
    events=json.loads(str(f['events']))
    output=FIG/dataset;output.mkdir(exist_ok=True)
    # Figure 1: geometry derived from USGS and station records, ray-calculated
    # CMB bounce points. Coastlines, if cached, are cartographic context only.
    fig,axes=plt.subplots(1,2,figsize=(11,5),gridspec_kw={'width_ratios':[1.2,1]})
    coastline=load_saved(ROOT/'data/geography/coastline.npz')['vertices']
    for coast_ax in axes:coast_ax.plot(coastline[:,0],coastline[:,1],color='0.5',lw=.5,zorder=0)
    ax=axes[0]
    ax.scatter([m['station_longitude'] for m in traces],[m['station_latitude'] for m in traces],s=8,marker='^',c='firebrick',label='Receivers')
    ax.scatter([e['longitude'] for e in events],[e['latitude'] for e in events],s=28,marker='*',c='black',label='USGS events')
    ax.scatter([m['bounce_longitude'] for m in traces],[m['bounce_latitude'] for m in traces],s=3,c='royalblue',label='ScS bounce')
    for name,(lat,lon,_) in profiles().items():ax.plot(lon,lat,'k-',lw=.8);ax.text(lon[0],lat[0],name)
    ax.set(xlim=(-130,-55),ylim=(-35,52),xlabel='Longitude (degrees east)',ylabel='Latitude (degrees north)',title=f'Figure 1 geometry: {dataset}')
    ax.legend(fontsize=7);ax.grid(alpha=.2)
    ax=axes[1]
    ax.scatter([m['bounce_longitude'] for m in traces],[m['bounce_latitude'] for m in traces],s=4,c='royalblue')
    for name,(lat,lon,_) in profiles().items():ax.plot(lon,lat,'k-',lw=.8);ax.text(lon[0],lat[0],name)
    ax.set(xlim=(-105,-75),ylim=(-8,23),xlabel='Longitude (degrees east)',ylabel='Latitude (degrees north)',title=f"{len(traces)} traces, {len(events)} events")
    if dataset=='expanded':ax.set(xlim=(CFG['expanded_grid_longitude'][0],CFG['expanded_grid_longitude'][1]),ylim=(CFG['expanded_grid_latitude'][0],CFG['expanded_grid_latitude'][1]))
    ax.set_aspect(1/np.cos(np.deg2rad(7)));ax.grid(alpha=.2)
    fig.tight_layout();fig.savefig(output/'figure1.pdf');plt.close(fig)
    # Four original Figure 2 sections: A/B with ScS retained/censored.
    fig,axes=plt.subplots(2,2,figsize=(12,5.5))
    for col,name in enumerate(['A','B']):
        p=load_saved(ROOT/f'data/images/{dataset}_profile{name}.npz')
        for row,iv in enumerate([0,1]):
            mask=(p['hitcount'][iv]>=20)&(p['event_count'][iv]>=3)
            im=section(axes[row,col],p['distance_km'],p['depth'],p['weighted'][iv],
                       f"{'a' if row==0 else 'b'}: {name} — ScS {'retained' if iv==0 else 'censored'}",mask)
    fig.colorbar(im,ax=axes.ravel().tolist(),fraction=.025,label='Sum of S-normalized amplitude / maximum hitcount')
    fig.savefig(output/'figure2.pdf');plt.close(fig)
    p=load_saved(ROOT/f'data/images/{dataset}_profileA.npz')
    fig,axes=plt.subplots(2,2,figsize=(12,5.5))
    for i,(ax,name) in enumerate(zip(axes.flat,['PREM','UT','UCB','CIT'])):
        if i==0:
            section(ax,p['distance_km'],p['depth'],p['weighted'][0],'PREM: independently computed',
                    (p['hitcount'][0]>=20)&(p['event_count'][0]>=3))
        else:
            ax.axis('off');ax.text(.5,.5,name+' — NOT REPRODUCED\nNumerical 3-D model coefficients unavailable\nfrom the permitted written specifications.',ha='center',va='center',transform=ax.transAxes)
    fig.savefig(output/'figure3.pdf');plt.close(fig)
    # Schematic is visibly labeled and does not turn the inferred slab into an
    # independently recovered thermomechanical model.
    fig,axes=plt.subplots(2,1,figsize=(9,6))
    ax=axes[0];x=np.linspace(0,1700,400)
    upper=200+100*(x>850)
    ax.fill_between(x,0,upper,color='lightsteelblue');ax.plot(x,upper,color='navy')
    ax.text(80,370,'SCHEMATIC: published folded-slab interpretation\nStep imposed for illustration; no flow or temperature inversion',fontsize=10)
    ax.set(xlim=(0,1700),ylim=(0,500),ylabel='Illustrative height (km)');ax.set_aspect('equal')
    section(axes[1],p['distance_km'],p['depth'],p['weighted'][0],dataset+': computed migration section',
            (p['hitcount'][0]>=20)&(p['event_count'][0]>=3))
    fig.tight_layout();fig.savefig(output/'figure4.pdf');plt.close(fig)


def supplementary(dataset):
    f=load_saved(ROOT/f'data/images/{dataset}.npz');output=FIG/dataset
    pa=load_saved(ROOT/f'data/images/{dataset}_profileA.npz')
    events=json.loads(str(pa['events'])); clusters={'North':lambda e:e['latitude']>-17,
            'Central':lambda e:-25<e['latitude']<=-17,'South':lambda e:e['latitude']<=-25,'All':lambda e:True}
    fig,axs=plt.subplots(5,2,figsize=(11,12))
    for row,(label,test) in enumerate(clusters.items()):
        chosen=[i for i,e in enumerate(events) if test(e)]
        for col,iv in enumerate([0,2]):
            im=pa['per_event'][chosen,iv].sum(axis=0)/max(1,int(pa['hitcount'].max()))
            section(axs[row,col],pa['distance_km'],pa['depth'],im,label+' / '+['ScS','S'][col])
    for col,iv in enumerate([0,2]):
        ax=axs[4,col];mesh=ax.pcolormesh(pa['distance_km'],CMB-pa['depth'],pa['hitcount'][iv],shading='nearest',rasterized=True)
        ax.set(xlabel='Distance at CMB (km)',ylabel='Height (km)',title='Valid ray hitcount');ax.set_aspect('equal')
        fig.colorbar(mesh,ax=ax,fraction=.025,label='Paths')
    fig.tight_layout();fig.savefig(output/'supplement2.pdf');plt.close(fig)
    # S3: six independently specified parallel corridors in each orientation.
    for orientation,stem in [('A','supplement3a'),('B','supplement3b')]:
        fig,axs=plt.subplots(6,4,figsize=(15,11))
        for row,offset in enumerate([-2.5,-1.5,-.5,.5,1.5,2.5]):
            lat,lon,s=profiles()[orientation]
            # Translate longitudes; no endpoints have been digitized.
            coords=np.array([(lat-f['latitude'][0])/.2,(lon+offset-f['longitude'][0])/.2])
            for iv in range(4):
                a=np.array([map_coordinates(layer,coords,order=1,mode='constant',cval=np.nan) for layer in f['weighted'][iv]])
                section(axs[row,iv],s,f['depth'],a,f"{orientation}, offset {offset:+.1f}° / {['ScS','ScS muted','S','S muted'][iv]}")
                axs[row,iv].tick_params(labelsize=6);axs[row,iv].set_xlabel('CMB distance (km)',fontsize=7);axs[row,iv].set_ylabel('Height (km)',fontsize=7)
        fig.tight_layout();fig.savefig(output/(stem+'.pdf'));plt.close(fig)
    fig,axs=plt.subplots(7,4,figsize=(11,16))
    for row,height in enumerate([400,350,300,250,200,100,0]):
        iz=np.argmin(abs(CMB-f['depth']-height))
        for col,iv in enumerate([1,0,1,0]):
            ax=axs[row,col]
            values=f['weighted'][iv,iz] if col<2 else f['hitcount'][iv,iz]
            if col<2:values=np.where(coverage_mask(f,iv)[iz],values,np.nan)
            opts=dict(cmap='RdBu_r',vmin=-.15,vmax=.15) if col<2 else dict(cmap='viridis',vmin=0,vmax=f['hitcount'].max())
            mesh=ax.pcolormesh(f['longitude'],f['latitude'],values,shading='nearest',rasterized=True,**opts)
            if col==0:amplitude_mesh=mesh
            if col==2:count_mesh=mesh
            ax.set_title(f'{CMB-f["depth"][iz]:.0f} km; '+(['muted','retained','hits muted','hits retained'][col]),fontsize=8)
            ax.set_aspect(1/np.cos(np.deg2rad(7)));ax.tick_params(labelsize=6)
    fig.tight_layout()
    fig.colorbar(amplitude_mesh,ax=axs[:,:2].ravel().tolist(),fraction=.015,label='Weighted amplitude')
    fig.colorbar(count_mesh,ax=axs[:,2:].ravel().tolist(),fraction=.015,label='Valid paths')
    fig.savefig(output/'supplement5.pdf');plt.close(fig)
    # S11 counterpart: average the saved 3-D profile, not a new double-array
    # inversion. Label this distinction; true 1-D stacks are generated separately.
    path=ROOT/f'data/images/{dataset}_double_array.npz'
    if path.exists():
        d=load_saved(path);fig,axs=plt.subplots(2,2,figsize=(9,7))
        for ib in range(2):
            for ir in range(2):
                ax=axs[ib,ir];ax.plot(d['mean'][ib,ir],CMB-d['depth'],'k')
                ax.fill_betweenx(CMB-d['depth'],d['low'][ib,ir],d['high'][ib,ir],color='0.8')
                ax.axvline(0,color='0.5',lw=.6);ax.set(xlabel='Mean S-normalized amplitude',ylabel='Height above CMB (km)',title=['South','North'][ib]+' / '+['ScS','S'][ir])
        fig.tight_layout();fig.savefig(output/'supplement11.pdf');plt.close(fig)


def event_figures(dataset):
    records=json.loads((ROOT/f'data/images/{dataset}.traces.json').read_text())
    events=json.loads((ROOT/'data/events.json').read_text())
    out=FIG/dataset/'events';out.mkdir(exist_ok=True)
    for event in events:
        if dataset=='historical' and not event['historical']:continue
        ids={m['id'] for m in records if m['event_id']==event['id']}
        path=ROOT/f'data/processed/{event["id"]}.npz'
        with PdfPages(out/(event['id']+'.pdf')) as pdf:
            if not path.exists() or not ids:
                fig,ax=plt.subplots(figsize=(11,4));ax.axis('off')
                audit=path.with_suffix('.audit.json');reason='No accepted trace in this dataset.'
                if audit.exists():
                    from collections import Counter
                    a=json.loads(audit.read_text());c=Counter(m.get('reason','candidate') for m in a['traces'])
                    reason+='\n'+'\n'.join(f'{k}: {v}' for k,v in c.most_common(6))
                ax.text(.03,.85,event['id']+' / '+event['time']+'\n'+reason,va='top',transform=ax.transAxes)
                pdf.savefig(fig);plt.close(fig);continue
            f=load_saved(path);meta=json.loads(str(f['metadata']));use=[i for i,m in enumerate(meta) if m['id'] in ids]
            use.sort(key=lambda i:meta[i]['distance_deg'])
            for start in range(0,len(use),24):
                subset=use[start:start+24]
                fig,axs=plt.subplots(1,2,figsize=(13,max(5,len(subset)*.29)))
                xmin=min(meta[i]['deconvolved_S']-meta[i]['deconvolved_ScS'] for i in subset)-80
                for row,i in enumerate(subset):
                    m=meta[i];tt=f['t']-m['deconvolved_ScS']
                    for ax,key in zip(axs,['processed','deconvolved']):
                        ax.plot(tt,row+.32*np.clip(f[key][i],-2,2),'k',lw=.45)
                        ax.plot(m['deconvolved_S']-m['deconvolved_ScS'],row,'o',color='firebrick',ms=2)
                labels=[f"{meta[i]['id']}  {meta[i]['distance_deg']:.1f}°  SNR {meta[i]['snr']:.0f}" for i in subset]
                for ax,title in zip(axs,['Processed displacement','Processed + source deconvolved']):
                    ax.set(xlim=(xmin,65),ylim=(-1,len(subset)),xlabel='Time from picked ScS (s)',title=title)
                    ax.axvline(0,color='royalblue',lw=.6);ax.set_yticks(range(len(subset)));ax.set_yticklabels(labels,fontsize=8)
                    ax.grid(axis='x',alpha=.2)
                fig.suptitle(event['id']+'  '+event['time'][:19]+f"  M{event['magnitude']}  {event['depth_km']:.1f} km\n{dataset}; S peak = 1 separately before/after deconvolution; plotting clipped at ±2; dots mark S",fontsize=9)
                fig.tight_layout();pdf.savefig(fig);plt.close(fig)


def validation():
    # A conceptual branch diagram is deliberately separate from computed rays.
    fig,ax=plt.subplots(figsize=(8,3))
    ax.axhspan(0,.3,color='lightskyblue');ax.axhspan(.3,1,color='honeydew')
    x=np.linspace(0,1,200)
    for height,label,color in [(.3,'Sbc reflected branch','darkorange'),(.15,'Scd turning branch','purple')]:
        y=height+(1-height)*(2*x-1)**2
        ax.plot(x,y,color=color,lw=2,label=label)
    ax.axhline(.3,color='k',lw=.6);ax.text(.03,.33,'Assumed D double-prime velocity jump')
    ax.set(xlim=(0,1),ylim=(0,1.05),title='Figure 1 branch concept: SCHEMATIC, not calculated rays')
    ax.axis('off');ax.legend(loc='upper center',fontsize=8)
    fig.savefig(FIG/'figure1-triplication-schematic.pdf');plt.close(fig)
    f=load_saved(ROOT/'data/validation/deconvolution.npz')
    fig,axs=plt.subplots(2,1,figsize=(9,5))
    axs[0].plot(f['source_time'],f['source']);axs[0].set(xlabel='Time (s)',ylabel='Source amplitude')
    axs[1].plot(f['time'],f['input']/np.max(f['input']),label='Convolved input')
    axs[1].plot(f['time'],f['output']/np.max(f['output']),label='Deconvolved');axs[1].legend();axs[1].set(xlabel='Time (s)',ylabel='Normalized amplitude')
    fig.tight_layout();fig.savefig(FIG/'validation.pdf');plt.close(fig)
    for dataset in ['historical','modern_same','expanded']:
        p=ROOT/'data/validation'/('points.npz' if dataset=='historical' else f'points_{dataset}.npz')
        if p.exists():
            f=load_saved(p);fig,axs=plt.subplots(4,4,figsize=(14,10))
            lat=f['event_latitude']
            groups=[('South',lat<-25),('Central',(lat>=-25)&(lat<-17)),('North',lat>=-17),('All',np.ones(len(lat),dtype=bool))]
            for row,(group,mask) in enumerate(groups):
                for col,name in enumerate(['A','B']):
                    hits=f[name+'_counts'][mask].sum(axis=0)
                    amplitude=f[name+'_per_event'][mask].sum(axis=0)/max(1,hits.max())
                    section(axs[row,col*2],f[name+'_distance_km'],f['depth'],amplitude,group+' / '+name,scale=.5)
                    ax=axs[row,col*2+1]
                    mesh=ax.pcolormesh(f[name+'_distance_km'],CMB-f['depth'],hits,shading='nearest',cmap='viridis',rasterized=True,vmin=0,vmax=f['hitcount'].max())
                    ax.set(title=group+' / '+name+' hitcount',xlabel='CMB distance (km)',ylabel='Height (km)')
            fig.tight_layout();fig.colorbar(mesh,ax=axs[:,1::2].ravel().tolist(),fraction=.02,label='Valid paths')
            fig.savefig(FIG/dataset/'supplement6.pdf')
            if dataset=='historical':fig.savefig(FIG/'supplement6.pdf')
            plt.close(fig)
    f=load_saved(ROOT/'data/validation/ray_synthetics.npz')
    fig,axs=plt.subplots(1,2,figsize=(11,5))
    for i,drop in enumerate(f['reductions']):
        axs[0].plot(f['time'],f['waves'][i]+i*1.5,label=f'{drop*100:.1f}% decrease')
        axs[1].plot(f['velocities'][i],f['depth'],label=f'{drop*100:.1f}% decrease')
    axs[0].set(xlabel='Time from predicted S (s)',ylabel='Arbitrary amplitude + offset',title='S7b: kinematic SH test; no Scd')
    axs[1].set(xlabel='Shear velocity (km/s)',ylabel='Depth (km)',title='S7c: specified jumps on PREM');axs[1].invert_yaxis();axs[1].legend(fontsize=7)
    fig.tight_layout();fig.savefig(FIG/'supplement7bc.pdf');plt.close(fig)
    fig=plt.figure(figsize=(9,5));ax=fig.add_subplot(111,projection='polar')
    for name in ['S','ScS']:ax.plot(f['ray_'+name+'_distance'],RADIUS-f['ray_'+name+'_depth'],label=name)
    a=np.linspace(0,np.pi/2,200);ax.plot(a,np.full_like(a,RADIUS-CMB),'k',lw=.8)
    ax.set_thetamin(0);ax.set_thetamax(90);ax.set_ylim(0,RADIUS);ax.legend();ax.set_title('Figure 1 ray inset: independently computed PREM paths')
    fig.savefig(FIG/'figure1-rays.pdf');plt.close(fig)
    f=load_saved(ROOT/'data/validation/step_model.npz')
    fig,ax=plt.subplots(figsize=(10,4))
    im=ax.pcolormesh(f['distance_km'],CMB-f['depth'],f['velocity'],shading='nearest',cmap='viridis',rasterized=True)
    ax.plot(f['distance_km'],f['discontinuity_height_km'],'k',lw=.7)
    ax.set(xlabel='Distance at CMB (km)',ylabel='Height above CMB (km)',title='S8 model / S9a: specified step on assumed PREM background\nNo finite-difference wavefield calculated');ax.set_aspect('equal')
    fig.colorbar(im,ax=ax,label='Shear speed (km/s)');fig.savefig(FIG/'step-model.pdf');plt.close(fig)
    for dataset in ['historical','modern_same','expanded']:
        path=ROOT/f'data/images/{dataset}_location_sensitivity.npz'
        if path.exists():
            f=load_saved(path);fig,axs=plt.subplots(5,2,figsize=(11,12))
            for i,label in enumerate(f['cases']):
                for j,ref in enumerate(['ScS','S']):section(axs[i,j],f['distance_km'],f['depth'],f['weighted'][i,j],str(label)+' / '+ref)
            fig.tight_layout();fig.savefig(FIG/dataset/'supplement10.pdf');plt.close(fig)


def plot_dataset(job):
    name,events_only=job
    if not events_only:main_figures(name);supplementary(name)
    event_figures(name)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dataset',default='all');p.add_argument('--events-only',action='store_true')
    args=p.parse_args()
    names=['historical','modern_same','expanded'] if args.dataset=='all' else [args.dataset]
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=min(3,len(names))) as pool:
        list(pool.map(plot_dataset,[(name,args.events_only) for name in names]))
    if not args.events_only:validation()
