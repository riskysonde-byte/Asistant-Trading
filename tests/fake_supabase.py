"""Server palsu yang meniru bagian REST Supabase (PostgREST) yang dipakai aplikasi. Hanya untuk tes."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

KUNCI = 'rahasia-tes'


class Server:
    def __init__(self):
        self.tabel = {}
        self.log = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _auth(self):
                if self.headers.get('apikey') != KUNCI or self.headers.get('Authorization') != 'Bearer ' + KUNCI:
                    self._kirim(401, {'message': 'Invalid API key'})
                    return False
                return True

            def _kirim(self, kode, isi):
                b = json.dumps(isi).encode()
                self.send_response(kode)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_GET(self):
                if not self._auth():
                    return
                u = urlparse(self.path)
                nama = u.path.rsplit('/', 1)[-1]
                q = {k: v[0] for k, v in parse_qs(u.query).items()}
                baris = list(outer.tabel.get(nama, {}).values())
                for k, v in q.items():
                    if k in ('select', 'order', 'limit'):
                        continue
                    if v.startswith('eq.'):
                        baris = [b for b in baris if str(b.get(k)) == v[3:]]
                    elif v.startswith('in.(') and v.endswith(')'):
                        baris = [b for b in baris if str(b.get(k)) in v[4:-1].split(',')]
                for kolom in reversed([c for c in q.get('order', '').split(',') if c]):
                    nm, _, arah = kolom.partition('.')
                    baris.sort(key=lambda b: (b.get(nm) is None, b.get(nm) or ''), reverse=(arah == 'desc'))
                if 'limit' in q:
                    baris = baris[:int(q['limit'])]
                if q.get('select', '*') != '*':
                    kol = q['select'].split(',')
                    baris = [{c: b.get(c) for c in kol} for b in baris]
                outer.log.append(('GET', nama, q))
                self._kirim(200, baris)

            def do_POST(self):
                if not self._auth():
                    return
                u = urlparse(self.path)
                nama = u.path.rsplit('/', 1)[-1]
                konflik = parse_qs(u.query).get('on_conflict', ['id'])[0]
                data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                t = outer.tabel.setdefault(nama, {})
                for b in data:
                    t[b[konflik]] = {**t.get(b[konflik], {}), **b}
                outer.log.append(('POST', nama, len(data)))
                self._kirim(201, [])

        self.httpd = HTTPServer(('127.0.0.1', 0), H)
        self.url = f'http://127.0.0.1:{self.httpd.server_port}'
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tutup(self):
        self.httpd.shutdown()
