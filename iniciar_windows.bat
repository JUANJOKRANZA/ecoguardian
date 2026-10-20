@echo off
REM Lanzador de EcoGuardian AI (doble clic). Requiere Python 3.10+ instalado.
cd /d "%~dp0"
if not exist venv (
    echo Creando entorno e instalando librerias, solo la primera vez...
    python -m venv venv
    call venv\Scripts\activate.bat
    python -m pip install --upgrade pip
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)
if not defined ECOGUARDIAN_SETUP_KEY (
    echo Primera configuracion: escribe una clave inicial larga y guardala temporalmente.
    echo La misma clave se escribe una vez en el formulario web para crear el administrador.
    set /p ECOGUARDIAN_SETUP_KEY=Clave inicial de configuracion: 
)
echo Abriendo EcoGuardian AI en el navegador...
streamlit run app.py --server.address 0.0.0.0
pause
