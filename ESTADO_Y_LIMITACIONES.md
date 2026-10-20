# EcoGuardian AI — estado de esta entrega parcial

Esta carpeta contiene la versión disponible del proyecto, con las correcciones de EcoScan, EcoSilencio y retroalimentación del modo restringido incorporadas en `app.py`.

## Pruebas realizadas en el entorno de preparación

- `python -m py_compile app.py`: aprobado.
- `pytest -q`: 9 pruebas aprobadas.
- Se comprobó la integridad estructural del ZIP después de empaquetarlo.

Estas pruebas no equivalen a una prueba integral de toda la plataforma. No se pudo ejecutar el servidor Streamlit en el entorno disponible ni probar cámara, micrófono, correo, concurrencia multiusuario o despliegue real.

## Limitaciones importantes pendientes

1. **No es una plataforma multicolegio completa.** El proyecto actual usa SQLite local y no proporciona aislamiento institucional completo con roles, cursos y políticas de acceso a nivel de servidor.
2. **Sesiones:** la sesión persistente utiliza el parámetro de consulta `eg_session`. Los tokens de sesión en URL pueden filtrarse mediante historial, capturas o registros; antes de uso público debe migrarse a cookies seguras HttpOnly/Secure/SameSite o a un mecanismo equivalente compatible con el despliegue.
3. **Recuperación de cuentas y correo:** no se ha integrado un flujo completo con tokens de un solo uso, SMTP verificado y límites de solicitudes.
4. **Chat y adjuntos:** hay mensajería básica, pero no se ha verificado ni completado un sistema de adjuntos privados con escaneo, límites y autorización por descarga.
5. **Campeonatos:** no se ha demostrado un sistema competitivo multiusuario en tiempo real, con sincronización, reconexión y validación autoritativa del servidor.
6. **Banco de preguntas:** los retos existentes no equivalen todavía a un banco persistente de preguntas vistas por estudiante con ciclo de agotamiento, revisión docente y publicación controlada por IA.
7. **Base de datos y operación:** no se ha migrado a PostgreSQL, ni se han probado migraciones, concurrencia, respaldo y restauración de producción.
8. **EcoScan:** clasificador experimental basado en reglas de imagen/palabras; no es un modelo de IA entrenado y no identifica residuos peligrosos con fiabilidad.
9. **EcoSilencio:** la lectura del micrófono es relativa y depende del navegador y del dispositivo; no es un sonómetro certificado.

## Instalación local

1. Instalar Python 3.10 o superior.
2. Abrir una terminal en esta carpeta.
3. Crear un entorno virtual: `python -m venv .venv`.
4. Activarlo en Windows: `.venv\\Scripts\\activate`; en macOS/Linux: `source .venv/bin/activate`.
5. Instalar dependencias: `python -m pip install -r requirements.txt`.
6. Ejecutar `streamlit run app.py`.

Configura `ECOGUARDIAN_SETUP_KEY` antes del primer arranque y crea una contraseña de administrador fuerte. No publiques la aplicación en internet sin abordar primero las limitaciones de seguridad anteriores.

## Copias de seguridad

Detén la aplicación y copia `ecoguardian.sqlite3` a una ubicación privada y restringida. Para restaurar, detén la aplicación y reemplaza el archivo con una copia verificada. No se incluye ninguna base de datos de usuario en este ZIP.

## Resultado

Entrega parcial con mejoras y pruebas limitadas. No declarar como cumplidos los requisitos completos del prompt maestro ni considerar esta versión lista para producción.

## Versión 17: qué está verificado y qué no

**Verificado con pruebas automáticas:** reglas de juego, anti-copia, selección sin repetición, interruptores, editor de preguntas (validación e importación), máquina de estados de la Arena (cierre idempotente entre conexiones, bonos, empates exactos y con ventana, repeticiones limitadas), y que cada página de cada rol se ejecuta sin excepciones con un Streamlit simulado.

**No verificado en un navegador real con Streamlit:** el aspecto exacto de los widgets nativos (el avatar circular y los botones de colores dependen de selectores `st-key-*` de Streamlit ≥ 1.39), la reproducción de audio (los navegadores exigen un primer clic) y la voz del avatar (depende de las voces en español instaladas en el dispositivo). Revisa estas tres cosas en tu entorno antes de usarlo en clase.

**Límites conocidos:**
- La velocidad se mide en el servidor al procesar el clic; no compensa la latencia de cada dispositivo. Para empates, el docente puede elegir una ventana de ±5/20/50 ms.
- El sondeo es de 1 s por sesión sobre SQLite: pensado para aulas (decenas de jugadores), no para cientos simultáneos.
- Las «imágenes enfrentadas» usan emojis (sin archivos externos); algunos sistemas antiguos pueden mostrar símbolos distintos.
- Las cifras de los retos de estimación son aproximadas y se indican así en pantalla.
- Un menú del avatar abierto no se cierra solo tras elegir una opción (limitación de `st.popover`).

## Refuerzo de notificaciones v18.1

La campana conserva el sondeo interno de 4 segundos y se añadió una opción voluntaria para avisos del navegador mientras la aplicación está abierta. El texto del aviso del sistema es genérico por privacidad. Ver `CAMBIOS_NOTIFICACIONES_V18_1.txt` para el alcance y las pruebas.

**No equivale a Web Push.** No se garantiza entrega con la pestaña cerrada o el navegador detenido. Para esa capacidad se necesita un service worker con alcance válido, un endpoint de suscripciones, claves VAPID, un backend de envío y persistencia de suscripciones. La opción del navegador tampoco se ha validado visualmente en un navegador real desde este entorno.


## EcoParty (añadido en esta revisión)
- Incluye modo local por turnos y modo online con PIN, hasta 12 jugadores, 12 minijuegos ambientales y clasificación.
- La suite automatizada cubre capacidad, registro de respuesta, puntuación y avance de rondas.
- El modo online requiere una única instalación accesible por todos y almacenamiento compartido/persistente. No se ha probado con 12 dispositivos físicos ni bajo carga.
- La sincronización usa actualizaciones periódicas de Streamlit, no WebSockets dedicados.


## Música ambiental (v23)

Reproductor persistente en el documento principal del navegador; ver `CAMBIOS_MUSICA_AMBIENTAL_V23.txt`.
Verificado con pruebas simuladas y en Chromium con un anfitrión que imita el protocolo de componentes;
pendiente de comprobación manual con Streamlit real, Safari e iOS/Android.
