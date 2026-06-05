@echo off
setlocal

cd /d "%~dp0"

echo Stopping module3 PRODUCTION Docker Compose...
docker compose -f docker-compose.prod.yml down

endlocal
