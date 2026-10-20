# EcoGuardian AI

Plataforma educativa ambiental desarrollada con Python y Streamlit. Este repositorio está pensado para guardar el código y continuar el desarrollo; **no representa una certificación de seguridad ni una versión lista para producción**.

## Funciones incluidas en esta versión

- Aplicación Streamlit con acceso por roles.
- EcoAventura y juegos educativos ambientales disponibles en el código de esta entrega.
- EcoReto en modo individual con preguntas, temporizador, puntuación y retroalimentación.
- Perfil de usuario y persistencia local mediante SQLite.
- Pruebas automatizadas para funciones principales.

Las funciones disponibles y sus límites se describen en [`ESTADO_Y_LIMITACIONES.md`](ESTADO_Y_LIMITACIONES.md) y en los documentos de notas de la entrega. En particular, EcoReto aún no implementa una competición sincronizada entre varios dispositivos mediante código de sala.

## Requisitos

- Python 3.10 o posterior.
- `pip`.

## Instalación local

### Windows (PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
streamlit run app.py
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
streamlit run app.py
```

También se incluyen los scripts `iniciar_windows.bat` e `iniciar_mac_linux.sh`.

## Configuración inicial

1. Edita `.env` localmente y define `ECOGUARDIAN_SETUP_KEY` con un secreto largo, aleatorio y exclusivo para tu instalación.
2. No compartas el archivo `.env` ni publiques su contenido. `.env` está excluido de Git por `.gitignore`.
3. Inicia la aplicación y crea la cuenta de administrador usando la clave de configuración y una contraseña robusta.
4. Guarda la base de datos y las copias de seguridad en una ubicación privada. Los datos de usuarios no deben subirse a GitHub.

**Importante:** revisa cómo la versión actual lee la configuración antes de asumir que todas las variables de `.env` se cargan automáticamente. `.env.example` es una plantilla, no una garantía de configuración de producción.

## Ejecutar las pruebas

Instala las dependencias de desarrollo y ejecuta:

```bash
python -m pip install -r requirements-dev.txt
python -m py_compile app.py
pytest -q
```

Las pruebas son una comprobación básica, no una prueba integral de interfaz, cámara, micrófono, permisos en todos los escenarios o despliegue.

## Estructura principal

```text
app.py                         Aplicación Streamlit
requirements.txt               Dependencias de ejecución
requirements-dev.txt           Dependencias de pruebas
.env.example                   Plantilla de configuración
.streamlit/config.toml         Configuración de Streamlit
 tests/                         Pruebas automatizadas
 ESTADO_Y_LIMITACIONES.md      Estado y limitaciones conocidas
```

## Subir a un repositorio privado de GitHub

1. Crea un repositorio **Private** en GitHub. Para este proyecto puedes llamarlo `ecoguardian-ai`.
2. Abre una terminal en esta carpeta del proyecto.
3. Inicializa Git y revisa los archivos antes del primer commit:

```bash
git init
git status
git add .
git status
git commit -m "Preparar EcoGuardian AI para desarrollo"
git branch -M main
git remote add origin https://github.com/TU-USUARIO/ecoguardian-ai.git
git push -u origin main
```

Sustituye `TU-USUARIO` por tu usuario real. GitHub puede pedir autenticación mediante navegador o un administrador de credenciales; no pongas contraseñas ni tokens dentro de la URL o de los archivos.

Antes de `git add .`, confirma que `.env`, bases de datos, archivos subidos por usuarios, entornos virtuales y secretos estén ignorados. Si ya se publicó un secreto por accidente, eliminar el archivo del último commit no basta: revoca o cambia el secreto.

## Antes de publicar la aplicación en internet

Esta entrega no debe considerarse lista para producción. Revisa como mínimo las limitaciones sobre sesiones y tokens en URL, autorización de recursos, recuperación de cuentas, adjuntos, base de datos, copias de seguridad y competición en tiempo real que aparecen en `ESTADO_Y_LIMITACIONES.md`. Un repositorio privado controla quién ve el código, pero no protege automáticamente una aplicación desplegada.

## Licencia

No se declara una licencia de código abierto en esta entrega. Si más adelante deseas hacer público el repositorio, define primero qué licencia y condiciones de reutilización corresponden al proyecto.

---

## Novedades de la versión 17 · «Ecológico & Arquitectónico»

Esta versión rediseña la interfaz y añade el sistema de campeonatos en vivo. El código nuevo vive en el paquete `eco/`:

| Módulo | Qué hace |
|---|---|
| `eco/engine.py` | Categorías, niveles, **anti-copia** (opciones barajadas por usuario), puntuación y desempates. Sin Streamlit. |
| `eco/seed.py` | Banco inicial: 140 preguntas (4 categorías × 4 niveles × 4 tipos) + 8 retos de estimación. |
| `eco/store.py` | SQLite: banco editable, historial «visto», interruptores de juegos/niveles, puntajes. Sin Streamlit. |
| `eco/arena.py` | Salas con PIN, rondas, velocidad, **empates con repetición de ronda**, ranking y equipos. Sin Streamlit. |
| `eco/theme.py` | Fondo de bosque, vidrio, logotipo, barra superior y avatar circular. |
| `eco/media.py` | Efectos de sonido y ambiente sintetizados (sin archivos), ranking animado, siluetas, avatar narrador. |
| `eco/pages.py` | Páginas: biblioteca, arena, misiones, globo, interruptores, editor de preguntas, «Acerca de». |

**Navegación:** ya no hay barra lateral. La barra superior tiene Biblioteca · Arena · Acerca de y, a la derecha, solo la foto circular; al pulsarla se abre el menú del rol (estudiante, docente o administrador), el interruptor de sonido, el perfil y «Cerrar sesión».

**Persistencia:** todo (preguntas, interruptores, salas, puntajes) se guarda en `ecoguardian.sqlite3`. En hosts con disco efímero (p. ej. Streamlit Community Cloud) ese archivo se reinicia al redesplegar: para producción usa un volumen persistente o respalda el archivo con la exportación JSON del editor de preguntas.

**Pruebas:**
```bash
pip install pytest
pytest tests/                       # todo (las pruebas de humo se omiten si Streamlit real está instalado)
python tests/run_standalone.py test_eco_core test_smoke_ui   # sin pytest
```

## EcoParty · modo de fiesta multijugador

La biblioteca incorpora **EcoParty**, una colección de minijuegos rápidos de educación ambiental con puntuación y partidas de hasta 12 jugadores.

- **Mismo dispositivo:** partida por turnos, con nombres configurables y marcador local.
- **En línea:** el anfitrión crea una sala con PIN y los demás jugadores se conectan desde sus propias sesiones.
- **Minijuegos:** separación de residuos, ahorro de energía y agua, biodiversidad, clima, reutilización, océanos, compostaje, movilidad, consumo responsable y cuidado del entorno escolar.
- **Rondas y puntuación:** preguntas con límite de tiempo, puntos por acierto con bonificación por rapidez, resultado y clasificación final.
- **Sincronización:** las rondas y respuestas online se almacenan en las tablas `eco_party_*`; el servidor controla el cierre de ronda para evitar que cada navegador avance por separado.

**Límite importante de despliegue:** para que los dispositivos se encuentren entre sí, deben acceder a la misma instalación de EcoGuardian AI y a una base de datos compartida y persistente. Una instalación local ejecutada en el computador de cada jugador no crea por sí sola una sala en internet. La sincronización está diseñada para sondeo periódico de Streamlit; no es una conexión WebSocket dedicada.
