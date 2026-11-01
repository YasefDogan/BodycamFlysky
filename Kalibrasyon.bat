@echo off
chcp 65001 >nul
title FlySky - Calibration
python "%~dp0flysky_bridge.py" --calibrate
pause
