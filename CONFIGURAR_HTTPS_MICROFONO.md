# EcoGuardian AI — activar el micrófono en los ordenadores de estudiantes

## Por qué ocurre
Los navegadores solo permiten `getUserMedia()` en un contexto seguro. `http://localhost:8501`
se considera seguro únicamente en el mismo ordenador que ejecuta el navegador. Si un estudiante
entra por `http://192.168.x.x:8501`, esa IP por HTTP no es un contexto seguro y el micrófono se bloquea.

## Recomendación para el colegio
Publicar Streamlit detrás de HTTPS con un nombre interno estable y un certificado que los
ordenadores del colegio confíen. Este paquete incluye `Caddyfile.HTTPS.ejemplo` como punto de partida.

1. Asigna al servidor una IP reservada y un nombre DNS interno, por ejemplo `ecoguardian.colegio`.
2. Instala Caddy en el servidor.
3. Ajusta el nombre del `Caddyfile` al nombre DNS real. El bloque `tls internal` crea un certificado
   emitido por la autoridad local de Caddy.
4. Inicia Streamlit solo en la máquina servidor, en el puerto 8501, y configura Caddy para reenviar
   a `127.0.0.1:8501`.
5. Confía la CA raíz de Caddy en el almacén de certificados de confianza de TODOS los ordenadores
   que usarán el micrófono. En Windows esto normalmente requiere permisos de administrador del colegio.
6. Comprueba en cada ordenador que la URL abre como `https://NOMBRE-REAL/`, sin advertencia de
   certificado. Aceptar una advertencia temporal no es una solución adecuada para un despliegue escolar.
7. En Chrome/Edge, permite el micrófono para ese sitio y comprueba que no esté bloqueado por políticas
   del navegador o por el sistema operativo.

`ecoguardian.colegio.test` es un ejemplo y no funcionará hasta configurar DNS y certificados.
No se puede activar HTTPS de confianza de forma universal solo cambiando Python: depende del nombre
del servidor, certificados y configuración de los equipos cliente.

## Canecas
En Inicio, cada una de las cuatro canecas es ahora un botón. Al seleccionarla, aparece debajo su
descripción, ejemplos y recomendación; se puede cerrar la ficha con el botón correspondiente.
