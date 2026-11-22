@echo off
cd /d "%~dp0"
set "PYTHON_CMD="
py -3 --version >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py -3"
if not defined PYTHON_CMD (
  python --version >nul 2>&1
  if not errorlevel 1 set "PYTHON_CMD=python"
)
if not defined PYTHON_CMD (
  echo No encuentro Python 3 en este computador anfitrion.
  echo Instala Python 3 y vuelve a abrir Iniciar_WINDOW.bat.
  pause
  exit /b 1
)
powershell -NoProfile -Command "$c=New-Object Net.Sockets.TcpClient; try {$c.Connect('127.0.0.1',8765); exit 0} catch {exit 1} finally {$c.Close()}" >nul 2>&1
if not errorlevel 1 (
  echo WINDOW ya esta funcionando en el puerto 8765.
  echo Cierra la ventana WINDOW-servidor anterior antes de volver a iniciar.
  pause
  exit /b 1
)
start "WINDOW-servidor" /D "%~dp0" cmd /k "%PYTHON_CMD% server.py"
set "ATTEMPTS=0"
:wait
powershell -NoProfile -Command "$c=New-Object Net.Sockets.TcpClient; try {$c.Connect('127.0.0.1',8765); exit 0} catch {exit 1} finally {$c.Close()}" >nul 2>&1
if not errorlevel 1 goto ready
set /a ATTEMPTS+=1
if %ATTEMPTS% geq 20 goto failed
timeout /t 1 /nobreak >nul
goto wait
:ready
start "" "http://localhost:8765"
echo WINDOW esta lista. Deja abierta la ventana WINDOW-servidor.
echo En los otros equipos usa Conectar_a_WINDOW.bat e introduce la IPv4 de este equipo.
pause
exit /b 0
:failed
echo No se pudo iniciar el servidor. Revisa la ventana WINDOW-servidor.
pause