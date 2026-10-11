#!/usr/bin/env python3
"""Read fio JSONs, export summary CSVs and SVG plots without external packages."""
import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from math import isfinite
from statistics import median
from analysis_common import CURRENT, SCENARIOS, methodology, stats, complete, session_config, verify_expected

from svg_plot import write_bar_chart

NAME_RE = re.compile(r'^(?P<scenario>.+)__(?P<engine>traditional|psync|libaio|io_uring)__run(?P<repeat>\d+)\.json$')

def rows_from_fio(root: Path, legacy=False, device=None):
    pattern = f'{device or "*"}/*/disk/'
    records = []
    sessions = {}
    if not legacy:
        for meta in root.glob(pattern+'metadata.txt'):
            if methodology(meta.parent) == CURRENT: sessions[meta.parent] = session_config(meta.parent)
    for src in sorted(root.glob(pattern+'*.json')):
        method = methodology(src.parent)
        if method != ('legacy' if legacy else CURRENT): continue
        if not legacy and src.parent not in sessions:
            sessions[src.parent] = session_config(src.parent)
        match = NAME_RE.match(src.name)
        if not match:
            if not legacy: raise ValueError(f'Unexpected JSON filename: {src}')
            continue
        if not legacy and (match['engine'] not in ('traditional','io_uring') or match['scenario'] not in SCENARIOS): raise ValueError(f'Unexpected workload/engine: {src}')
        try:
            data = json.loads(src.read_text(encoding='utf-8'))
            jobs = data['jobs']
            if not jobs or any(j['error'] != 0 for j in jobs):
                raise ValueError('fio recorded job errors or no jobs')
            if not legacy:
                expected = 32 if match['engine'] == 'traditional' and match['scenario'] == 'random_direct_qd32' else 1
                if len(jobs) != expected: raise ValueError(f'Expected {expected} ungrouped jobs, found {len(jobs)}')
                if any(not isfinite(j['read'][field]) or j['read'][field] <= 0 for j in jobs for field in ('total_ios','bw_bytes','iops')):
                    raise ValueError('A worker completed no reads')
            # With group_reporting, fio ordinarily emits a single aggregated job.
            # Multiple jobs can sum throughput/IOPS but latency below is a weighted mean.
            bw = sum(j.get('read', {}).get('bw_bytes', 0) for j in jobs)
            iops = sum(j.get('read', {}).get('iops', 0) for j in jobs)
            weights = [j.get('read', {}).get('total_ios', 0) for j in jobs]
            lat_values = [j.get('read', {}).get('clat_ns', {}).get('mean') for j in jobs]
            if not bw or not iops or not all(x is not None for x in lat_values):
                raise ValueError('missing read bw/iops/clat in JSON')
            if not all(isfinite(v) and v >= 0 for v in [bw, iops, *lat_values, *weights]):
                raise ValueError('invalid nonfinite/negative metrics')
            lat_us = (sum(w * v for w, v in zip(weights, lat_values)) / sum(weights) / 1000
                      if sum(weights) else sum(lat_values)/len(lat_values)/1000)
            device = src.relative_to(root).parts[0]
            records.append({
                'methodology': method, 'device': device, 'host_run': src.relative_to(root).parts[1],
                'scenario': match['scenario'], 'engine': match['engine'],
                'repeat': int(match['repeat']), 'bw_MiB_s': bw / 1048576,
                'iops': iops, 'clat_mean_us': lat_us, 'source': str(src),
            })
        except (KeyError, ValueError, json.JSONDecodeError, OSError) as ex:
            raise ValueError(f'Invalid fio result {src}: {ex}') from ex
    for directory, config in sessions.items():
        scenarios=config['scenarios'].split()
        if not scenarios or any(s not in SCENARIOS for s in scenarios): raise ValueError(f'Invalid scenarios: {directory}')
        actual=[(r['scenario'],r['engine'],r['repeat']) for r in records if Path(r['source']).parent == directory]
        verify_expected(actual, scenarios, int(config['repeats']), directory)
    return records

def write_csv(path: Path, rows: list[dict]):
    if not rows:
        path.unlink(missing_ok=True)
        return
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

