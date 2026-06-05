@echo off
setlocal

cd /d "%~dp0"

echo Starting module3 with Docker Compose...
docker compose --env-file .env up --build --force-recreate app

endlocal
