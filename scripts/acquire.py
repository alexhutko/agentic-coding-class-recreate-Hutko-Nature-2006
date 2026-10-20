"""Download only USGS event information and permitted FDSN archive records.

The catalog and HTTP request log are scientific outputs. Cached successes are
reused; failed requests are logged and can be retried by removing *.failed.json.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
from pathlib import Path
import time
import requests
from obspy import UTCDateTime, read_inventory
from obspy.geodetics import locations2degrees

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "config.json").read_text())
DATA = ROOT / "data"
USGS = "https://earthquake.usgs.gov/fdsnws/event/1/query"
ARCHIVES = {"BK": "https://service.ncedc.org", "CI": "https://service.scedc.caltech.edu"}
EARTHSCOPE = "https://service.iris.edu"


def fetch(url, params, path):
    """Atomic cached GET, with explicit provenance and bounded retries."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path.read_bytes()
    error_path = path.with_suffix(path.suffix + ".failed.json")
    if error_path.exists():
        return None
    for attempt in range(3):
        begin = time.time()
        try:
            r = requests.get(url, params=params, timeout=(20, 180))
            info = dict(url=r.url, status=r.status_code, seconds=time.time()-begin,
                        retrieved_utc=str(UTCDateTime()), path=str(path.relative_to(ROOT)))
            if r.status_code == 200 and r.content:
                info.update(bytes=len(r.content), sha256=hashlib.sha256(r.content).hexdigest())
                path.with_suffix(path.suffix + ".tmp").write_bytes(r.content)
                path.with_suffix(path.suffix + ".tmp").replace(path)
                path.with_suffix(path.suffix + ".request.json").write_text(json.dumps(info, indent=2))
                return r.content
            info['message'] = r.text[:300]
            if r.status_code in (204, 400, 404):
                break
        except requests.RequestException as exc:
            info = dict(url=url, params=params, error=str(exc), seconds=time.time()-begin)
        time.sleep(2*(attempt+1))
    error_path.write_text(json.dumps(info, indent=2))
    return None


def event_record(feature, historical=False):
    p = feature['properties']
    lon, lat, depth = feature['geometry']['coordinates']
    return dict(id=feature['id'], time=str(UTCDateTime(p['time']/1000)),
                latitude=lat, longitude=lon, depth_km=depth, magnitude=p['mag'],
                magnitude_type=p['magType'], historical=historical,
                catalog_exception=not (6 <= p['mag'] <= 7.2 and 218 <= depth <= 610),
                detail_url=p['detail'])


def catalog():
    q = dict(format='geojson', starttime=CFG['modern_start'], endtime=CFG['catalog_end'],
             minlatitude=-35, maxlatitude=0, minlongitude=-85, maxlongitude=-55,
             mindepth=218, maxdepth=610, minmagnitude=6, maxmagnitude=7.2, orderby='time-asc')
    raw = fetch(USGS, q, DATA/'catalog/modern.json')
    events = [event_record(f) for f in json.loads(raw)['features']]
    for date in CFG['historical_dates']:
        # Thomas2004 Table2 says 1999-08-30. USGS has no matching event then;
        # 1998-08-30 matches its (-23.934,-66.906) exactly and depth within 0.5km.
        query_date='1998-08-30' if date=='1999-08-30' else date
        raw = fetch(USGS, dict(format='geojson', starttime=query_date,
                    endtime=str(UTCDateTime(query_date)+86400), minlatitude=-35, maxlatitude=0,
                    minlongitude=-85, maxlongitude=-55, mindepth=180),
                    DATA/f'catalog/{query_date}.json')
        features = json.loads(raw)['features'] if raw else []
        if not features:
            print('No historical match', date, flush=True)
            continue
        if date == '2000-04-23':
            features = [f for f in features if UTCDateTime(f['properties']['time']/1000).hour == 17]
        chosen = max(features, key=lambda f: f['properties']['mag'] or 0)
        record=event_record(chosen, True)
        record['published_date']=date
        record['date_inference']='1998 event exactly matches published coordinates; inferred year typo' if query_date!=date else 'same UTC day'
        events.append(record)
    events.sort(key=lambda e:e['time'])
    def detail(e):
        fetch(e['detail_url'], {}, DATA/f"catalog/details/{e['id']}.json")
    with ThreadPoolExecutor(max_workers=CFG['workers']) as pool:
        list(pool.map(detail, events))
    (DATA/'events.json').write_text(json.dumps(events, indent=2))
    print('Catalog:', len(events), 'events;', sum(e['historical'] for e in events), 'historical', flush=True)
    return events


