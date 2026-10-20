# Historial de cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).

## [1.2.0] - 2026-10-20

Robustez ante cortes de comunicación. **Cambia el protocolo (`WCP1` → `WCP2`)**:
las versiones 1.0.x y 1.2 no se entienden entre sí; actualizar ambos PCs.

### Añadido
- Reanudación a mitad de archivo: el receptor guarda `archivo.<size>.<mtime>.wcp-part`
  y responde `ok` / `resume` (+`offset`) / `skip` tras la cabecera, antes de recibir datos.
- Reintento automático del emisor (hasta 5 fallos seguidos, espera 1-15 s); avanzar
  en un intento reinicia el contador.
- TCP keepalive y timeout de 30 s (antes 120 s): un cable/Wi-Fi caído se detecta en segundos.
- Interfaz: la barra de estado muestra "Reconectando…", y al terminar indica
  "Completado" o "Interrumpido — pulsa Iniciar para reanudar".
- Tests de transferencia: envío, salto de existentes, reanudación, origen cambiado,
  reconexión tras corte (proxy) y PIN incorrecto sin reintentos.

### Cambiado
- Los archivos se escriben como `.wcp-part` y se renombran al terminar: nunca queda
  un archivo a medias con su nombre final.
- Un parcial solo se reanuda si tamaño y fecha del origen no cambiaron; si no, se descarta.
- El receptor ya no registra `[OK] Sesión` cuando el cliente se cae: registra
  "Conexión perdida" (y que se puede reanudar).
- El progreso incluye los archivos saltados (la barra llega al 100 %) y se actualiza en cada salto.
- El emisor valida el `offset` recibido y trata un cierre del receptor como corte (reintenta),
  no como error de archivo.

### Corregido
- `except:` desnudos y bytes contados aunque fallara el guardado en la propuesta de cliente.

## [1.0.1] - 2026-10-20
- Pipeline de GitHub Actions que compila `WCP.exe` portable (PyInstaller) con versión y SHA256.

## [1.0.0] - 2026-10-20
- Versión inicial: src-layout, licencia dual MIT OR Apache-2.0, tests de protocolo.
