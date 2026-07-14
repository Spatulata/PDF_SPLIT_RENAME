@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo  Build portable tools (same folder)
echo ============================================
echo.

set "PYEXE="
set "PYARGS="

REM 1) Python Launcher (best on Windows)
where py >nul 2>&1
if not errorlevel 1 (
    py -3 -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        set "PYEXE=py"
        set "PYARGS=-3"
        goto found_python
    )
)

REM 2) python on PATH
where python >nul 2>&1
if not errorlevel 1 (
    python -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        set "PYEXE=python"
        set "PYARGS="
        goto found_python
    )
)

REM 3) Common python.org install paths
for %%P in (
    "%LocalAppData%\Programs\Python\Python313\python.exe"
    "%LocalAppData%\Programs\Python\Python312\python.exe"
    "%LocalAppData%\Programs\Python\Python311\python.exe"
    "%LocalAppData%\Programs\Python\Python310\python.exe"
    "C:\Python313\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
    "C:\Python310\python.exe"
) do (
    if exist %%P (
        %%P -c "import sys" >nul 2>&1
        if not errorlevel 1 (
            set "PYEXE=%%P"
            set "PYARGS="
            goto found_python
        )
    )
)

echo [ERROR] No working Python found.
echo.
echo FIX:
echo   1. Install Python from https://www.python.org/downloads/
echo   2. Check: Add python.exe to PATH
echo   3. Turn OFF Store aliases for python.exe / python3.exe
echo   4. Open a NEW cmd and run build_windows.bat again
echo.
pause
exit /b 1

:found_python
echo Using Python:
if defined PYARGS (
    %PYEXE% %PYARGS% --version
) else (
    "%PYEXE%" --version
)
echo %PYEXE% | findstr /I "WindowsApps" >nul
if not errorlevel 1 (
    echo.
    echo [WARNING] Microsoft Store Python detected.
    echo If build fails, install Python from python.org instead.
    echo.
)

if not exist ".venv" (
    echo Creating virtual environment...
    if defined PYARGS (
        %PYEXE% %PYARGS% -m venv .venv
    ) else (
        "%PYEXE%" -m venv .venv
    )
    if errorlevel 1 (
        echo [ERROR] Failed to create venv.
        goto python_help
    )
)

if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] venv was not created: .venv\Scripts\activate.bat missing
    goto python_help
)

call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] Failed to activate venv.
    goto python_help
)

echo Installing dependencies...
python -m pip install --upgrade pip
if errorlevel 1 goto install_fail

pip install -r requirements-build.txt
if errorlevel 1 goto install_fail

echo.
echo Building split_pdf_by_titul.exe ...
pyinstaller --clean --noconfirm split_pdf_by_titul.spec
if errorlevel 1 (
    echo [ERROR] Build split failed.
    pause
    exit /b 1
)

echo.
echo Building rename_pdfs_by_titul.exe ...
pyinstaller --noconfirm rename_pdfs_by_titul.spec
if errorlevel 1 (
    echo [ERROR] Build rename failed.
    pause
    exit /b 1
)

REM Portable layout: exe лежат в этой же папке рядом с tesseract\
copy /Y "dist\split_pdf_by_titul.exe" ".\split_pdf_by_titul.exe" >nul
copy /Y "dist\rename_pdfs_by_titul.exe" ".\rename_pdfs_by_titul.exe" >nul

echo.
echo ============================================
echo  Done! Portable folder ready:
echo.
echo    %cd%
echo.
echo    run_split.bat              - drag PDF
echo    run_rename.bat             - drag FOLDER
echo    split_pdf_by_titul.exe
echo    rename_pdfs_by_titul.exe
echo    tesseract\
echo ============================================
echo.
if not exist "tesseract\tesseract.exe" (
    echo [WARNING] tesseract\ not found next to exe.
    echo OCR will not work until you add portable tesseract here.
    echo.
)
pause
exit /b 0

:install_fail
echo [ERROR] Failed to install dependencies.
goto python_help

:python_help
echo.
echo Try installing Python from https://www.python.org/downloads/
echo NOT from Microsoft Store.
echo.
pause
exit /b 1
