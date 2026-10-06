"""Faro: local maintenance evidence workspace. Python 3.11+."""
from __future__ import annotations

import argparse
import io
import json
import logging
import re
import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
MAX_UPLOAD = 10 * 1024 * 1024
MAX_PAGES = 150
STATUSES = {'Abierta', 'En investigación', 'Resuelta'}
PRIORITIES = {'Baja', 'Media', 'Alta'}
CLOSURE_FIELDS = ('conclusion', 'evidence', 'action_taken', 'verification', 'reviewed_by')


class ValidationError(Exception):
    pass


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS incidents (
                    id INTEGER PRIMARY KEY, title TEXT NOT NULL, equipment TEXT NOT NULL,
                    symptoms TEXT NOT NULL, conditions TEXT NOT NULL DEFAULT '',
                    priority TEXT NOT NULL, status TEXT NOT NULL,
                    notes TEXT NOT NULL DEFAULT '', synthetic INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY, incident_id INTEGER REFERENCES incidents(id),
                    name TEXT NOT NULL, media_type TEXT NOT NULL, content BLOB NOT NULL,
                    page_count INTEGER NOT NULL, empty_pages INTEGER NOT NULL DEFAULT 0,
                    synthetic INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS passages USING fts5(
                    document_id UNINDEXED, page UNINDEXED, text,
                    tokenize='unicode61 remove_diacritics 2'
                );
            ''')
            # Additive migration: keep existing incidents, user notes and attachments.
            columns = {row['name'] for row in db.execute('PRAGMA table_info(incidents)')}
            for field in CLOSURE_FIELDS + ('closed_at',):
                if field not in columns:
                    db.execute(f"ALTER TABLE incidents ADD COLUMN {field} TEXT NOT NULL DEFAULT ''")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def list_incidents(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('''SELECT i.*,
                (SELECT count(*) FROM documents d WHERE d.incident_id=i.id) document_count
                FROM incidents i ORDER BY i.updated_at DESC, i.id DESC''')]

    def incident(self, incident_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM incidents WHERE id=?', (incident_id,)).fetchone()
            if not row:
                raise KeyError('Incidencia no encontrada.')
            result = dict(row)
            result['documents'] = [dict(r) for r in db.execute('''SELECT id,name,media_type,
                page_count,empty_pages,synthetic,created_at FROM documents
                WHERE incident_id=? ORDER BY id DESC''', (incident_id,))]
            return result

    @staticmethod
    def validate(data):
        if not isinstance(data, dict):
            raise ValidationError('Se esperaba un objeto JSON.')
        result = {}
        limits = {'title': 160, 'equipment': 120, 'symptoms': 5000,
                  'conditions': 3000, 'notes': 10000, 'priority': 20, 'status': 30}
        limits.update({field: 5000 for field in CLOSURE_FIELDS})
        limits['reviewed_by'] = 160
        for key, limit in limits.items():
            value = data.get(key, {'priority': 'Media', 'status': 'Abierta'}.get(key, ''))
            if not isinstance(value, str) or len(value) > limit:
                raise ValidationError(f'Campo inválido o demasiado largo: {key}.')
            result[key] = value.strip()
        if not all(result[k] for k in ('title', 'equipment', 'symptoms')):
            raise ValidationError('Completa el título, equipo y síntomas.')
        if result['priority'] not in PRIORITIES or result['status'] not in STATUSES:
            raise ValidationError('Prioridad o estado inválido.')
        if result['status'] == 'Resuelta' and not all(result[field] for field in CLOSURE_FIELDS):
            raise ValidationError('Para marcar Resuelta completa la ficha de cierre: conclusión, evidencia, acción, verificación y responsable de revisión.')
        return result

    def create_incident(self, data, synthetic=False):
        values = self.validate(data)
        stamp = now()
        with self.connect() as db:
            cur = db.execute('''INSERT INTO incidents
                (title,equipment,symptoms,conditions,priority,status,notes,synthetic,created_at,updated_at,
                conclusion,evidence,action_taken,verification,reviewed_by,closed_at)
                VALUES (:title,:equipment,:symptoms,:conditions,:priority,:status,:notes,
                :synthetic,:created_at,:updated_at,:conclusion,:evidence,:action_taken,:verification,:reviewed_by,:closed_at)''',
                dict(values, synthetic=int(synthetic), created_at=stamp, updated_at=stamp,
                     closed_at=stamp if values['status'] == 'Resuelta' else ''))
            return cur.lastrowid

    def update_incident(self, incident_id, data):
        existing = self.incident(incident_id)
        if not isinstance(data, dict):
            raise ValidationError('Se esperaba un objeto JSON.')
        if set(data) - {'status', 'notes', *CLOSURE_FIELDS}:
            raise ValidationError('Solo se pueden actualizar el estado, las notas y la ficha de cierre.')
        values = self.validate(dict(existing, **data))
        with self.connect() as db:
            db.execute('''UPDATE incidents SET status=:status,notes=:notes,updated_at=:updated_at,
                conclusion=:conclusion,evidence=:evidence,action_taken=:action_taken,
                verification=:verification,reviewed_by=:reviewed_by,closed_at=:closed_at WHERE id=:id''',
                dict(values, updated_at=now(), id=incident_id,
                     closed_at=(existing['closed_at'] or now()) if values['status'] == 'Resuelta' else ''))

    def add_document(self, incident_id, name, content, synthetic=False):
        self.incident(incident_id)
        name = name.replace('\\', '/').split('/')[-1].strip()
        if not name or len(name) > 180 or any(ord(c) < 32 for c in name):
            raise ValidationError('Nombre de archivo inválido.')
        if not content or len(content) > MAX_UPLOAD:
            raise ValidationError('El archivo debe contener datos y pesar como máximo 10 MB.')
        suffix = Path(name).suffix.lower()
        if suffix == '.pdf':
            from pypdf import PdfReader
            try:
                reader = PdfReader(io.BytesIO(content))
                if reader.is_encrypted:
                    raise ValidationError('El PDF está protegido. Adjunta una copia sin contraseña.')
                if len(reader.pages) > MAX_PAGES:
                    raise ValidationError('El máximo es de 150 páginas por documento.')
                pages = [(p.extract_text() or '').strip() for p in reader.pages]
            except ValidationError:
                raise
            except Exception as exc:
                raise ValidationError('No se pudo leer el PDF. Comprueba que sea válido.') from exc
            media_type = 'application/pdf'
        elif suffix == '.txt':
            try:
                pages = content.decode('utf-8-sig').split('\f')
            except UnicodeDecodeError as exc:
                raise ValidationError('Guarda el archivo de texto con codificación UTF-8.') from exc
            media_type = 'text/plain'
        else:
            raise ValidationError('Formatos admitidos: PDF con texto y TXT UTF-8.')
        if len(pages) > MAX_PAGES:
            raise ValidationError('El máximo es de 150 páginas o secciones.')
        if not any(p.strip() for p in pages):
            raise ValidationError('No se encontró texto extraíble. Los PDF escaneados requieren OCR, aún no incluido.')
        if sum(map(len, pages)) > 2_000_000:
            raise ValidationError('El documento contiene demasiado texto para esta versión.')
        with self.connect() as db:
            cur = db.execute('''INSERT INTO documents
                (incident_id,name,media_type,content,page_count,empty_pages,synthetic,created_at)
                VALUES (?,?,?,?,?,?,?,?)''', (incident_id, name, media_type, content,
                    len(pages), sum(not p.strip() for p in pages), int(synthetic), now()))
            document_id = cur.lastrowid
            for page, value in enumerate(pages, 1):
                if value.strip():
                    db.execute('INSERT INTO passages(document_id,page,text) VALUES (?,?,?)',
                               (document_id, page, value))
            db.execute('UPDATE incidents SET updated_at=? WHERE id=?', (now(), incident_id))
        return document_id

    def document(self, document_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM documents WHERE id=?', (document_id,)).fetchone()
            if not row:
                raise KeyError('Documento no encontrado.')
            return dict(row)

    def delete_document(self, incident_id, document_id):
        with self.connect() as db:
            row = db.execute('SELECT id FROM documents WHERE id=? AND incident_id=?',
                             (document_id, incident_id)).fetchone()
            if not row:
                raise KeyError('Documento no encontrado en esta incidencia.')
            db.execute('DELETE FROM passages WHERE document_id=?', (document_id,))
            db.execute('DELETE FROM documents WHERE id=? AND incident_id=?', (document_id, incident_id))
            db.execute('UPDATE incidents SET updated_at=? WHERE id=?', (now(), incident_id))

    def search(self, incident_id, query):
        self.incident(incident_id)
        if len(query) > 500:
            raise ValidationError('La búsqueda admite hasta 500 caracteres.')
        terms = re.findall(r'[^\W_]+', unicodedata.normalize('NFC', query), flags=re.UNICODE)[:20]
        stopwords = {'de', 'la', 'el', 'los', 'las', 'en', 'un', 'una', 'y', 'o', 'que', 'con', 'por', 'para'}
        terms = [t for t in terms if t.lower() not in stopwords]
        if not terms:
            return []
        match = ' OR '.join('"' + t + '"' for t in terms)
        # Unique delimiters let SQLite identify its exact matches, including accents.
        # Return structured text, never HTML supplied by a document.
        marker = uuid4().hex
        start, end = f'[{marker}:start]', f'[{marker}:end]'
        with self.connect() as db:
            results = [dict(r) for r in db.execute('''SELECT d.id document_id,d.name,d.media_type,
                d.synthetic,CAST(passages.page AS INTEGER) page,
                snippet(passages,2,?,?,' … ',48) excerpt
                FROM passages JOIN documents d ON d.id=passages.document_id
                WHERE passages MATCH ? AND d.incident_id=?
                ORDER BY bm25(passages), d.id, CAST(passages.page AS INTEGER) LIMIT 12''',
                (start, end, match, incident_id))]
        for result in results:
            parts, highlighted = [], False
            for text in re.split(f'({re.escape(start)}|{re.escape(end)})', result['excerpt']):
                if text == start:
                    highlighted = True
                elif text == end:
                    highlighted = False
                elif text:
                    parts.append({'text': text, 'highlight': highlighted})
            result['excerpt_parts'] = parts
            result['excerpt'] = ''.join(part['text'] for part in parts)
        return results

    def seed_demo(self):
        if self.list_incidents():
            return
        incident_id = self.create_incident({
            'title': 'Vibración y temperatura elevadas en bomba de recirculación',
            'equipment': 'Bomba centrífuga · BC-104',
            'symptoms': 'El operador reporta un aumento de vibración y temperatura después del arranque. Se escucha ruido intermitente cerca del acoplamiento.',
            'conditions': 'Caso sintético. Operación al 70 % de carga. Aún no hay mediciones verificadas de vibración, temperatura ni presión de succión.',
            'priority': 'Media', 'status': 'En investigación',
            'notes': 'Pendiente: recopilar valores, unidades y condiciones de medición. Separar las observaciones de las hipótesis.'
        }, synthetic=True)
        self.add_document(incident_id, 'guia-sintetica-bomba.txt', (ROOT / 'examples' / 'guia-sintetica-bomba.txt').read_bytes(), synthetic=True)


class Handler(BaseHTTPRequestHandler):
    server_version = 'Faro/0.1'

    def send(self, status, content, content_type='application/json; charset=utf-8', headers=None):
        if not isinstance(content, bytes):
            content = json.dumps(content, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(content)

    def body(self, limit, json_body=False):
        if self.headers.get('Transfer-Encoding'):
            raise ValidationError('Transferencia no admitida.')
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError as exc:
            raise ValidationError('Longitud inválida.') from exc
        if length <= 0 or length > limit:
            raise ValidationError('Solicitud vacía o demasiado grande.')
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise ValidationError('Carga incompleta.')
        if json_body:
            if self.headers.get_content_type() != 'application/json':
                raise ValidationError('Se requiere application/json.')
            try:
                return json.loads(raw)
            except (ValueError, UnicodeDecodeError) as exc:
                raise ValidationError('JSON inválido.') from exc
        return raw

    def do_GET(self):
        self.dispatch('GET')

    def do_POST(self):
        self.dispatch('POST')

    def do_PATCH(self):
        self.dispatch('PATCH')

    def do_DELETE(self):
        self.dispatch('DELETE')

    def dispatch(self, method):
        try:
            host = self.headers.get('Host', '')
            port = self.server.server_port
            if host not in {f'127.0.0.1:{port}', f'localhost:{port}'}:
                return self.send(403, {'error': 'Acceso permitido únicamente desde localhost.'})
            origin = self.headers.get('Origin')
            if origin and origin not in {f'http://127.0.0.1:{port}', f'http://localhost:{port}'}:
                return self.send(403, {'error': 'Origen no permitido.'})
            path = urlparse(self.path).path
            query = parse_qs(urlparse(self.path).query)
            store = self.server.store
            if method == 'GET' and path in {'/', '/app.js', '/style.css'}:
                name = 'index.html' if path == '/' else path[1:]
                kind = {'index.html': 'text/html', 'app.js': 'text/javascript', 'style.css': 'text/css'}[name]
                return self.send(200, (ROOT / 'static' / name).read_bytes(), kind + '; charset=utf-8')
            if path == '/api/incidents':
                if method == 'GET':
                    return self.send(200, store.list_incidents())
                if method == 'POST':
                    incident_id = store.create_incident(self.body(30000, True))
                    return self.send(201, store.incident(incident_id))
            match = re.fullmatch(r'/api/incidents/(\d+)(?:/(documents|search|export))?', path)
            if match:
                incident_id = int(match[1])
                action = match[2]
                if method == 'GET' and not action:
                    return self.send(200, store.incident(incident_id))
                if method == 'PATCH' and not action:
                    store.update_incident(incident_id, self.body(30000, True))
                    return self.send(200, store.incident(incident_id))
                if method == 'POST' and action == 'documents':
                    document_id = store.add_document(incident_id,
                        unquote(self.headers.get('X-Filename', '')), self.body(MAX_UPLOAD))
                    return self.send(201, {'id': document_id})
                if method == 'GET' and action == 'search':
                    return self.send(200, store.search(incident_id, query.get('q', [''])[0]))
                if method == 'GET' and action == 'export':
                    return self.send(200, store.incident(incident_id), headers={
                        'Content-Disposition': f'attachment; filename="incidencia-{incident_id:04d}.json"'})
            match = re.fullmatch(r'/api/incidents/(\d+)/documents/(\d+)', path)
            if method == 'DELETE' and match:
                store.delete_document(int(match[1]), int(match[2]))
                return self.send(200, {'deleted': int(match[2])})
            match = re.fullmatch(r'/api/documents/(\d+)/file', path)
            if method == 'GET' and match:
                doc = store.document(int(match[1]))
                return self.send(200, doc['content'], doc['media_type'], {
                    'Content-Disposition': 'inline' if doc['media_type'] == 'application/pdf' else 'inline; filename="documento.txt"'})
            self.send(404, {'error': 'Recurso no encontrado.'})
        except ValidationError as exc:
            self.send(400, {'error': str(exc)})
        except KeyError as exc:
            self.send(404, {'error': str(exc.args[0])})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            logging.exception('Error procesando la solicitud')
            self.send(500, {'error': 'Error interno. Revisa el registro del servidor.'})

    def setup(self):
        super().setup()
        self.connection.settimeout(30)


def make_server(path, port=8765, demo=False):
    store = Store(path)
    if demo:
        store.seed_demo()
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.store = store
    return server


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Faro Mantenimiento · aplicación local')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--db', type=Path, default=ROOT / 'data' / 'faro.sqlite3')
    parser.add_argument('--demo', action='store_true', help='Cargar caso sintético si la base está vacía')
    args = parser.parse_args()
    server = make_server(args.db, args.port, args.demo)
    print(f'Faro Mantenimiento: http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
