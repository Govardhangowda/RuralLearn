import sys
import logging
from pathlib import Path
from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QApplication
from rurallearn.ui import MainWindow
from rurallearn.db import Database

def main():
    app = QApplication(sys.argv)
    app.setApplicationName('RuralLearn')
    app.setStyle('Fusion')
    log_dir=Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
    log_dir.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=log_dir/'rurallearn.log',level=logging.INFO,encoding='utf-8',
                        format='%(asctime)s %(levelname)s %(name)s %(message)s')
    db = Database()
    window = MainWindow(db)
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
