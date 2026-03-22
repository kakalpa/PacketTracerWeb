"""WSGI entry point for gunicorn with HTTPS support"""

import sys
import os

sys.path.insert(0, '/app')
from app import create_app

app = create_app()

# SSL will be handled entirely by gunicorn via command-line arguments
# This allows enabling/disabling HTTPS via environment variables

if __name__ == '__main__':
    app.run()
