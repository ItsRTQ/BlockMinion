"""Run the unit tests and surface failures as GitHub annotations (readable through the API when the raw
job log is not reachable). Exit status mirrors unittest."""
import re, subprocess, sys
proc = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], capture_output=True, text=True)
out = proc.stdout + proc.stderr
print(out[-20000:])
for m in re.finditer(r"^(FAIL|ERROR): (\S+) \(([^)]+)\)\n-+\n(?:Traceback.*?\n)?(.*?)(?=\n\n(?:FAIL|ERROR|Ran |-{10}))", out, re.S | re.M):
    kind, name, loc, body = m.groups()
    last = [l for l in body.strip().splitlines() if l.strip()][-1:] or ["?"]
    msg = (last[0][:300]).replace("\n", " ")
    print(f"::error title={kind} {name}::{loc} — {msg}")
if proc.returncode and "::error" not in "\n".join(l for l in out.splitlines() if l.startswith("::error")) and not re.search(r"^(FAIL|ERROR): ", out, re.M):
    # The run died outside unittest's FAIL/ERROR report (import crash, encoding error, discovery failure): surface the tail.
    tail = " | ".join(l.strip() for l in out.strip().splitlines()[-6:])
    print(f"::error title=unittest crashed::{tail[:900]}")
sys.exit(proc.returncode)
