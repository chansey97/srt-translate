@echo off
setlocal
set "PORTABLE_EXIT=1"

if not "%OS%"=="Windows_NT" (
    echo ERROR: This script requires Windows.
    goto finish
)

pushd "%~dp0"
if errorlevel 1 goto finish

set "PORTABLE_PYTHON=%CD%\.venv\Scripts\python.exe"
set "PYINSTALLER_CONFIG_DIR=%CD%\build\portable\cache"
if not exist "%PORTABLE_PYTHON%" (
    echo ERROR: .venv\Scripts\python.exe was not found. See README.md for build setup.
    goto failed
)

"%PORTABLE_PYTHON%" -c "import sys, sysconfig; sys.exit(0 if sys.platform == 'win32' and sysconfig.get_platform() == 'win-amd64' else 'ERROR: Windows x64 Python is required.')"
if errorlevel 1 goto failed

"%PORTABLE_PYTHON%" -m PyInstaller --version
if errorlevel 1 (
    echo ERROR: PyInstaller is unavailable. Install requirements-build.txt first.
    goto failed
)

"%PORTABLE_PYTHON%" -m PyInstaller ^
    --noconfirm --clean --onedir --console ^
    --name srt-translate ^
    --distpath dist ^
    --workpath build\portable\work ^
    --specpath build\portable ^
    --paths "%CD%\src" ^
    --add-data "%CD%\src\srt_translate\config.default.toml:srt_translate" ^
    --collect-submodules openai ^
    --copy-metadata httpx2 --copy-metadata httpcore2 ^
    portable_entry.py
if errorlevel 1 goto failed

copy /y "src\srt_translate\config.default.toml" "dist\srt-translate\config.toml" >nul
if errorlevel 1 goto failed
copy /y "README.md" "dist\srt-translate\README.md" >nul
if errorlevel 1 goto failed

"%PORTABLE_PYTHON%" -c "import shutil; shutil.make_archive('dist/srt-translate-windows-x64', 'zip', 'dist', 'srt-translate')"
if errorlevel 1 goto failed

echo Built dist\srt-translate\ and dist\srt-translate-windows-x64.zip
set "PORTABLE_EXIT=0"
goto cleanup

:failed
echo ERROR: Portable build failed. See the error above.

:cleanup
popd

:finish
if not defined CI pause
exit /b %PORTABLE_EXIT%
