#!/usr/bin/env python3

import logging
from aqpy.ingest.config import load_config
from aqpy.ingest.service import run_ingest_loop


def main():
    config = load_config()
    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    run_ingest_loop()


if __name__ == "__main__":
    main()
