from datetime import datetime
from pathlib import Path

import pytest


RUN_DIR = Path(__file__).resolve().parents[2] / "test_outputs" / "live" / datetime.now().strftime("%Y%m%d_%H%M%S_%f")


@pytest.fixture(scope="session")
def live_run_dir():
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    return RUN_DIR


def pytest_terminal_summary(terminalreporter):
    terminalreporter.write_sep("=", f"Live API artifacts (retained): {RUN_DIR}")

