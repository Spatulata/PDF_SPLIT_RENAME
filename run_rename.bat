@echo off
setlocal

set "BASE=%~dp0"
set "EXE="

if exist "%BASE%dist\rename_pdfs_by_titul.exe" set "EXE=%BASE%dist\rename_pdfs_by_titul.exe"
if not defined EXE if exist "%BASE%rename_pdfs_by_titul.exe" set "EXE=%BASE%rename_pdfs_by_titul.exe"

if not defined EXE (
    echo rename_pdfs_by_titul.exe not found.
    echo Expected: rename_pdfs_by_titul.exe  or  dist\rename_pdfs_by_titul.exe
    echo Run build_windows.bat first.
    pause
    exit /b 1
)

if "%~1"=="" (
    echo.
    echo  Rename PDFs by title page number + name
    echo  --------------------------------------
    echo  Drag and drop a FOLDER with PDFs onto this bat file.
    echo.
    echo  Result example:
    echo    1360.443291.2002 Поддон шасси ВЧ-генератора.pdf
    echo.
    echo  Or from command line:
    echo    run_rename.bat "C:\path\to\folder_split"
    echo.
    pause
    exit /b 1
)

if not exist "%~1\" (
    echo.
    echo Error: need a FOLDER, not a file.
    echo You dropped: %~1
    echo.
    pause
    exit /b 1
)

echo Using: %EXE%
echo Folder: %~1
echo.

"%EXE%" "%~1"
set ERR=%ERRORLEVEL%

echo.
if %ERR% EQU 0 (
    echo Done. Files renamed in the same folder.
) else (
    echo Finished with error code %ERR%.
)
echo.
pause
exit /b %ERR%
