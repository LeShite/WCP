# Historial de cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).

## [1.6.0] - 2026-10-20

### Añadido
- Interfaz nueva con CustomTkinter (tema oscuro cálido, barra superior, tarjetas) y vista **Ajustes**.
- **Carpetas de destino por defecto** en Ajustes: Escritorio, Descargas, Documentos, Música y Fotos.
  Al recibir, cada carpeta del origen se guarda en la suya (o en una sola carpeta si se desactiva el interruptor).
- El emisor también envía la carpeta **Música**.
- Preferencias en `~/.wcp_config.json` (puerto por defecto, última IP, carpetas de destino).
- **Ajustes → Apariencia e idioma**: color de interfaz (Oscuro cálido, Azul, Negro, Blanco, Verde, Morado) e idioma (Español / English). Se aplican al guardar; con un envío o recepción activos, al reiniciar.
- Ajustes → Acerca de: licencias MIT y Apache 2.0, y un apartado reservado «Cuenta KODECOUNT» (aún sin función).
- Dependencia nueva: `customtkinter`.

## [1.5.0] - 2026-10-20

### Añadido
- Si un archivo ya existe en el destino y es distinto, una ventana emergente pregunta
  **Omitir / Sobrescribir / Cancelar**, con la casilla "Aplicar a todos los siguientes".
  La decisión se recuerda: una reconexión no vuelve a preguntar. Sin interfaz se sobrescribe.
- El receptor espera hasta 10 min entre mensajes (antes 30 s) para dar tiempo a decidir;
  el keepalive TCP sigue detectando un emisor caído.

### Eliminado
- El filtro de `WCP*.exe` de 1.4.0: lo sustituye la ventana de conflicto.

## [1.4.0] - 2026-10-20

### Cambiado
- El emisor omite los ejecutables de WCP (`WCP*.exe`, sin distinguir mayúsculas) con un aviso
  en el registro. En el receptor, `WCP.exe` en uso no se puede sobrescribir (`WinError 5`).
  No se filtran otros `.exe`: copiar instaladores es un uso legítimo.

## [1.3.1] - 2026-10-20

### Corregido
- `WinError 10053` con reconexiones en bucle: un fallo local del receptor en un solo
  archivo (antivirus, archivo bloqueado u oculto como `desktop.ini`, ruta larga) cerraba la
  conexión y el emisor lo veía como corte de red. Ahora el receptor consume los datos de ese
  archivo, registra `[!] No se pudo guardar <archivo>: <error>` y continúa; el renombrado
  final se reintenta 4 veces y quita atributos de solo lectura/oculto en Windows.
- Un archivo bloqueado o ilegible en el origen se omite con aviso en vez de abortar
  y reintentar como si fuera un corte de red.
- El resumen final indica cuántos archivos fallaron; al volver a pulsar Iniciar solo se reintentan esos.
- Los errores del receptor ahora incluyen el tipo de excepción.

## [1.3.0] - 2026-10-20

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

### Rendimiento
- Antes: ~0,8 MB/s en uso real; 1000 archivos de 10 KB tardaban más de 2 minutos.
  Causas: dos `sendall` por mensaje (bloqueo Nagle + ACK retardado, ~40-200 ms por
  mensaje) y un viaje de ida y vuelta por archivo.
- Ahora: `TCP_NODELAY` y mensaje en un solo envío; el emisor manda un *plan* por lotes de
  2000 archivos y el receptor responde cuáles faltan (`-1` = ya completo, `n` = desde el byte n);
  luego se envía todo seguido sin acuses por archivo. Acuse final obligatorio.
- Medido en loopback: 1000 archivos de 10 KB en 0,24 s (reenvío de lo ya copiado: 0,06 s).
- Un archivo de destino dañado (tamaño/fecha distintos) se detecta y se reconstruye.

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
