import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLineEdit, QLabel, 
                             QCheckBox, QProgressBar, QTextEdit, QStackedWidget)
from PyQt6.QtCore import QPropertyAnimation, QRect, QEasingCurve, QTimer, Qt
from PyQt6.QtGui import QFont, QColor

class WCPWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WCP - Windows Copy Peer (Aero UI)")
        self.resize(800, 650)
        
        # Estilos globales (CSS para PyQt)
        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e2e; }
            QLabel { color: #cdd6f4; font-size: 14px; }
            QLineEdit { 
                background-color: #313244; color: #cdd6f4; 
                border: 2px solid #45475a; border-radius: 8px; padding: 5px 10px;
            }
            QLineEdit:focus { border: 2px solid #89b4fa; }
            QCheckBox { color: #cdd6f4; font-size: 14px; spacing: 8px; }
            QCheckBox::indicator { width: 18px; height: 18px; border-radius: 4px; }
            QCheckBox::indicator:unchecked { background-color: #313244; border: 2px solid #45475a; }
            QCheckBox::indicator:checked { background-color: #89b4fa; border: 2px solid #89b4fa; }
            QTextEdit { 
                background-color: #11111b; color: #a6e3a1; 
                font-family: Consolas, monospace; font-size: 13px;
                border: 2px solid #313244; border-radius: 8px; padding: 5px;
            }
            QPushButton { 
                background-color: #89b4fa; color: #11111b; 
                font-size: 15px; font-weight: bold; border-radius: 8px; padding: 10px;
            }
            QPushButton:hover { background-color: #b4befe; }
            QPushButton:disabled { background-color: #45475a; color: #7f849c; }
            
            /* Estilo de las pestañas superiores */
            QPushButton#TabButton {
                background-color: transparent; color: #7f849c; border-radius: 0px;
                border-bottom: 3px solid transparent; font-size: 16px; padding: 10px;
            }
            QPushButton#TabButton:hover { color: #cdd6f4; }
            QPushButton#TabButton:checked { 
                color: #89b4fa; border-bottom: 3px solid #89b4fa; font-weight: bold;
            }
            QProgressBar {
                background-color: #313244; border-radius: 6px; text-align: center;
                color: white; font-weight: bold;
            }
            QProgressBar::chunk { background-color: #a6e3a1; border-radius: 6px; }
        """)

        # Contenedor principal
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 20)
        main_layout.setSpacing(0)

        # --- BARRA DE PESTAÑAS ---
        tab_layout = QHBoxLayout()
        tab_layout.setContentsMargins(20, 10, 20, 10)
        
        self.btn_tab_send = QPushButton("Enviar Archivos")
        self.btn_tab_send.setObjectName("TabButton")
        self.btn_tab_send.setCheckable(True)
        self.btn_tab_send.setChecked(True)
        self.btn_tab_send.clicked.connect(lambda: self.switch_tab(0))
        
        self.btn_tab_recv = QPushButton("Recibir Archivos")
        self.btn_tab_recv.setObjectName("TabButton")
        self.btn_tab_recv.setCheckable(True)
        self.btn_tab_recv.clicked.connect(lambda: self.switch_tab(1))

        tab_layout.addWidget(self.btn_tab_send)
        tab_layout.addWidget(self.btn_tab_recv)
        tab_layout.addStretch()
        main_layout.addLayout(tab_layout)

        # --- STACKED WIDGET (Para cambiar entre vistas) ---
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)

        # Crear las dos vistas
        self.view_send = self.create_send_view()
        self.view_recv = self.create_recv_view()
        self.stack.addWidget(self.view_send)
        self.stack.addWidget(self.view_recv)

        # Iniciar animación de caída al abrir
        QTimer.singleShot(100, lambda: self.animate_in(self.view_send))

    def create_send_view(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(40, 20, 40, 20)
        layout.setSpacing(20)

        # 1. Conexión
        conn_layout = QHBoxLayout()
        conn_layout.addWidget(QLabel("IP Destino:"))
        ip_input = QLineEdit()
        ip_input.setPlaceholderText("192.168.1.X")
        conn_layout.addWidget(ip_input)
        
        conn_layout.addWidget(QLabel("Puerto:"))
        port_input = QLineEdit()
        port_input.setText("8765")
        port_input.setFixedWidth(60)
        conn_layout.addWidget(port_input)
        
        conn_layout.addWidget(QLabel("PIN:"))
        pin_input = QLineEdit()
        pin_input.setEchoMode(QLineEdit.EchoMode.Password)
        pin_input.setFixedWidth(100)
        conn_layout.addWidget(pin_input)
        
        btn_search = QPushButton("🔍 Buscar")
        btn_search.setFixedWidth(100)
        conn_layout.addWidget(btn_search)
        
        layout.addLayout(conn_layout)

        # 2. Carpetas
        layout.addWidget(QLabel("Carpetas a copiar:"))
        folder_layout = QHBoxLayout()
        folder_layout.addWidget(QCheckBox("Escritorio"))
        folder_layout.addWidget(QCheckBox("Documentos"))
        folder_layout.addWidget(QCheckBox("Descargas"))
        folder_layout.addWidget(QCheckBox("Imágenes"))
        layout.addLayout(folder_layout)

        # 3. Controles
        ctrl_layout = QHBoxLayout()
        btn_start = QPushButton("▶ Iniciar Envío")
        btn_start.setFixedHeight(45)
        btn_stop = QPushButton("■ Detener")
        btn_stop.setFixedHeight(45)
        btn_stop.setEnabled(False)
        ctrl_layout.addWidget(btn_start, 3)
        ctrl_layout.addWidget(btn_stop, 1)
        layout.addLayout(ctrl_layout)

        # 4. Progreso
        progress = QProgressBar()
        progress.setValue(0)
        progress.setFixedHeight(15)
        layout.addWidget(progress)
        
        lbl_status = QLabel("Listo para enviar")
        lbl_status.setStyleSheet("color: #a6adc8;")
        layout.addWidget(lbl_status)

        # 5. Log
        log = QTextEdit()
        log.setReadOnly(True)
        log.setText("[INFO] Esperando conexión...\n")
        layout.addWidget(log)

        return widget

    def create_recv_view(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(40, 20, 40, 20)
        layout.setSpacing(20)

        # 1. Info
        lbl_info = QLabel("Tu PC está lista para recibir")
        lbl_info.setStyleSheet("font-size: 18px; font-weight: bold; color: #89b4fa;")
        lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_info)
        
        lbl_ip = QLabel("IP: 192.168.1.50    |    PIN: 123456")
        lbl_ip.setStyleSheet("font-size: 22px; font-family: Consolas; font-weight: bold;")
        lbl_ip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_ip)

        # 2. Ruta
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("Guardar en:"))
        path_input = QLineEdit()
        path_input.setText("C:\\Users\\Iker\\Downloads")
        path_input.setReadOnly(True)
        path_layout.addWidget(path_input)
        btn_pick = QPushButton("...")
        btn_pick.setFixedWidth(50)
        path_layout.addWidget(btn_pick)
        layout.addLayout(path_layout)

        # 3. Controles
        ctrl_layout = QHBoxLayout()
        btn_start = QPushButton("▶ Iniciar Recepción")
        btn_start.setFixedHeight(45)
        btn_stop = QPushButton("■ Detener")
        btn_stop.setFixedHeight(45)
        btn_stop.setEnabled(False)
        ctrl_layout.addWidget(btn_start, 3)
        ctrl_layout.addWidget(btn_stop, 1)
        layout.addLayout(ctrl_layout)

        # 4. Log
        log = QTextEdit()
        log.setReadOnly(True)
        log.setText("[INFO] Servidor detenido.\n")
        layout.addWidget(log)

        return widget

    def switch_tab(self, index):
        # Actualizar botones
        self.btn_tab_send.setChecked(index == 0)
        self.btn_tab_recv.setChecked(index == 1)
        
        # Cambiar vista
        self.stack.setCurrentIndex(index)
        
        # Animar la nueva vista
        current_view = self.stack.currentWidget()
        self.animate_in(current_view)

    def animate_in(self, widget):
        """Animación Aero: El widget cae desde arriba y rebota."""
        # Detener animación previa si existe
        if hasattr(self, 'anim') and self.anim.state() == QPropertyAnimation.State.Running:
            self.anim.stop()
            
        self.anim = QPropertyAnimation(widget, b"geometry")
        self.anim.setDuration(1000) # 1 segundo
        
        # Calcular posiciones
        target_rect = widget.geometry()
        start_rect = QRect(target_rect.x(), target_rect.y() - 600, target_rect.width(), target_rect.height())
        
        self.anim.setStartValue(start_rect)
        self.anim.setEndValue(target_rect)
        
        # El toque mágico: Rebote
        self.anim.setEasingCurve(QEasingCurve.Type.OutBounce)
        self.anim.start()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = WCPWindow()
    window.show()
    sys.exit(app.exec())
