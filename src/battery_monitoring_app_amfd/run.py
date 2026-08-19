import sys

from .app import BatMonApp

if __name__ == '__main__':
    app = BatMonApp(sys.argv)
    app.exec()
