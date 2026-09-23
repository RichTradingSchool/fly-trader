@echo off
rem 초파리 트레이딩 챌린지 - Windows 설치 도우미 (더블클릭)
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows-setup.ps1" %*
