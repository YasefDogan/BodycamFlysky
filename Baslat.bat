@echo off
chcp 65001 >nul
title FlySky - Bodycam Bridge
python "%~dp0flysky_bridge.py"
pause
