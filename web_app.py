"""Local dashboard entrypoint. Run python web_app.py."""
import argparse
import subprocess  # compatibility for existing tests
from http.server import ThreadingHTTPServer
from src.web.service import Dashboard
from src.web.http import make_handler

def main():
    parser = argparse.ArgumentParser(description='Olzha Agro local web dashboard')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    app = Dashboard()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(app))
    print(f'Olzha Agro: http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.close()
        server.server_close()


if __name__ == '__main__':
    main()
