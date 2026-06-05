@echo off
setlocal

cd /d "%~dp0"

echo Stopping module3 Docker Compose...
docker compose down

endlocal
