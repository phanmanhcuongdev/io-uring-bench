"""Shared statistics and methodology selection; no third-party dependencies."""
from statistics import mean, median, stdev
from math import isfinite

def methodology(directory):
    path = directory / 'metadata.txt'
    if not path.exists(): return 'legacy'
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.startswith('methodology='): return line.split('=', 1)[1]
    return 'legacy'

def stats(values):
    return dict(mean=mean(values), median=median(values),
                stddev=stdev(values) if len(values) > 1 else 0.0)

def complete(ids, values):
    return (len(ids) >= 10 and len(ids) == len(set(ids)) and
            all(i > 0 for i in ids) and all(isfinite(v) and v > 0 for v in values))

CURRENT = 'traditional-v2'
SCENARIOS = ('cached_qd1','short_qd1','random_direct_qd32','sequential_direct_qd1')

def session_config(directory):
    status = directory / 'status.txt'
    if not status.exists() or status.read_text().strip() != 'complete':
        raise ValueError(f'Failed, running or unverified session: {directory}')
    config = dict(line.split('=',1) for line in (directory/'metadata.txt').read_text(encoding='utf-8').splitlines() if '=' in line)
    repeats = int(config['repeats'])
    if repeats < 1: raise ValueError(f'Invalid repeats in {directory}')
    return config

def verify_expected(actual, scenarios, repeats, directory):
    expected={(scenario,engine,i) for scenario in scenarios for engine in ('traditional','io_uring') for i in range(1,repeats+1)}
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise ValueError(f'Duplicate, missing or unexpected measurements in {directory}; missing={sorted(expected-set(actual))}, unexpected={sorted(set(actual)-expected)}')
