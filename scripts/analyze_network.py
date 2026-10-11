#!/usr/bin/env python3
"""Summarize network echo benchmark CSVs; dependency-free SVG plotting."""
import argparse, csv, re
from collections import defaultdict
from pathlib import Path
from statistics import median
from math import isfinite, isclose
from svg_plot import write_bar_chart
from analysis_common import CURRENT, methodology, stats, session_config, verify_expected

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,default=Path('results'))
    p.add_argument('--out',type=Path,default=Path('charts'))
    p.add_argument('--legacy',action='store_true',help='Analyze only legacy results separately')
    p.add_argument('--device',help='Explicitly select one device label')
    args=p.parse_args()
    if args.device and not re.fullmatch(r'[A-Za-z0-9_-]+',args.device): p.error('Invalid device label')
    pattern=f'{args.device or "*"}/*/network/'
    if args.legacy: args.out=args.out/'legacy'
    baseline_name='epoll' if args.legacy else 'traditional'
    args.out.mkdir(parents=True,exist_ok=True)
    for name in ('network_runs.csv','network_medians.csv','network_speedups.csv','network_speedup.svg'):
        (args.out/name).unlink(missing_ok=True)
    groups=defaultdict(list)
    repeat_ids=defaultdict(list)
    raw=[]
    if not args.legacy:
        for meta in args.root.glob(pattern+'metadata.txt'):
            if methodology(meta.parent) == CURRENT:
                session_config(meta.parent)
                if not (meta.parent/'runs.csv').is_file(): raise ValueError(f'Missing runs.csv: {meta.parent}')
    for src in args.root.glob(pattern+'runs.csv'):
        method=methodology(src.parent)
        if method != ('legacy' if args.legacy else CURRENT): continue
        config = None if args.legacy else session_config(src.parent)
        actual=[]
        parts=src.relative_to(args.root).parts
        with src.open(newline='') as f:
            for row in csv.DictReader(f):
                if not args.legacy and (row.get('methodology') != CURRENT or row['server'] not in ('traditional','io_uring')): raise ValueError(f'Invalid methodology/server in {src}')
                key=(parts[0],parts[1],int(row['connections']),row['server'])
                value=float(row['responses_per_second'])
                if not isfinite(value) or value <= 0: raise ValueError(f'Invalid throughput in {src}: {row}')
                if not args.legacy:
                    actual.append((int(row['connections']),row['server'],int(row['repeat'])))
                    seconds=float(row['measurement_seconds'])
                    responses=int(row['response_count']); requests=int(row['request_count'])
                    if (not isfinite(seconds) or seconds != float(config['duration_sec']) or seconds <= 0 or
                        int(row['active_connections']) != int(row['connections']) or
                        responses <= 0 or requests < responses or
                        not isclose(value,responses/seconds,rel_tol=1e-9,abs_tol=1e-5) or
                        not isclose(float(row['rps']),requests/seconds,rel_tol=1e-9,abs_tol=1e-5)):
                        raise ValueError(f'Rate/count/window/connection mismatch in {src}: {row}')
                groups[key].append(value)
                repeat_ids[key].append(int(row['repeat']))
                raw.append(dict(device=parts[0],host_run=parts[1],source=str(src),**row))
        if not args.legacy:
            verify_expected(actual, [int(c) for c in config['connections'].split()], int(config['repeats']), src.parent)
    if not groups:
        raise SystemExit('No network runs.csv found')
    args.out.mkdir(parents=True,exist_ok=True)
    with (args.out/'network_runs.csv').open('w',newline='') as f:
        fields=list(dict.fromkeys(field for row in raw for field in row))
        writer=csv.DictWriter(f,fieldnames=fields); writer.writeheader(); writer.writerows(raw)
    rows=[]
    for (dev,host,c,server),values in sorted(groups.items()):
        rows.append(dict(device=dev,host_run=host,connections=c,server=server,
                         repeats=len(values),median_rps=median(values),
                         min_rps=min(values),max_rps=max(values),
                         mean_rps=stats(values)["mean"],stddev_rps=stats(values)["stddev"],cv_percent=100*stats(values)['stddev']/stats(values)['mean']))
    with (args.out/'network_medians.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    lookup={(r['device'],r['host_run'],r['connections'],r['server']):r for r in rows}
    speed=[]
    for r in rows:
        if r['server']!='io_uring':continue
        baseline=lookup.get((r['device'],r['host_run'],r['connections'],baseline_name))
        key=(r['device'],r['host_run'],r['connections'])
        uring_ids=repeat_ids[(*key,'io_uring')]
        baseline_ids=repeat_ids[(*key,baseline_name)]
        # Keep all CSV summaries; chart only complete, matched experiments.
        complete=(r['connections'] in (1,100,1000)
                  and len(uring_ids) >= 10 and len(baseline_ids) >= 10
                  and len(set(uring_ids)) == len(uring_ids)
                  and len(set(baseline_ids)) == len(baseline_ids)
                  and set(uring_ids) == set(baseline_ids)
                  and all(i > 0 for i in uring_ids)
                  and all(isfinite(v) and v > 0
                          for engine in (baseline_name,'io_uring')
                          for v in groups[(*key,engine)]))
        if complete and baseline and baseline['median_rps']:
            speed.append(dict(device=r['device'],host_run=r['host_run'],connections=r['connections'],
                              baseline=baseline_name, percent_difference=100*(r['median_rps']/baseline['median_rps']-1),
                              mean_percent_difference=100*(r['mean_rps']/baseline['mean_rps']-1),
                              speedup=r['median_rps']/baseline['median_rps']))
    speed.sort(key=lambda r:(r['connections'],r['device'],r['host_run']))
    with (args.out/'network_speedups.csv').open('w',newline='') as f:
        if speed:
            w=csv.DictWriter(f,fieldnames=list(speed[0])); w.writeheader(); w.writerows(speed)
    if speed:
        write_bar_chart(args.out/'network_speedup.svg',
            f'TCP loopback io_uring / {baseline_name} throughput', 'Median RPS ratio (1x = equal)',
            [f"{r['connections']} connections / {r['device']}/{r['host_run']}" for r in speed],
            [r['speedup'] for r in speed], reference=1.0)
    else:
        # Do not leave a previous successful chart looking like current output.
        (args.out/'network_speedup.svg').unlink(missing_ok=True)
    print(f'Network median CSV: {args.out}; chart includes {len(speed)} complete experiments')

if __name__=='__main__':main()
