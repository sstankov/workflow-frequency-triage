"""Local dashboard with durable, explicitly submitted corrections."""
import json
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from .corrections import save_override, remove_override
from .repository import ArtifactRepository


def make_server(port, *, repository=None):
    repository = repository if repository is not None else ArtifactRepository()
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,directory=str(repository.dist),**kwargs)
        def end_headers(self):
            self.send_header('Cache-Control','no-store')
            super().end_headers()
        def do_POST(self):
            expected = '127.0.0.1:%s' % self.server.server_port
            if self.path not in ('/api/override', '/api/override/remove'):
                self.send_error(404); return
            if self.headers.get('Origin') != 'http://'+expected or self.headers.get('Host') != expected or self.headers.get('Content-Type') != 'application/json':
                self.send_error(403,'Use the local dashboard origin'); return
            try:
                length = int(self.headers.get('Content-Length','0'))
                if not 0 < length <= 20000: raise ValueError('Invalid request size')
                fields = json.loads(self.rfile.read(length))
                if self.path == '/api/override/remove':
                    if set(fields) != {'flow_id', 'correction_id', 'reviewer'}:
                        raise ValueError('Invalid removal fields')
                    remove_override(fields['flow_id'], fields['correction_id'], fields['reviewer'], repository=repository)
                else:
                    if set(fields) != {'flow_id','outcome','cadence','reason','reviewer'}: raise ValueError('Invalid correction fields')
                    save_override(**fields, repository=repository)
                status,body = 200,{'ok':True}
            except (ValueError,TypeError,KeyError,OSError) as exc:
                status,body = 400,{'error':str(exc)}
            encoded = json.dumps(body).encode()
            self.send_response(status)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(encoded)))
            self.end_headers(); self.wfile.write(encoded)
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)


def serve_dashboard(port, *, repository=None):
    server = make_server(port, repository=repository)
    print('Dashboard: http://127.0.0.1:%s (Ctrl+C to stop)' % server.server_port,flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
