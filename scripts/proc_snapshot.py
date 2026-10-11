"""Linux process counters for diagnostic deltas, not a benchmark rate."""
import json, os, sys, time
from pathlib import Path
pid=int(sys.argv[1])
root=Path('/proc')/str(pid)
# comm can contain spaces/parentheses; split after the final closing parenthesis.
fields=(root/'stat').read_text().rsplit(')',1)[1].split()
status=dict(line.split(':',1) for line in (root/'status').read_text().splitlines() if ':' in line)
print(json.dumps(dict(pid=pid,monotonic_seconds=time.monotonic(),
    cpu_user_seconds=int(fields[11])/os.sysconf('SC_CLK_TCK'),
    cpu_system_seconds=int(fields[12])/os.sysconf('SC_CLK_TCK'),
    threads=int(fields[17]),rss_pages=int(fields[21]),
    voluntary_context_switches=int(status.get('voluntary_ctxt_switches',0)),
    nonvoluntary_context_switches=int(status.get('nonvoluntary_ctxt_switches',0)))))
