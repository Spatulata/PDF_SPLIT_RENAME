@echo off
setlocal

set "BASE=%~dp0"
set "EXE="

if exist "%BASE%split_pdf_by_titul.exe" set "EXE=%BASE%split_pdf_by_titul.exe"
if not defined EXE if exist "%BASE%dist\split_pdf_by_titul.exe" set "EXE=%BASE%dist\split_pdf_by_titul.exe"

if not defined EXE (
    echo split_pdf_by_titul.exe not found.
    echo Expected: dist\split_pdf_by_titul.exe
    echo Run build_windows.bat first.
    pause
    exit /b 1
)

if "%~1"=="" (
    echo.
    echo  Split PDF by title pages
    echo  -----------------------
    echo  Drag and drop a PDF file onto this bat file.
    echo.
    echo  Or from command line:
    echo    run_split.bat "C:\path\to\scan.pdf"
    echo.
    pause
    exit /b 1
)

echo Using: %EXE%
echo Input file: %~1
echo.

"%EXE%" "%~1"
set ERR=%ERRORLEVEL%

echo.
if %ERR% EQU 0 (
    echo Done. Output is in the *_split folder next to the source PDF.
) else (
    echo Finished with error code %ERR%.
)
echo.
pause
exit /b %ERR%
