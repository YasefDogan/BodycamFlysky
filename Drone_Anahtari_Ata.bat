@echo off
chcp 65001 >nul
title FlySky - Assign Drone Switch
python "%~dp0flysky_bridge.py" --assign-spawn
pause
