@echo off
setlocal
cd /d "%~dp0"

set "URL=https://github.com/tesseract-ocr/tessdata/raw/main/rus.traineddata"
set "PORTABLE=%~dp0tesseract\tessdata"
set "TARGET=%PORTABLE%\rus.traineddata"

if not exist "%PORTABLE%" (
    echo Creating portable tessdata folder...
    mkdir "%PORTABLE%"
)

if exist "%TARGET%" (
    echo rus.traineddata already exists in portable folder:
    echo   %TARGET%
    pause
    exit /b 0
)

if exist "C:\Program Files\Tesseract-OCR\tessdata\rus.traineddata" (
    echo Copying rus.traineddata from Program Files to portable folder...
    copy /Y "C:\Program Files\Tesseract-OCR\tessdata\rus.traineddata" "%TARGET%" >nul
    if exist "%TARGET%" (
        echo Done: %TARGET%
        pause
        exit /b 0
    )
)

if exist "C:\Program Files (x86)\Tesseract-OCR\tessdata\rus.traineddata" (
    echo Copying rus.traineddata from Program Files x86 to portable folder...
    copy /Y "C:\Program Files (x86)\Tesseract-OCR\tessdata\rus.traineddata" "%TARGET%" >nul
    if exist "%TARGET%" (
        echo Done: %TARGET%
        pause
        exit /b 0
    )
)

echo Downloading Russian language pack to portable folder...
echo Target: %TARGET%
echo.

powershell -NoProfile -Command ^
  "try { Invoke-WebRequest -Uri '%URL%' -OutFile '%TARGET%' -UseBasicParsing; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"

if errorlevel 1 (
    echo.
    echo [ERROR] Download failed.
    echo Copy manually to:
    echo   %TARGET%
    echo From:
    echo   %URL%
    pause
    exit /b 1
)

echo.
echo Done: %TARGET%
echo Now run run_split.bat again.
echo.
pause
