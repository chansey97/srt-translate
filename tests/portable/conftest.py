import os
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest


@pytest.fixture(scope="session")
def portable_app(tmp_path_factory):
    if sys.platform != "win32":
        pytest.skip("Portable executable tests require Windows")
    root = Path(__file__).resolve().parents[2]
    archive = root / "dist" / "srt-translate-windows-x64.zip"
    assert archive.is_file(), "Run build_portable.bat before tests/portable"
    destination = tmp_path_factory.mktemp("portable") / "解压 portable 🎬"
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(destination)
    return destination / "srt-translate"


@pytest.fixture
def portable_config_file(portable_app):
    path = portable_app / "config.toml"
    original = path.read_bytes()
    yield path
    path.write_bytes(original)


@pytest.fixture
def run_portable(portable_app, portable_config_file, tmp_path):
    user_dir = tmp_path / "user" / "srt-translate"
    user_dir.mkdir(parents=True)
    (user_dir / "config.toml").write_text("invalid user config", encoding="utf-8")
    (tmp_path / "config.toml").write_text("invalid cwd config", encoding="utf-8")
    env = {
        **os.environ,
        "APPDATA": str(user_dir.parent), "LOCALAPPDATA": str(user_dir.parent),
        "PYTHONIOENCODING": "cp1252:strict", "PYTHONUTF8": "0",
        "PATH": str(Path(os.environ["SystemRoot"]) / "System32"),
        "NO_PROXY": "127.0.0.1,localhost",
    }
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)

    def run(*args, redirect=False):
        command = [str(portable_app / "srt-translate.exe"), *map(str, args)]
        if not redirect:
            return subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, timeout=60)
        stdout_path, stderr_path = tmp_path / "stdout.txt", tmp_path / "stderr.txt"
        with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
            result = subprocess.run(command, cwd=tmp_path, env=env, stdout=out, stderr=err, timeout=60)
        return subprocess.CompletedProcess(
            command, result.returncode, stdout_path.read_bytes(), stderr_path.read_bytes(),
        )

    return run
