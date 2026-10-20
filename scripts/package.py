"""Bundle the reviewable deliverables; exclude environments and raw MiniSEED.

Raw records remain in the local project and can be fetched from the included
archive manifests. This package uses the same exclusions as GitHub publication.
"""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED

ROOT=Path(__file__).resolve().parents[1]


def main():
    names=['README.md','.gitignore','requirements.txt','config.json',
           'receiver_splitting.json','rebuild.sh','usage.tex','usage.pdf',
           'references/README.md','references/AGENTS.md','references/academic-style.md']
    paths=[ROOT/name for name in names]
    for directory in ['scripts','report','figures','data','logs']:
        for path in (ROOT/directory).rglob('*'):
            if not path.is_file():continue
            if path.suffix in ['.mseed','.tmp','.aux','.out','.toc','.pid','.pyc','.png']:continue
            if directory=='report' and path.suffix=='.log':continue
            paths.append(path)
    target=ROOT/'deliverables.zip';temporary=ROOT/'.tmp/deliverables.zip'
    with ZipFile(temporary,'w',compression=ZIP_DEFLATED,compresslevel=6) as archive:
        for path in sorted(paths):
            compression=ZIP_STORED if path.suffix in ['.pdf','.npz','.zip'] else ZIP_DEFLATED
            archive.write(path,path.relative_to(ROOT),compress_type=compression)
    temporary.replace(target)
    print(f'{target}: {len(paths)} files, {target.stat().st_size/1e6:.1f} MB')


if __name__=='__main__':main()
