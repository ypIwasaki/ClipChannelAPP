"""Throwaway UI only. Serves embedded fixtures, never imports the application."""
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


class Preview(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split('?')[0] not in ('/', '/prototype/responsive-ui'):
            self.send_error(404)
            return
        body = Path(__file__).with_suffix('.html').read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == '__main__':
    print('PROTOTYPE: http://127.0.0.1:8765/prototype/responsive-ui', flush=True)
    HTTPServer(('127.0.0.1', 8765), Preview).serve_forever()
