@echo off
setlocal
chcp 65001 >nul
echo WINDOW - conectar este computador a la instalacion
echo.
echo Asegurate de que este computador y el anfitrion usen la misma red.
echo En el anfitrion, ejecuta ipconfig y busca Direccion IPv4.
echo.
set /p HOST_IP=Escribe la IPv4 del anfitrion (ejemplo 192.168.1.20): 
if not defined HOST_IP (
  echo No escribiste una direccion.
  pause
  exit /b 1
)
start "" "http://%HOST_IP%:8765"
endlocal