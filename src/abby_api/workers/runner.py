from __future__ import annotations

import logging
import time

logging.basicConfig(level=logging.INFO, format="[abby-worker] %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("Placeholder Abby worker started. Integrate Celery/RQ tasks here.")
    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
