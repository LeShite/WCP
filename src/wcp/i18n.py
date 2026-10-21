"""Idioma de la interfaz y del motor: el texto fuente está en español."""
IDIOMAS = {"es": "Español", "en": "English"}
_lang = "es"

# Traducciones al inglés (clave = texto en español)
EN = {
    "Demasiados intentos, espera un minuto": "Too many attempts, wait a minute",
    "[!] Demasiados intentos desde {}": "[!] Too many attempts from {}",
    "El receptor no respondió a la solicitud": "The receiver did not answer the request",
    "▲  Enviar Archivos": "▲  Send Files", "▼  Recibir Archivos": "▼  Receive Files",
    "⚙️  Ajustes": "⚙️  Settings", "Enviar Archivos": "Send Files",
    "Recibir Archivos": "Receive Files", "Ajustes": "Settings",
    "Destino": "Destination", "Dirección IP / host": "IP address / host", "Buscar": "Search",
    "Puerto": "Port", "Carpetas": "Folders", "Escritorio": "Desktop", "Documentos": "Documents",
    "Descargas": "Downloads", "Música": "Music", "Fotos": "Photos", "NO EXISTE": "MISSING",
    "Iniciar envío": "Start sending", "Detener": "Stop", "Listo": "Ready", "Detenido": "Stopped",
    "Tu PC": "This PC", "Comparte estos datos con el origen.": "Share this info with the sender.",
    "Carpeta destino": "Destination folder",
    "Usar las carpetas de destino por defecto (Ajustes)": "Use the default destination folders (Settings)",
    "Una sola carpeta para todo": "A single folder for everything",
    "Iniciar recepción": "Start receiving",
    "Configuración general de WCP.": "General WCP settings.",
    "Apariencia e idioma": "Appearance and language", "Idioma:": "Language:",
    "Color de interfaz:": "Interface color:", "Red": "Network",
    "Puerto por defecto": "Default port",
    "Carpetas de destino por defecto": "Default destination folders",
    "Dónde guarda este PC lo que recibe de cada carpeta del origen. Se aplican al iniciar la recepción.":
        "Where this PC saves what it receives from each source folder. Applied when receiving starts.",
    "Acerca de WCP": "About WCP", "Versión": "Version",
    "Motor de transferencia: TCP con reanudación de archivos.": "Transfer engine: TCP with file resume.",
    "Desarrollado con Python y CustomTkinter.": "Built with Python and CustomTkinter.",
    "Licencias": "Licenses",
    "WCP se distribuye bajo cualquiera de las dos, a tu elección.":
        "WCP is distributed under either of the two, at your option.",
    "Cuenta KODECOUNT": "KODECOUNT account",
    "Próximamente: vincula tu cuenta de KODECOUNT con WCP.":
        "Coming soon: link your KODECOUNT account to WCP.",
    "Vincular cuenta": "Link account",
    "Guardar Cambios": "Save Changes", "✓  Guardado": "✓  Saved", "Puerto inválido": "Invalid port",
    "[i] Buscando servidores WCP en la red (2s)...": "[i] Looking for WCP servers on the network (2s)...",
    "[!] No se encontraron servidores": "[!] No servers found",
    "[OK] Encontrados: {}": "[OK] Found: {}",
    "Completa IP y PIN": "Enter IP and PIN",
    "Selecciona al menos una carpeta": "Select at least one folder",
    "Conectando...": "Connecting...",
    "{done}/{total} archivos · {db}/{tb} · {rate}/s": "{done}/{total} files · {db}/{tb} · {rate}/s",
    "Archivo existente": "Existing file",
    "El archivo ya existe en el destino y es distinto:":
        "The file already exists at the destination and is different:",
    "Aplicar a todos los siguientes": "Apply to all following",
    "Omitir": "Skip", "Sobrescribir": "Overwrite", "Cancelar": "Cancel",
    "Completado ✔": "Completed ✔",
    "Interrumpido — pulsa Iniciar para reanudar": "Interrupted — press Start to resume",
    "[!] Deteniendo...": "[!] Stopping...", "Elige carpeta destino": "Choose a destination folder",
    "Recibidos: {ok} · Saltados: {skip} · {b} · {rate}/s":
        "Received: {ok} · Skipped: {skip} · {b} · {rate}/s",
    "Escuchando...": "Listening...",
    # --- motor (envío / recepción) ---
    "[+] Conexión de {}": "[+] Connection from {}",
    "[!] Error: {}: {}": "[!] Error: {}: {}",
    "[ERROR] Servidor: {}": "[ERROR] Server: {}",
    "[.] Servidor detenido": "[.] Server stopped",
    "[OK] Escuchando en puerto {}": "[OK] Listening on port {}",
    "[i] Destino: {}": "[i] Destination: {}",
    "[!] Cliente no-WCP": "[!] Non-WCP client",
    "[!] PIN incorrecto": "[!] Wrong PIN",
    "[!] Envío rechazado: {} ({})": "[!] Transfer rejected: {} ({})",
    "[OK] Cliente '{}' autenticado": "[OK] Client '{}' authenticated",
    "[!] Conexión perdida: {} copiados, {} saltados (el cliente puede reanudar)":
        "[!] Connection lost: {} copied, {} skipped (the client can resume)",
    "[!] {} archivos no se pudieron guardar (ver líneas anteriores)":
        "[!] {} files could not be saved (see previous lines)",
    "[OK] Sesión: {} copiados, {} saltados, {:.1f} MB":
        "[OK] Session: {} copied, {} skipped, {:.1f} MB",
    "[!] No se pudo guardar {}: {}: {}": "[!] Could not save {}: {}: {}",
    "[!] No existe: {}": "[!] Does not exist: {}",
    "Conectando a {}:{}...": "Connecting to {}:{}...",
    "[OK] Conectado y autenticado": "[OK] Connected and authenticated",
    "Enviando {} archivos ({})": "Sending {} files ({})",
    "[!] Omitido {}: {}": "[!] Skipped {}: {}",
    "[i] Reanudando {} desde {}": "[i] Resuming {} from {}",
    "[OK] Terminado: {} copiados, {} saltados": "[OK] Done: {} copied, {} skipped",
    "[!] {} archivos con error: pulsa Iniciar de nuevo para reintentarlos (detalle en el registro del receptor)":
        "[!] {} files failed: press Start again to retry them (details in the receiver's log)",
    "[~] Conexión perdida ({}). Reconectando ({}/{})...":
        "[~] Connection lost ({}). Reconnecting ({}/{})...",
    "[ERROR] {}": "[ERROR] {}",
    "cancelado por el usuario": "cancelled by the user",
    "Handshake fallido: {}": "Handshake failed: {}",
    "El receptor rechazó la conexión": "The receiver rejected the connection",
    "PIN incorrecto": "Wrong PIN", "handshake inválido": "invalid handshake",
    "sin respuesta": "no response",
    "plan inválido del receptor": "invalid plan from receiver",
    "offset inválido del receptor para {}": "invalid offset from receiver for {}",
    "archivo modificado durante el envío: {}": "file changed while sending: {}",
    "el receptor cerró la conexión": "the receiver closed the connection",
    "el receptor no confirmó la recepción": "the receiver did not confirm reception",
    # --- confirmación de recepción ---
    "Solicitud de envío": "Incoming transfer",
    "Este equipo quiere enviarte archivos:": "This computer wants to send you files:",
    "Aceptar": "Accept", "Rechazar": "Reject",
    "Pedir confirmación antes de recibir": "Ask for confirmation before receiving",
}


def set_lang(code):
    global _lang
    _lang = code if code in IDIOMAS else "es"


def lang():
    return _lang


def _(texto):
    return EN.get(texto, texto) if _lang == "en" else texto
