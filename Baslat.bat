@echo off
chcp 65001 >nul
title FlySky - Bodycam Kopru
python "%~dp0flysky_bridge.py"
pause
