"""Local Qt themes for light and dark Windows desktop use."""
from PySide6.QtWidgets import QApplication


def apply_theme(app: QApplication, dark: bool) -> None:
    """Set theme colors without depending on external assets."""
    background, panel, text, faint, border, accent, selected = (
        ("#171b23", "#202631", "#ecf0f6", "#aab5c5", "#3b4656", "#3169c9", "#293e62") if dark else
        ("#f2f5fa", "#ffffff", "#192438", "#58677b", "#cdd6e3", "#235abd", "#dfebff")
    )
    app.setStyle("Fusion")
    app.setStyleSheet(f"""
        QWidget {{ background: {background}; color: {text}; font: 10pt "Segoe UI"; }}
        QLabel#brand {{ font-size: 16pt; font-weight: 700; }}
        QLabel#heading {{ font-size: 18pt; font-weight: 700; }}
        QLabel#muted {{ color: {faint}; }}
        QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QListWidget, QTreeWidget {{
            background: {panel}; border: 1px solid {border}; border-radius: 6px; padding: 6px;
        }}
        QLineEdit:focus, QPlainTextEdit:focus, QTreeWidget:focus {{ border-color: {accent}; }}
        QPushButton, QToolButton {{
            background: {panel}; border: 1px solid {border}; border-radius: 6px; padding: 6px 10px;
        }}
        QPushButton:hover, QToolButton:hover {{ border-color: {accent}; }}
        QPushButton#primary {{ background: {accent}; color: white; border-color: {accent}; font-weight: 600; }}
        QPushButton:disabled {{ color: {faint}; }}
        QTreeWidget::item {{ padding: 8px 2px; }}
        QTreeWidget::item:selected, QListWidget::item:selected {{ background: {selected}; color: {text}; }}
        QTabBar::tab {{ padding: 8px 11px; color: {faint}; }}
        QTabBar::tab:selected {{ color: {text}; border-bottom: 2px solid {accent}; }}
        QScrollArea {{ border: none; }}
        QSplitter::handle {{ background: {border}; width: 1px; }}
    """)
