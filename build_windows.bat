@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo  Build portable tools (same folder)
echo ============================================
echo.

set "PYEXE="
set "PYARGS="

REM Prefer Python 3.14 / 3.13 / 3.12 (любой рабочий)
for %%P in (
    "%LocalAppData%\Programs\Python\Python314\python.exe"
    "%LocalAppData%\Programs\Python\Python313\python.exe"
    "%LocalAppData%\Programs\Python\Python312\python.exe"
    "%LocalAppData%\Programs\Python\Python311\python.exe"
    "C:\Python314\python.exe"
    "C:\Python313\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
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

REM Python Launcher
where py >nul 2>&1
if not errorlevel 1 (
    py -3.14 -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        set "PYEXE=py"
        set "PYARGS=-3.14"
        goto found_python
    )
    py -3.13 -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        set "PYEXE=py"
        set "PYARGS=-3.13"
        goto found_python
    )
    py -3.12 -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        set "PYEXE=py"
        set "PYARGS=-3.12"
        goto found_python
    )
    py -3.11 -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        set "PYEXE=py"
        set "PYARGS=-3.11"
        goto found_python
    )
    py -3 -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        set "PYEXE=py"
        set "PYARGS=-3"
        goto found_python
    )
)

REM python on PATH
where python >nul 2>&1
if not errorlevel 1 (
    python -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        set "PYEXE=python"
        set "PYARGS="
        goto found_python
    )
)

echo [ERROR] No working Python found.
echo.
echo Recommended: Python from https://www.python.org/downloads/
echo During install check: Add python.exe to PATH
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

pip install -r requirements-build.txt --force-reinstall
if errorlevel 1 goto install_fail

echo.
echo Cleaning old build artifacts...
if exist build rmdir /S /Q build
if exist dist rmdir /S /Q dist

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

REM Portable layout: exe в корне папки рядом с tesseract\
copy /Y "dist\split_pdf_by_titul.exe" ".\split_pdf_by_titul.exe" >nul
copy /Y "dist\rename_pdfs_by_titul.exe" ".\rename_pdfs_by_titul.exe" >nul

echo.
echo ============================================
echo  Done! Portable folder ready:
echo.
echo    %cd%
echo.
echo    run_split.bat
echo    run_rename.bat
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
echo Try:
echo   1. Delete folder .venv in this directory
echo   2. Run build_windows.bat again
echo.
pause
exit /b 1
