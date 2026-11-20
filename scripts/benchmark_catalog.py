"""20 clients, 100 catalog requests. Use only an isolated local evaluation server."""
import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--url', default='http://127.0.0.1:8766/')
parser.add_argument('--output', required=True)
args = parser.parse_args()
url = urlsplit(args.url)
if url.scheme != 'http' or url.hostname not in ('localhost', '127.0.0.1') or url.query or url.fragment:
    parser.error('Usá un servidor local aislado, sin query ni fragmento.')

def hit(index):
    start = time.perf_counter()
    try:
        with urlopen(args.url + '?page=' + str(index % 20 + 1), timeout=30) as response:
            response.read()
            status = response.status
        return {'seconds': time.perf_counter() - start, 'status': status}
    except Exception as exc:
        return {'seconds': time.perf_counter() - start, 'status': 'error', 'error_type': type(exc).__name__}

with ThreadPoolExecutor(max_workers=20) as pool:
    results = list(pool.map(hit, range(100)))
durations = sorted(row['seconds'] for row in results)
report = {'concurrent_clients': 20, 'requests': 100, 'p95_seconds': durations[94],
          'median_seconds': statistics.median(durations), 'errors': sum(row['status'] != 200 for row in results),
          'request_results': results}
report['passed'] = report['errors'] == 0 and report['p95_seconds'] < 3
Path(args.output).write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({key: value for key, value in report.items() if key != 'request_results'}))
