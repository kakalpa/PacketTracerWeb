#!/bin/bash
set -e

ENABLE_HTTPS="${ENABLE_HTTPS:-false}"
SSL_CERT="${SSL_CERT_PATH:-/app/ssl/server.crt}"
SSL_KEY="${SSL_KEY_PATH:-/app/ssl/server.key}"

if [ "$ENABLE_HTTPS" = "true" ] && [ -f "$SSL_CERT" ] && [ -f "$SSL_KEY" ]; then
  echo "Starting pt-management with HTTPS (port 5443, HTTP redirect port 5000)"
  
  # Start HTTP redirect server in background
  # Health checks on /health are served as-is (no redirect)
  # All other endpoints redirect to HTTPS
  python3 << 'PYEOF' &
import http.server
import socketserver
import json
import urllib.parse

class SmartRedirectHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        # Health checks use HTTP directly (for internal monitoring)
        if self.path.startswith('/health'):
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "endpoint": "http"}).encode())
        else:
            # Serve redirect page with helpful instructions
            html_page = """<!DOCTYPE html>
<html>
<head>
    <title>Redirecting to HTTPS...</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; 
               background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
               margin: 0; padding: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
        .container { background: white; padding: 40px; border-radius: 10px; box-shadow: 0 10px 40px rgba(0,0,0,0.1); 
                     max-width: 500px; text-align: center; }
        h1 { color: #333; margin-top: 0; }
        p { color: #666; line-height: 1.6; }
        .secure-icon { font-size: 48px; margin: 20px 0; }
        a { display: inline-block; margin-top: 20px; padding: 12px 30px; background: #667eea; color: white; 
            text-decoration: none; border-radius: 5px; transition: background 0.3s; }
        a:hover { background: #764ba2; }
        code { background: #f5f5f5; padding: 2px 6px; border-radius: 3px; font-family: monospace; }
    </style>
</head>
<body>
    <div class="container">
        <div class="secure-icon">🔒</div>
        <h1>Secure Connection</h1>
        <p>This page is being redirected to HTTPS for security.</p>
        <p style="font-size: 14px; color: #999;">If you see a certificate warning, this is expected with self-signed certificates.</p>
        <a href="https://localhost:5443""" + self.path + """">Click here to continue to secure endpoint</a>
        <p style="margin-top: 30px; font-size: 12px; color: #bbb;">Or use: <code>curl -sk https://localhost:5443</code></p>
    </div>
    <script>
        // Auto-redirect after 1 second if JavaScript is enabled
        setTimeout(function() {
            window.location.replace('https://localhost:5443""" + self.path + """');
        }, 1000);
    </script>
</body>
</html>"""
            self.send_response(307)  # Temporary redirect
            self.send_header('Location', 'https://localhost:5443' + self.path)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', len(html_page))
            self.end_headers()
            self.wfile.write(html_page.encode())
    
    def log_message(self, format, *args):
        pass  # Suppress logs

socketserver.TCPServer(('0.0.0.0', 5000), SmartRedirectHandler).serve_forever()
PYEOF
  
  sleep 1
  
  # Start HTTPS gunicorn in foreground
  # Suppress SSLV3_ALERT_CERTIFICATE_UNKNOWN warnings from internal Docker network requests
  # These are harmless and occur when internal services probe HTTPS without certificate validation
  exec gunicorn \
    --bind 0.0.0.0:5443 \
    --certfile="$SSL_CERT" \
    --keyfile="$SSL_KEY" \
    --workers 2 \
    --timeout 120 \
    wsgi:app 2>&1 | grep -v "SSLV3_ALERT_CERTIFICATE_UNKNOWN\|Invalid request from ip=172\." || true
else
  echo "Starting pt-management with HTTP (port 5000)"
  exec gunicorn \
    --bind 0.0.0.0:5000 \
    --workers 2 \
    --timeout 120 \
    wsgi:app
fi
