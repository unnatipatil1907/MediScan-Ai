@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Creating Python virtual environment...
    py -m venv .venv
    if errorlevel 1 (
        echo Could not create the virtual environment. Install Python 3 and retry.
        pause
        exit /b 1
    )
)
call ".venv\Scripts\activate.bat"
python -c "import streamlit, pandas, numpy, pypdf" >nul 2>&1
if errorlevel 1 (
    echo Installing project dependencies. Internet access is required for first setup.
    python -m pip install --upgrade pip
    if errorlevel 1 goto install_failed
    python -m pip install -r requirements.txt
    if errorlevel 1 goto install_failed
)
python -m streamlit run app.py
if errorlevel 1 (
    echo.
    echo Streamlit exited with an error. Read the message above.
    pause
)
exit /b 0

:install_failed
echo.
echo Dependency installation failed. Check internet/DNS and see README_FIRST.txt.
pause
exit /b 1