def plot_bar(rows: list[dict], outdir: Path, field: str, filename: str, ylabel: str):
    items = sorted(rows, key=lambda r: (r['host_run'], r['scenario'], r['engine']))
    labels = [f"{r['scenario']} / {r['engine']} / {r['device']}/{r['host_run']}" for r in items]
    write_bar_chart(outdir / filename, f'Disk fio median: {field}', ylabel,
                    labels, [r[field] for r in items])

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path('results'))
    parser.add_argument('--out', type=Path, default=Path('charts'))
    parser.add_argument('--legacy', action='store_true', help='Analyze only original methodology, in a separate output directory')
    parser.add_argument('--device', help='Explicitly select one device label; summaries still separate host sessions')
    args = parser.parse_args()
    if args.device and not re.fullmatch(r'[A-Za-z0-9_-]+', args.device): parser.error('Invalid device label')
    if args.legacy: args.out = args.out / 'legacy'
    args.out.mkdir(exist_ok=True, parents=True)
    for name in ('disk_runs.csv','disk_medians.csv','disk_speedups.csv','disk_throughput.svg','disk_clatency.svg','disk_speedup.svg'):
        (args.out / name).unlink(missing_ok=True)
    raw = rows_from_fio(args.root, args.legacy, args.device)
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
                            bw_cv_percent=100*stats([r['bw_MiB_s'] for r in group])['stddev']/stats([r['bw_MiB_s'] for r in group])['mean'],
                            clat_min_us=min(r['clat_mean_us'] for r in group),
                            clat_max_us=max(r['clat_mean_us'] for r in group),
                            clat_mean_us=median(r['clat_mean_us'] for r in group)))
    for row in medians:
        group = groups[(row['device'], row['host_run'], row['scenario'], row['engine'])]
        for field in ('bw_MiB_s', 'iops', 'clat_mean_us'):
            row.update({f'{field}_{name}': value for name, value in stats([r[field] for r in group]).items()})
    write_csv(args.out / 'disk_medians.csv', medians)
    chart_rows = []
    for row in medians:
        key = (row['device'], row['host_run'], row['scenario'])
        base = ('psync' if row['scenario'] in ('cached_qd1','short_qd1') else 'libaio') if args.legacy else 'traditional'
        pair = [groups.get((*key, engine), []) for engine in (base, 'io_uring')]
        if all(complete([r['repeat'] for r in g], [r['bw_MiB_s'] for r in g]) for g in pair) and {r['repeat'] for r in pair[0]} == {r['repeat'] for r in pair[1]}:
            chart_rows.append(row)
    for name in ('disk_throughput.svg', 'disk_clatency.svg', 'disk_speedup.svg'):
        (args.out / name).unlink(missing_ok=True)
    plot_bar(chart_rows, args.out, 'bw_MiB_s', 'disk_throughput.svg', 'MiB/s')
    plot_bar(chart_rows, args.out, 'clat_mean_us', 'disk_clatency.svg', 'Mean completion latency (us)')
    lookup = {(r['device'], r['host_run'], r['scenario'], r['engine']):r for r in medians}
    speedups = []
    for r in chart_rows:
        if r['engine'] != 'io_uring':
            continue
        baseline = ('psync' if r['scenario'] in ('cached_qd1','short_qd1') else 'libaio') if args.legacy else 'traditional'
        b = lookup.get((r['device'],r['host_run'],r['scenario'],baseline))
        if not b or not b['bw_MiB_s']:
            continue
        speedups.append(dict(device=r['device'], host_run=r['host_run'], scenario=r['scenario'],
                             baseline=baseline, percent_difference=100*(r['bw_MiB_s']/b['bw_MiB_s']-1), mean_percent_difference=100*(r['bw_MiB_s_mean']/b['bw_MiB_s_mean']-1), speedup=r['bw_MiB_s']/b['bw_MiB_s'],
                             n_uring=r['repeats'], n_baseline=b['repeats']))
    write_csv(args.out / 'disk_speedups.csv', speedups)
    if speedups:
        write_bar_chart(args.out / 'disk_speedup.svg',
            'io_uring throughput / baseline throughput', 'Speedup ratio (1x = equal)',
            [f"{r['scenario']} vs {r['baseline']} / {r['device']}/{r['host_run']}" for r in speedups],
            [r['speedup'] for r in speedups], reference=1.0)
    print(f'Parsed {len(raw)} runs; {len(speedups)} complete comparisons; CSV summaries in {args.out}')

if __name__ == '__main__':
    main()
