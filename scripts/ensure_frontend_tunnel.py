#!/usr/bin/env python3
"""Wait for the project's supervised frontend tunnel, releasing a stale child."""
import os
import signal
import subprocess
import time
import urllib.error
import urllib.request


def main():
    deadline=time.monotonic()+45;released=set()
    while time.monotonic()<deadline:
        try:
            with urllib.request.urlopen('http://127.0.0.1:8080/',timeout=3) as response:
                if response.status==200:print('Frontend tunnel ready: HTTP200');return 0
        except urllib.error.HTTPError:
            pass  # An application response is not evidence of a stale tunnel.
        except (OSError,ConnectionError):
            probe=subprocess.run(['lsof','-t','-iTCP:8080','-sTCP:LISTEN'],text=True,capture_output=True)
            for value in set(probe.stdout.split()):
                if not value.isdigit() or value in released:continue
                process=subprocess.run(['ps','-p',value,'-o','command='],text=True,capture_output=True)
                command=process.stdout
                if all(x in command for x in ('kubectl','port-forward','front-end','8080:80','shyn-thesis')):
                    try:os.kill(int(value),signal.SIGTERM);released.add(value)
                    except ProcessLookupError:pass
        time.sleep(1)
    raise RuntimeError('Frontend tunnel unavailable; start scripts/port_forward.sh before soak')


if __name__=='__main__':raise SystemExit(main())
