@echo off
setlocal
set "PYTHONDONTWRITEBYTECODE=1"
where py >nul 2>nul
if not errorlevel 1 (
    py -3 "%~dp0code\run_process.py" --mode ideal --run %*
    goto done
)
if exist "D:\SEMulator3D9\runtime\python\v3.6\NT40_x64\python.exe" (
    "D:\SEMulator3D9\runtime\python\v3.6\NT40_x64\python.exe" "%~dp0code\run_process.py" --mode ideal --run %*
    goto done
)
python "%~dp0code\run_process.py" --mode ideal --run %*
:done
set "PROCESS_TUTORIAL_EXIT=%errorlevel%"
pause
exit /b %PROCESS_TUTORIAL_EXIT%
