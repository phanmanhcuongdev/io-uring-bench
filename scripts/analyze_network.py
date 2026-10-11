#!/usr/bin/env python3
"""Summarize network echo benchmark CSVs; dependency-free SVG plotting."""
import argparse, csv
from collections import defaultdict
from pathlib import Path
from statistics import median
from math import isfinite
from svg_plot import write_bar_chart

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,default=Path('results'))
    p.add_argument('--out',type=Path,default=Path('charts'))
    args=p.parse_args()
    groups=defaultdict(list)
    repeat_ids=defaultdict(list)
    for src in args.root.glob('*/*/network/runs.csv'):
        parts=src.relative_to(args.root).parts
        with src.open(newline='') as f:
            for row in csv.DictReader(f):
                key=(parts[0],parts[1],int(row['connections']),row['server'])
                groups[key].append(float(row['responses_per_second']))
                repeat_ids[key].append(int(row['repeat']))
    if not groups:
        raise SystemExit('No network runs.csv found')
    args.out.mkdir(parents=True,exist_ok=True)
    rows=[]
    for (dev,host,c,server),values in sorted(groups.items()):
        rows.append(dict(device=dev,host_run=host,connections=c,server=server,
                         repeats=len(values),median_rps=median(values),
                         min_rps=min(values),max_rps=max(values)))
    with (args.out/'network_medians.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    lookup={(r['device'],r['host_run'],r['connections'],r['server']):r for r in rows}
    speed=[]
    for r in rows:
        if r['server']!='io_uring':continue
        baseline=lookup.get((r['device'],r['host_run'],r['connections'],'epoll'))
        key=(r['device'],r['host_run'],r['connections'])
        uring_ids=repeat_ids[(*key,'io_uring')]
        epoll_ids=repeat_ids[(*key,'epoll')]
        # Keep all CSV summaries; chart only complete, matched experiments.
        complete=(r['connections'] in (1,100,1000)
                  and len(uring_ids) >= 10 and len(epoll_ids) >= 10
                  and len(set(uring_ids)) == len(uring_ids)
                  and len(set(epoll_ids)) == len(epoll_ids)
                  and set(uring_ids) == set(epoll_ids)
                  and all(i > 0 for i in uring_ids)
                  and all(isfinite(v) and v > 0
                          for engine in ('epoll','io_uring')
                          for v in groups[(*key,engine)]))
        if complete and baseline and baseline['median_rps']:
            speed.append(dict(device=r['device'],host_run=r['host_run'],connections=r['connections'],
                              speedup=r['median_rps']/baseline['median_rps']))
    speed.sort(key=lambda r:(r['connections'],r['device'],r['host_run']))
    if speed:
        write_bar_chart(args.out/'network_speedup.svg',
            'TCP loopback io_uring / epoll throughput', 'Median RPS ratio (1x = equal)',
            [f"{r['device']} / {r['connections']} connections" for r in speed],
            [r['speedup'] for r in speed], reference=1.0)
    else:
        # Do not leave a previous successful chart looking like current output.
        (args.out/'network_speedup.svg').unlink(missing_ok=True)
    print(f'Network median CSV: {args.out}; chart includes {len(speed)} complete experiments')

if __name__=='__main__':main()
