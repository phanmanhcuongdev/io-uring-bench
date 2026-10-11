"""Synthetic fixtures only; these are not benchmark measurements."""
import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from analyze_disk import rows_from_fio
from analysis_common import stats

class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.results = self.root / 'results'
        self.out = self.root / 'charts'

    def disk(self, session, engine, repeat, workers=None, marker=True):
        folder = self.results / 'test' / session / 'disk'
        folder.mkdir(parents=True, exist_ok=True)
        if marker:
            (folder/'metadata.txt').write_text('methodology=traditional-v2\nrepeats=1\nscenarios=random_direct_qd32\n')
            (folder/'status.txt').write_text('complete')
        if workers is None: workers=32 if marker and engine=='traditional' else 1
        meta=folder/'metadata.txt'
        if marker:
            # Keep declared repeat count in sync while generating fixtures.
            ids=[int(p.stem.rsplit('run',1)[1]) for p in folder.glob('*.json')]
            meta.write_text(f'methodology=traditional-v2\nrepeats={max([repeat,*ids])}\nscenarios=random_direct_qd32\n')
        jobs = [{'error':0, 'read':{'bw_bytes':1048576, 'iops':256,
                 'total_ios':100, 'clat_ns':{'mean':2000}}} for _ in range(workers)]
        (folder/f'random_direct_qd32__{engine}__run{repeat:02}.json').write_text(json.dumps({'jobs':jobs}))

    def run_analyzer(self, kind, *args):
        return subprocess.run([sys.executable, str(ROOT/f'scripts/analyze_{kind}.py'),
                               '--root', str(self.results), '--out', str(self.out), *args],
                              capture_output=True, text=True, check=True)

    def test_sum_workers_and_exclude_entire_legacy_session(self):
        self.disk('new','traditional',1,32)
        self.disk('new','io_uring',1)
        self.disk('old','libaio',1,marker=False)
        self.disk('old','io_uring',1,marker=False)
        rows = rows_from_fio(self.results)
        self.assertEqual(len(rows),2)
        row=next(r for r in rows if r['engine']=='traditional')
        self.assertEqual(row['bw_MiB_s'],32)
        self.assertEqual(row['iops'],8192)
        self.assertEqual(row['clat_mean_us'],2)
        self.assertEqual({r['engine'] for r in rows_from_fio(self.results,True)}, {'libaio','io_uring'})

    def test_statistics_percentage_and_legacy_directory(self):
        for i in range(1,11):
            self.disk('new','traditional',i,32)
            self.disk('new','io_uring',i,1)
            for engine,bw in [('traditional',65536),('io_uring',3145728)]:
                path=self.results/'test/new/disk'/f'random_direct_qd32__{engine}__run{i:02}.json'
                data=json.loads(path.read_text())
                for job in data['jobs']: job['read']['bw_bytes']=bw
                path.write_text(json.dumps(data))
            self.disk('old','libaio',i,marker=False)
            self.disk('old','io_uring',i,marker=False)
        self.run_analyzer('disk')
        with (self.out/'disk_speedups.csv').open() as f: row=next(csv.DictReader(f))
        self.assertEqual(float(row['percent_difference']),50)
        with (self.out/'disk_medians.csv').open() as f: row=next(csv.DictReader(f))
        self.assertEqual(float(row['bw_MiB_s_stddev']),0)
        self.assertEqual(float(row['bw_MiB_s_mean']),3)
        self.assertTrue((self.out/'disk_throughput.svg').exists())
        self.run_analyzer('disk','--legacy')
        self.assertTrue((self.out/'legacy/disk_speedup.svg').exists())

    def test_sample_stddev(self):
        result=stats([1,2,3])
        self.assertEqual(result,dict(mean=2,median=2,stddev=1))

    def test_weighted_latency(self):
        self.disk('new','traditional',1,32)
        self.disk('new','io_uring',1)
        source=next(self.results.glob('*/*/disk/*__traditional__*.json'))
        data=json.loads(source.read_text())
        for i,job in enumerate(data['jobs']):
            job['read']['total_ios']=100 if i<16 else 300
            job['read']['clat_ns']['mean']=1000 if i<16 else 3000
        source.write_text(json.dumps(data))
        self.assertEqual(next(r for r in rows_from_fio(self.results) if r['engine']=='traditional')['clat_mean_us'],2.5)

    def test_disk_incomplete_pair_has_no_chart(self):
        self.disk('new','traditional',1)
        self.disk('new','io_uring',1)
        self.run_analyzer('disk')
        self.assertFalse((self.out/'disk_throughput.svg').exists())

    def network(self, session, marker=True, repeats=10, duplicate=False):
        folder=self.results/'loopback'/session/'network'
        folder.mkdir(parents=True,exist_ok=True)
        if marker:
            (folder/'metadata.txt').write_text(f'methodology=traditional-v2\nrepeats={repeats}\nconnections=100\nduration_sec=1\nmessage_bytes=512\n')
            (folder/'status.txt').write_text('complete')
        with (folder/'runs.csv').open('w',newline='') as f:
            writer=csv.writer(f)
            writer.writerow(['methodology','server','connections','repeat','rps','responses_per_second','raw_log','request_count','response_count','measurement_seconds','active_connections'])
            for server in (('traditional','io_uring') if marker else ('epoll','io_uring')):
                for i in range(1,repeats+1):
                    writer.writerow(['traditional-v2' if marker else '', server,100,1 if duplicate else i,120,100 if server in ('traditional','epoll') else 120,'fixture',120,100 if server in ('traditional','epoll') else 120,1,100])

    def test_network_complete_stats_and_legacy_exclusion(self):
        self.network('new')
        self.network('old',False)
        self.run_analyzer('network')
        with (self.out/'network_medians.csv').open() as f: rows=list(csv.DictReader(f))
        self.assertEqual(len(rows),2)
        self.assertEqual({r['server'] for r in rows},{'traditional','io_uring'})
        with (self.out/'network_speedups.csv').open() as f: row=next(csv.DictReader(f))
        self.assertAlmostEqual(float(row['percent_difference']),20)
        self.assertTrue((self.out/'network_speedup.svg').exists())
        self.run_analyzer('network','--legacy')
        self.assertTrue((self.out/'legacy/network_speedup.svg').exists())

    def test_network_duplicates_excluded_and_stale_chart_removed(self):
        self.network('new',duplicate=True)
        self.out.mkdir()
        (self.out/'network_speedup.svg').write_text('stale')
        with self.assertRaises(subprocess.CalledProcessError): self.run_analyzer('network')
        self.assertFalse((self.out/'network_speedup.svg').exists())

    def test_corrupt_disk_fails_instead_of_skipping(self):
        self.disk('new','traditional',1)
        self.disk('new','io_uring',1)
        next(self.results.glob('*/*/disk/*.json')).write_text('{broken')
        with self.assertRaises(subprocess.CalledProcessError): self.run_analyzer('disk')
        self.assertFalse((self.out/'disk_throughput.svg').exists())

    def test_missing_disk_measurement_fails(self):
        self.disk('new','traditional',1)
        with self.assertRaises(subprocess.CalledProcessError): self.run_analyzer('disk')

    def test_grouped_or_missing_workers_fails(self):
        self.disk('new','traditional',1,1)
        self.disk('new','io_uring',1)
        with self.assertRaises(subprocess.CalledProcessError): self.run_analyzer('disk')

    def test_failed_session_is_not_successful_analysis(self):
        self.network('new')
        next(self.results.glob('*/*/network/status.txt')).write_text('failed exit=1')
        with self.assertRaises(subprocess.CalledProcessError): self.run_analyzer('network')

    def test_network_counts_must_match_rate(self):
        self.network('new')
        source=next(self.results.glob('*/*/network/runs.csv'))
        text=source.read_text().replace(',fixture,120,100,1,100',',fixture,120,99,1,100',1)
        source.write_text(text)
        with self.assertRaises(subprocess.CalledProcessError): self.run_analyzer('network')

    def test_missing_network_csv_fails(self):
        self.network('new')
        next(self.results.glob('*/*/network/runs.csv')).unlink()
        with self.assertRaises(subprocess.CalledProcessError): self.run_analyzer('network')

    def test_svg_uses_median_not_mean(self):
        import xml.etree.ElementTree as ET
        for i in range(1,11):
            self.disk('new','traditional',i)
            self.disk('new','io_uring',i)
            for engine,bw in [('traditional',65536),('io_uring',1048576 if i<10 else 20971520)]:
                source=self.results/'test/new/disk'/f'random_direct_qd32__{engine}__run{i:02}.json'
                data=json.loads(source.read_text())
                for job in data['jobs']: job['read']['bw_bytes']=bw
                source.write_text(json.dumps(data))
        self.run_analyzer('disk')
        with (self.out/'disk_speedups.csv').open() as f: row=next(csv.DictReader(f))
        self.assertEqual(float(row['percent_difference']),-50)
        self.assertAlmostEqual(float(row['mean_percent_difference']),45)
        root=ET.parse(self.out/'disk_speedup.svg').getroot()
        texts=[''.join(e.itertext()) for e in root.iter() if e.tag.endswith('}text')]
        self.assertIn('0.500',texts)
        bars=[e for e in root.iter() if e.tag.endswith('}rect') and e.get('fill')=='#5675a2']
        self.assertEqual(len(bars),1)
        self.assertAlmostEqual(float(bars[0].get('width')),310.27,places=2)

    def test_explicit_device_selection_excludes_other_failed_label(self):
        self.network('good',repeats=1)
        failed=self.results/'failed/bad/network'
        failed.mkdir(parents=True)
        (failed/'metadata.txt').write_text('methodology=traditional-v2')
        (failed/'status.txt').write_text('failed exit=1')
        self.run_analyzer('network','--device','loopback')
        with (self.out/'network_medians.csv').open() as f: rows=list(csv.DictReader(f))
        self.assertEqual(len(rows),2)
        self.assertEqual({r['device'] for r in rows},{'loopback'})

if __name__ == '__main__': unittest.main()
