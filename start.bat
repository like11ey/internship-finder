@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo   ========================================
echo   实习岗位智能筛查工具
echo   ========================================
echo.
echo   正在启动 Web 服务...
echo.
python main.py --web
pause
