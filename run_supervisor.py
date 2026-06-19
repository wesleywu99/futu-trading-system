"""Supervisor: restarts the trading system if it crashes.

Usage:
    python run_supervisor.py

The supervisor starts src.main as a subprocess and monitors it.
If the process exits unexpectedly, it restarts after a delay.
"""

import os
import sys
import time
import subprocess
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] supervisor: %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
MAX_RESTARTS = 50
RESTART_DELAY_SEC = 30


def main():
    restart_count = 0

    while restart_count < MAX_RESTARTS:
        logger.info(f"Starting trading system (attempt {restart_count + 1}/{MAX_RESTARTS})...")
        start_time = datetime.now()

        proc = subprocess.Popen(
            [sys.executable, "-m", "src.main"],
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        # Stream output to log
        try:
            for line in proc.stdout:
                sys.stdout.write(line)
                sys.stdout.flush()
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt — terminating...")
            proc.terminate()
            proc.wait(timeout=10)
            return

        ret_code = proc.wait()
        uptime = (datetime.now() - start_time).total_seconds()

        if ret_code == 0:
            logger.info(f"Process exited cleanly (uptime={uptime:.0f}s). Stopping supervisor.")
            return

        logger.warning(
            f"Process crashed with code {ret_code} (uptime={uptime:.0f}s). "
            f"Restarting in {RESTART_DELAY_SEC}s..."
        )
        time.sleep(RESTART_DELAY_SEC)
        restart_count += 1

    logger.error(f"Max restarts ({MAX_RESTARTS}) reached. Giving up.")


if __name__ == "__main__":
    main()