def station_table():
    raw = fetch(EARTHSCOPE+'/fdsnws/station/1/query',
                dict(net=','.join(CFG['networks']), cha='BH?', level='station', format='text',
                     minlat=30, maxlat=49, minlon=-126, maxlon=-105,
                     starttime=CFG['catalog_start'], endtime=CFG['catalog_end']),
                DATA/'catalog/stations.txt')
    rows=[]
    for line in raw.decode().splitlines():
        if line.startswith('#') or not line.strip(): continue
        f=line.split('|')
        rows.append(dict(network=f[0], station=f[1], latitude=float(f[2]),
                         longitude=float(f[3]), elevation_m=float(f[4]),
                         start=f[6], end=f[7]))
    return rows


def select_stations(e, rows):
    active=[]
    for r in rows:
        if UTCDateTime(r['start']) > UTCDateTime(e['time']): continue
        if r['end'] and UTCDateTime(r['end']) < UTCDateTime(e['time']): continue
        distance=locations2degrees(e['latitude'],e['longitude'],r['latitude'],r['longitude'])
        if 65 <= distance <= 85:
            active.append(r)
    # Historical California membership is approximate; no modern-only stations
    # are inserted into historical runs. For modern coverage retain historical
    # sites and one additional broadband site per 1-degree cell and network.
    selected={}
    cells=set()
    for r in sorted(active, key=lambda r:(r['station'] not in CFG['historical_stations'],r['network'],r['station'])):
        key=(r['network'],r['station'])
        old=r['station'] in CFG['historical_stations']
        cell=(r['network'],int(r['latitude']//CFG['expanded_station_cell_deg']),
              int(r['longitude']//CFG['expanded_station_cell_deg']))
        if old or (not e['historical'] and cell not in cells):
            selected[key]=r
            cells.add(cell)
    return list(selected.values())


def download_group(job):
    e, net, stations=job
    directory=DATA/'raw'/e['id']
    endpoint=ARCHIVES.get(net,EARTHSCOPE)
    names=','.join(sorted(set(r['station'] for r in stations)))
    epoch=UTCDateTime(e['time'])
    query=dict(net=net, sta=names, cha='BH?', starttime=str(epoch+500),endtime=str(epoch+1550))
    inv=fetch(endpoint+'/fdsnws/station/1/query',dict(query,level='response',format='xml'),directory/f'{net}.xml')
    if inv is None and endpoint != EARTHSCOPE:
        inv=fetch(EARTHSCOPE+'/fdsnws/station/1/query',dict(query,level='response',format='xml'),directory/f'{net}_fallback.xml')
    if inv is not None:
        raw=fetch(endpoint+'/fdsnws/dataselect/1/query',query,directory/f'{net}.mseed')
        if raw is None and endpoint != EARTHSCOPE:
            raw=fetch(EARTHSCOPE+'/fdsnws/dataselect/1/query',query,directory/f'{net}_fallback.mseed')
        print(e['id'],net,'stations',len(stations),'waveform bytes',len(raw) if raw else 0,flush=True)
    else:
        print(e['id'],net,'metadata unavailable',flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--catalog-only',action='store_true')
    p.add_argument('--event')
    args=p.parse_args()
    events=catalog()
    rows=station_table()
    jobs=[]
    for e in events:
        if args.event and e['id'] != args.event: continue
        stations=select_stations(e,rows)
        directory=DATA/'raw'/e['id']; directory.mkdir(parents=True,exist_ok=True)
        (directory/'requested-stations.json').write_text(json.dumps(stations,indent=2))
        for net in sorted(set(r['network'] for r in stations)):
            jobs.append((e,net,[r for r in stations if r['network']==net]))
    if not args.catalog_only:
        with ThreadPoolExecutor(max_workers=CFG['workers']) as pool:
            list(pool.map(download_group,jobs))


if __name__=='__main__': main()
