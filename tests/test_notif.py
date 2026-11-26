"""Tes modul Telegram dengan server palsu."""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import notif  # noqa: E402


def server(balas):
    diterima = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            diterima.append((self.path, json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
            kode, isi = balas
            b = json.dumps(isi).encode()
            self.send_response(kode)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(b)))
            self.end_headers()
            self.wfile.write(b)

    httpd = HTTPServer(('127.0.0.1', 0), H)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, diterima


def test_kirim_berhasil_dan_dipecah(monkeypatch):
    httpd, terima = server((200, {'ok': True}))
    monkeypatch.setattr(notif, 'API', f'http://127.0.0.1:{httpd.server_port}')
    teks = '\n'.join(f'baris {i} ' + 'x' * 100 for i in range(80))          # > 4096 karakter
    ok, ket = notif.kirim('TOKEN123', '42', teks)
    httpd.shutdown()
    assert ok and ket == 'terkirim' and len(terima) >= 2
    assert terima[0][0] == '/botTOKEN123/sendMessage' and terima[0][1]['chat_id'] == '42' and terima[0][1]['parse_mode'] == 'HTML'
    assert all(len(p[1]['text']) <= 4096 for p in terima)


def test_ditolak_telegram_token_tidak_bocor(monkeypatch):
    httpd, _ = server((401, {'ok': False, 'description': 'Unauthorized'}))
    monkeypatch.setattr(notif, 'API', f'http://127.0.0.1:{httpd.server_port}')
    ok, ket = notif.kirim('TOKEN-RAHASIA', '42', 'halo')
    httpd.shutdown()
    assert not ok and 'Unauthorized' in ket and 'TOKEN-RAHASIA' not in ket


def test_server_mati_dan_belum_diisi(monkeypatch):
    monkeypatch.setattr(notif, 'API', 'http://127.0.0.1:9')
    ok, ket = notif.kirim('TOKEN-RAHASIA', '42', 'halo')
    assert not ok and 'TOKEN-RAHASIA' not in ket
    assert notif.kirim('', '42', 'x')[0] is False and notif.kirim('t', '', 'x')[0] is False
