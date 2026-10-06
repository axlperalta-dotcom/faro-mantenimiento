import io
import json
import shutil
import threading
import unittest
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app import Store, ValidationError, make_server, MAX_UPLOAD
from training import load_training, PT_CLOSURE


class TestDirectory:
    """Workspace-local scratch space, compatible with restricted Windows runtimes."""
    def __init__(self):
        self.root = (Path(__file__).resolve().parents[1] / 'test-results').resolve()
        self.path = self.root / uuid.uuid4().hex
        self.path.mkdir(parents=True)
        self.name = str(self.path)

    def cleanup(self):
        target = self.path.resolve()
        if target.parent != self.root or target == self.root:
            raise RuntimeError('Unexpected test cleanup target')
        shutil.rmtree(target)


def pdf_bytes(text_pages):
    writer = PdfWriter()
    for text in text_pages:
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
            NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'):
            DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(f'BT /F1 12 Tf 50 700 Td ({text}) Tj ET'.encode('ascii'))
        page[NameObject('/Contents')] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = TestDirectory()
        self.path = Path(self.temp.name) / 'faro.db'
        self.store = Store(self.path)
        self.incident_id = self.store.create_incident({'title': 'Ruido', 'equipment': 'BC-1', 'symptoms': 'Vibración'})

    def tearDown(self):
        self.temp.cleanup()

    def test_persistence_status_notes_and_documents(self):
        self.store.update_incident(self.incident_id, dict(PT_CLOSURE, status='Resuelta', notes='Revisión humana.'))
        content = 'Temperatura elevada.'.encode()
        doc = self.store.add_document(self.incident_id, 'evidencia.txt', content)
        restarted = Store(self.path)
        result = restarted.incident(self.incident_id)
        self.assertEqual(result['status'], 'Resuelta')
        self.assertEqual(result['notes'], 'Revisión humana.')
        self.assertEqual(len(result['documents']), 1)
        self.assertEqual(restarted.document(doc)['content'], content)

    def test_search_preserves_pdf_page_and_source(self):
        doc = self.store.add_document(self.incident_id, 'manual.pdf', pdf_bytes(['Inspection log.', 'Vibration found in coupling.']))
        results = self.store.search(self.incident_id, 'vibration')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['page'], 2)
        self.assertEqual(results[0]['document_id'], doc)
        self.assertIn('coupling', results[0]['excerpt'])

    def test_search_accents_case_and_case_isolation(self):
        self.store.add_document(self.incident_id, 'guia.txt', 'Vibración del equipo.'.encode())
        other = self.store.create_incident({'title':'Otro', 'equipment':'BC-2', 'symptoms':'Ruido'})
        self.store.add_document(other, 'otro.txt', b'Vibration leak uniqueleak')
        self.assertEqual(len(self.store.search(self.incident_id, 'VIBRACION')), 1)
        self.assertEqual(self.store.search(self.incident_id, 'uniqueleak'), [])
        self.assertEqual(self.store.search(self.incident_id, '???'), [])
        self.assertEqual(self.store.search(self.incident_id, 'OR " * NEAR('), [])

    def test_invalid_uploads_leave_no_partial_data(self):
        bad = [('bad.exe', b'abc'), ('bad.pdf', b'not pdf'), ('empty.txt', b'   '),
               ('bad.txt', b'\xff'), ('scan.pdf', pdf_bytes([''])), ('large.txt', b'x' * (MAX_UPLOAD + 1))]
        for name, content in bad:
            with self.subTest(name=name), self.assertRaises(ValidationError):
                self.store.add_document(self.incident_id, name, content)
        self.assertEqual(self.store.incident(self.incident_id)['documents'], [])

    def test_empty_pages_preserve_numbering(self):
        doc = self.store.add_document(self.incident_id, 'mixed.pdf', pdf_bytes(['', 'Temperature trend.']))
        self.assertEqual(self.store.document(doc)['empty_pages'], 1)
        self.assertEqual(self.store.search(self.incident_id, 'temperature')[0]['page'], 2)

    def test_highlights_exact_matches_with_accents_and_untrusted_text(self):
        source = '<script>alert(1)</script> VIBRACIÓN, temperatura; vibración y vibraciones.'
        self.store.add_document(self.incident_id, 'guia.txt', source.encode())
        result = self.store.search(self.incident_id, 'vibracion temperatura')[0]
        self.assertEqual(result['excerpt'], source)
        self.assertEqual(''.join(p['text'] for p in result['excerpt_parts']), source)
        self.assertEqual([p['text'] for p in result['excerpt_parts'] if p['highlight']],
                         ['VIBRACIÓN', 'temperatura', 'vibración'])

    def test_delete_removes_file_and_index_without_changing_review(self):
        self.store.update_incident(self.incident_id, {'notes': 'Datos faltantes del usuario.', 'status': 'En investigación'})
        deleted = self.store.add_document(self.incident_id, 'quitar.txt', b'unique_deleted')
        retained = self.store.add_document(self.incident_id, 'conservar.txt', b'unique_retained')
        self.store.delete_document(self.incident_id, deleted)
        restarted = Store(self.path)
        self.assertEqual(restarted.search(self.incident_id, 'deleted'), [])
        self.assertEqual(len(restarted.search(self.incident_id, 'retained')), 1)
        with self.assertRaises(KeyError): restarted.document(deleted)
        case = restarted.incident(self.incident_id)
        self.assertEqual([d['id'] for d in case['documents']], [retained])
        self.assertEqual(case['notes'], 'Datos faltantes del usuario.')
        self.assertEqual(case['status'], 'En investigación')
        self.assertEqual(restarted.list_incidents()[0]['document_count'], 1)
        with restarted.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM passages WHERE document_id=?', (deleted,)).fetchone()[0], 0)

    def test_delete_wrong_case_is_rejected_and_failure_rolls_back(self):
        document_id = self.store.add_document(self.incident_id, 'guia.txt', b'vibration')
        with self.assertRaises(KeyError): self.store.delete_document(9999, document_id)
        with self.store.connect() as db:
            db.execute("CREATE TRIGGER fail_delete BEFORE DELETE ON documents BEGIN SELECT RAISE(ABORT, 'test failure'); END")
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.delete_document(self.incident_id, document_id)
        self.assertEqual(len(self.store.search(self.incident_id, 'vibration')), 1)
        self.assertEqual(self.store.document(document_id)['name'], 'guia.txt')

    def test_validation_missing_record_and_invalid_changes(self):
        for data in [{'title':' '}, [], {'title':123}]:
            with self.assertRaises(ValidationError): self.store.create_incident(data)
        with self.assertRaises(ValidationError): self.store.update_incident(self.incident_id, {'status':'Invalid'})
        with self.assertRaises(ValidationError): self.store.update_incident(self.incident_id, {'title':'Overwrite'})
        with self.assertRaises(KeyError): self.store.add_document(999, 'x.txt', b'hello')

    def test_demo_only_seeds_empty_database(self):
        self.store.seed_demo()
        self.assertEqual(len(self.store.list_incidents()), 1)
        fresh = Store(Path(self.temp.name) / 'demo.db')
        fresh.seed_demo(); fresh.seed_demo()
        self.assertEqual(len(fresh.list_incidents()), 1)
        self.assertTrue(fresh.incident(1)['synthetic'])
        self.assertTrue(fresh.search(1, 'vibración'))

    def test_closure_requires_all_fields_and_preserves_drafts_on_reopen(self):
        self.store.update_incident(self.incident_id, {'conclusion':'Hipótesis inicial', 'notes':'Sin terminar'})
        with self.assertRaises(ValidationError):
            self.store.update_incident(self.incident_id, {'status':'Resuelta', 'notes':'No guardar esto'})
        self.assertEqual(self.store.incident(self.incident_id)['notes'], 'Sin terminar')
        for field in PT_CLOSURE:
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.store.update_incident(self.incident_id, dict(PT_CLOSURE, status='Resuelta', **{field:' '}))
        self.store.update_incident(self.incident_id, dict(PT_CLOSURE, status='Resuelta'))
        closed = self.store.incident(self.incident_id)
        self.assertTrue(closed['closed_at'])
        self.store.update_incident(self.incident_id, {'notes':'Nota adicional'})
        self.assertEqual(self.store.incident(self.incident_id)['closed_at'], closed['closed_at'])
        self.store.update_incident(self.incident_id, {'status':'En investigación'})
        reopened = self.store.incident(self.incident_id)
        self.assertEqual(reopened['closed_at'], '')
        self.assertEqual(reopened['evidence'], PT_CLOSURE['evidence'])

    def test_additive_migration_preserves_legacy_notes(self):
        import sqlite3
        legacy = Path(self.temp.name) / 'legacy.db'
        with sqlite3.connect(legacy) as db:
            db.execute('''CREATE TABLE incidents (id INTEGER PRIMARY KEY,title TEXT,equipment TEXT,
                symptoms TEXT,conditions TEXT,priority TEXT,status TEXT,notes TEXT,synthetic INTEGER,
                created_at TEXT,updated_at TEXT)''')
            db.execute("INSERT INTO incidents VALUES (1,'Caso','Equipo','Ruido','','Media','En investigación','Notas originales',0,'2026-09-19','2026-09-19')")
        db.close()
        upgraded = Store(legacy)
        self.assertEqual(upgraded.incident(1)['notes'], 'Notas originales')
        self.assertEqual(upgraded.incident(1)['conclusion'], '')
        self.assertEqual(Store(legacy).incident(1)['status'], 'En investigación')

    def test_training_import_is_idempotent_and_preserves_user_work(self):
        fresh = Store(Path(self.temp.name) / 'training.db')
        fresh.seed_demo()
        fresh.update_incident(1, {'notes':'Notas del alumno, no reemplazar'})
        ids = load_training(fresh)
        cases = fresh.list_incidents()
        self.assertEqual(len(cases), 3)
        self.assertEqual({c['status'] for c in cases}, {'Abierta','En investigación','Resuelta'})
        self.assertTrue(all(c['synthetic'] for c in cases))
        self.assertEqual(fresh.incident(1)['notes'], 'Notas del alumno, no reemplazar')
        self.assertTrue(fresh.search(ids['exercise'], 'caudal'))
        resolved = fresh.incident(ids['resolved_example'])
        self.assertTrue(all(resolved[k] for k in PT_CLOSURE))
        doc = fresh.incident(ids['exercise'])['documents'][0]
        fresh.delete_document(ids['exercise'], doc['id'])
        fresh.update_incident(ids['exercise'], {'status':'En investigación', 'notes':'Mi progreso'})
        before = fresh.list_incidents()
        load_training(fresh)
        self.assertEqual(fresh.list_incidents(), before)
        self.assertEqual(fresh.incident(ids['exercise'])['notes'], 'Mi progreso')


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = TestDirectory()
        cls.server = make_server(Path(cls.temp.name) / 'api.db', port=0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()
        cls.temp.cleanup()

    def request(self, path, method='GET', data=None, headers=None):
        headers = dict(headers or {})
        if isinstance(data, (dict, list)):
            data = json.dumps(data).encode()
            headers['Content-Type'] = 'application/json'
        req = Request(self.base + path, data=data, headers=headers, method=method)
        try:
            response = urlopen(req, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, response.headers, response.read()

    def test_create_upload_search_export_roundtrip(self):
        code, _, body = self.request('/api/incidents', 'POST', {'title':'API test','equipment':'Pump','symptoms':'Noise'})
        self.assertEqual(code, 201)
        incident_id = json.loads(body)['id']
        code, _, body = self.request(f'/api/incidents/{incident_id}/documents', 'POST',
            pdf_bytes(['No observations.', 'Evidence: temperature.']), {'X-Filename':'manual.pdf'})
        self.assertEqual(code, 201)
        document_id = json.loads(body)['id']
        code, _, body = self.request(f'/api/incidents/{incident_id}/search?q=temperature')
        self.assertEqual(json.loads(body)[0]['page'], 2)
        self.assertEqual(self.request(f'/api/incidents/{incident_id}', 'PATCH', {'status':'Resuelta'})[0], 400)
        code, _, _ = self.request(f'/api/incidents/{incident_id}', 'PATCH', dict(PT_CLOSURE, notes='Reviewed', status='Resuelta'))
        self.assertEqual(code, 200)
        code, headers, body = self.request(f'/api/incidents/{incident_id}/export')
        self.assertIn('attachment', headers['Content-Disposition'])
        self.assertEqual(json.loads(body)['notes'], 'Reviewed')
        self.assertEqual(json.loads(body)['verification'], PT_CLOSURE['verification'])
        code, headers, body = self.request(f'/api/documents/{document_id}/file')
        self.assertEqual(headers['Content-Type'], 'application/pdf')
        self.assertTrue(body.startswith(b'%PDF'))

    def test_origin_host_json_and_not_found(self):
        self.assertEqual(self.request('/api/incidents', headers={'Origin':'https://untrusted.example'})[0], 403)
        self.assertEqual(self.request('/api/incidents', headers={'Host':'untrusted.example'})[0], 403)
        self.assertEqual(self.request('/api/incidents', 'POST', b'not json', {'Content-Type':'application/json'})[0], 400)
        self.assertEqual(self.request('/api/incidents', 'POST', [1, 2])[0], 400)
        self.assertEqual(self.request('/api/incidents/999999')[0], 404)
        self.assertEqual(self.request('/../app.py')[0], 404)

    def test_frontend_security_headers(self):
        code, headers, body = self.request('/')
        self.assertEqual(code, 200)
        self.assertIn('Faro', body.decode())
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
        self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])

    def test_delete_http_and_search_highlights(self):
        _, _, body = self.request('/api/incidents', 'POST', {'title':'Delete test','equipment':'Pump','symptoms':'Noise'})
        incident_id = json.loads(body)['id']
        _, _, body = self.request(f'/api/incidents/{incident_id}/documents', 'POST',
                                 b'Vibration source', {'X-Filename':'temporary.txt'})
        document_id = json.loads(body)['id']
        route = f'/api/incidents/{incident_id}/documents/{document_id}'
        _, _, body = self.request(f'/api/incidents/{incident_id}/search?q=vibration')
        self.assertTrue(json.loads(body)[0]['excerpt_parts'][0]['highlight'])
        self.assertEqual(self.request(route, 'DELETE', headers={'Origin':'https://untrusted.example'})[0], 403)
        self.assertEqual(self.request(route, 'DELETE')[0], 200)
        self.assertEqual(self.request(route, 'DELETE')[0], 404)
        self.assertEqual(self.request(f'/api/documents/{document_id}/file')[0], 404)
        _, _, body = self.request(f'/api/incidents/{incident_id}/search?q=vibration')
        self.assertEqual(json.loads(body), [])


if __name__ == '__main__':
    unittest.main()
