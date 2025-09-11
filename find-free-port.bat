@echo off
echo Finding free port...

REM Try ports 8000-8010
for /L %%i in (8000,1,8010) do (
    netstat -an | findstr :%%i >nul
    if errorlevel 1 (
        echo Found free port: %%i
        set FREE_PORT=%%i
        goto :found
    )
)

echo No free port found in range 8000-8010, using 8000
set FREE_PORT=8000

:found
echo Using port: %FREE_PORT%
