@echo off
setlocal

cd /d "%~dp0"

echo Starting module3 in PRODUCTION mode with Docker Compose...
docker compose -f docker-compose.prod.yml --env-file .env up --build -d app

endlocal
