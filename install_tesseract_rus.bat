@echo off
setlocal
cd /d "%~dp0"

set "URL=https://github.com/tesseract-ocr/tessdata/raw/main/rus.traineddata"
set "TARGET="

if exist "C:\Program Files\Tesseract-OCR\tessdata" (
    set "TARGET=C:\Program Files\Tesseract-OCR\tessdata\rus.traineddata"
)
if not defined TARGET if exist "C:\Program Files (x86)\Tesseract-OCR\tessdata" (
    set "TARGET=C:\Program Files (x86)\Tesseract-OCR\tessdata\rus.traineddata"
)
if not defined TARGET if exist "%~dp0tesseract\tessdata" (
    set "TARGET=%~dp0tesseract\tessdata\rus.traineddata"
)
if not defined TARGET if exist "%~dp0dist\tesseract\tessdata" (
    set "TARGET=%~dp0dist\tesseract\tessdata\rus.traineddata"
)

if not defined TARGET (
    echo [ERROR] tessdata folder not found.
    echo Install Tesseract first:
    echo   https://github.com/UB-Mannheim/tesseract/wiki
    pause
    exit /b 1
)

if exist "%TARGET%" (
    echo rus.traineddata already exists:
    echo   %TARGET%
    pause
    exit /b 0
)

echo Downloading Russian language pack...
echo Target: %TARGET%
echo.

powershell -NoProfile -Command ^
  "try { Invoke-WebRequest -Uri '%URL%' -OutFile '%TARGET%' -UseBasicParsing; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"

if errorlevel 1 (
    echo.
    echo [ERROR] Download failed.
    echo Download manually and copy to tessdata folder:
    echo   %URL%
    pause
    exit /b 1
)

echo.
echo Done: %TARGET%
echo Now run run_split.bat again.
echo.
pause
