@echo off
chcp 65001 >nul
title FlySky - Drone Anahtari Ata
python "%~dp0flysky_bridge.py" --assign-spawn
pause
