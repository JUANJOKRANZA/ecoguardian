# Audio de Balloon Bash

Los archivos de audio se encuentran en `eco/web/balloon_host/assets/` y se cargan desde el panel del profesor:

- `fun-game.mp3`: música del lobby.
- `hitslab-game.mp3`: música durante la tensión de la partida.
- `adventure-loop.mp3`: música durante la revelación de resultados.
- `balloon-inflate.mp3`: efecto real de globo inflándose al bombear.

Estos MP3 fueron proporcionados por el usuario en esta conversación. Antes de publicar EcoGuardian AI en Internet, conserva y verifica las licencias y condiciones de uso aplicables a cada pista. La disponibilidad de un archivo no garantiza por sí sola derechos de redistribución pública.

## Compatibilidad y pruebas

El audio empieza después de pulsar «Activar sonido y narrador», porque los navegadores pueden bloquear la reproducción automática. El botón táctil de inflado está disponible durante la fase de juego incluso si se activa el sensor de movimiento.

Se ejecutaron las pruebas automatizadas del proyecto: `71 passed`. También se comprobó la sintaxis JavaScript con Node.js y la compilación de módulos Python. Aún debe hacerse una prueba manual en Safari/iOS y Chrome/Android, y una partida completa con varios dispositivos en el despliegue HTTPS real antes de considerarlo listo para producción.
