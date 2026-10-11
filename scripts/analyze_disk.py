#!/usr/bin/env python3
"""Read fio JSONs, export summary CSVs and SVG plots without external packages."""
import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from statistics import median

from svg_plot import write_bar_chart

NAME_RE = re.compile(r'^(?P<scenario>.+)__(?P<engine>psync|libaio|io_uring)__run(?P<repeat>\d+)\.json$')

def rows_from_fio(root: Path):
    records = []
    for src in sorted(root.glob('*/*/disk/*.json')):
        match = NAME_RE.match(src.name)
        if not match:
            continue
        try:
            data = json.loads(src.read_text())
            jobs = data['jobs']
            if not jobs or any(j.get('error', 0) != 0 for j in jobs):
                raise ValueError('fio recorded job errors or no jobs')
            # With group_reporting, fio ordinarily emits a single aggregated job.
            # Multiple jobs can sum throughput/IOPS but latency below is a weighted mean.
            bw = sum(j.get('read', {}).get('bw_bytes', 0) for j in jobs)
            iops = sum(j.get('read', {}).get('iops', 0) for j in jobs)
            weights = [max(0, j.get('read', {}).get('total_ios', 0)) for j in jobs]
            lat_values = [j.get('read', {}).get('clat_ns', {}).get('mean') for j in jobs]
            if not bw or not iops or not all(x is not None for x in lat_values):
                raise ValueError('missing read bw/iops/clat in JSON')
            lat_us = (sum(w * v for w, v in zip(weights, lat_values)) / sum(weights) / 1000
                      if sum(weights) else sum(lat_values)/len(lat_values)/1000)
            device = src.relative_to(root).parts[0]
            records.append({
                'device': device, 'host_run': src.relative_to(root).parts[1],
                'scenario': match['scenario'], 'engine': match['engine'],
                'repeat': int(match['repeat']), 'bw_MiB_s': bw / 1048576,
                'iops': iops, 'clat_mean_us': lat_us, 'source': str(src),
            })
        except (KeyError, ValueError, json.JSONDecodeError, OSError) as ex:
            print(f'SKIP {src}: {ex}')
    return records

def write_csv(path: Path, rows: list[dict]):
    if not rows:
        return
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

def plot_bar(rows: list[dict], outdir: Path, field: str, filename: str, ylabel: str):
    items = sorted(rows, key=lambda r: (r['host_run'], r['scenario'], r['engine']))
    labels = [f"{r['device']}/{r['host_run']} / {r['scenario']} / {r['engine']}" for r in items]
    write_bar_chart(outdir / filename, f'Disk fio median: {field}', ylabel,
                    labels, [r[field] for r in items])

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path('results'))
    parser.add_argument('--out', type=Path, default=Path('charts'))
    args = parser.parse_args()
    args.out.mkdir(exist_ok=True, parents=True)
    raw = rows_from_fio(args.root)
    if not raw:
        raise SystemExit('No fio JSON results found in results/<device>/<host-run>/disk/*.json')
    write_csv(args.out / 'disk_runs.csv', raw)
    groups = defaultdict(list)
    for r in raw:
        groups[(r['device'], r['host_run'], r['scenario'], r['engine'])].append(r)
    medians = []
    for (device, host_run, scenario, engine), group in sorted(groups.items()):
        medians.append(dict(device=device, host_run=host_run, scenario=scenario, engine=engine,
                            repeats=len(group),
                            bw_MiB_s=median(r['bw_MiB_s'] for r in group),
                            iops=median(r['iops'] for r in group),
                            bw_min_MiB_s=min(r['bw_MiB_s'] for r in group),
                            bw_max_MiB_s=max(r['bw_MiB_s'] for r in group),
                            clat_min_us=min(r['clat_mean_us'] for r in group),
                            clat_max_us=max(r['clat_mean_us'] for r in group),
                            clat_mean_us=median(r['clat_mean_us'] for r in group)))
    write_csv(args.out / 'disk_medians.csv', medians)
    plot_bar(medians, args.out, 'bw_MiB_s', 'disk_throughput.svg', 'MiB/s')
    plot_bar(medians, args.out, 'clat_mean_us', 'disk_clatency.svg', 'Mean completion latency (µs)')
    lookup = {(r['device'], r['host_run'], r['scenario'], r['engine']):r for r in medians}
    speedups = []
    for r in medians:
        if r['engine'] != 'io_uring':
            continue
        baseline = 'psync' if r['scenario'] in ('cached_qd1','short_qd1') else 'libaio'
        b = lookup.get((r['device'],r['host_run'],r['scenario'],baseline))
        if not b or not b['bw_MiB_s']:
            continue
        speedups.append(dict(device=r['device'], host_run=r['host_run'], scenario=r['scenario'],
                             baseline=baseline, speedup=r['bw_MiB_s']/b['bw_MiB_s'],
                             n_uring=r['repeats'], n_baseline=b['repeats']))
    write_csv(args.out / 'disk_speedups.csv', speedups)
    if speedups:
        write_bar_chart(args.out / 'disk_speedup.svg',
            'io_uring throughput / baseline throughput', 'Speedup ratio (1x = equal)',
            [f"{r['device']}/{r['host_run']} / {r['scenario']} vs {r['baseline']}" for r in speedups],
            [r['speedup'] for r in speedups], reference=1.0)
    print(f'Parsed {len(raw)} runs; wrote CSV and charts to {args.out}')

if __name__ == '__main__':
    main()
