"""WSGI entry point for gunicorn"""

import sys
import os

# Import create_app from the main app.py file
sys.path.insert(0, '/app')
from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run()

