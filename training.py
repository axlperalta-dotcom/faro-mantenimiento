"""Load explicitly requested synthetic practice cases without overwriting user work."""
from pathlib import Path
from app import Store, ROOT

TRAINING = ROOT / 'examples' / 'training'
PT_CLOSURE = {
    'conclusion': 'La discrepancia de +1,00 bar estaba asociada al desplazamiento configurado en la pantalla. El transmisor y la referencia coincidían antes de aplicarlo; no se documentó un aumento físico equivalente.',
    'evidence': 'PT310-R01, secciones 1–2: pantalla 3,00/3,02 bar frente a referencia 2,00/2,02 bar y criterios previos. PT310-C01, sección 1: desplazamiento +1,00 bar frente a 0,00 bar aprobado. PT310-V01, sección 1: tres comparaciones posteriores.',
    'action_taken': 'En la simulación, el equipo de control restituyó el desplazamiento a 0,00 bar (PT310-C01, sección 2). No cambió la consigna ni el transmisor.',
    'verification': 'PT310-V01: a las 09:00, 09:15 y 09:30 las referencias fueron 2,00; 2,03; 1,99 bar, dentro de 1,80–2,20. Diferencias absolutas 0,00; 0,01; 0,01 bar, todas ≤0,05. Sin recurrencia en los 30 minutos observados. No implica garantía indefinida; revisión de cambios de parámetros queda como tarea separada.',
    'reviewed_by': 'Equipo de capacitación de Planta Norte (ficticio)'
}


def load_training(store):
    with store.connect() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS training_imports (
            key TEXT PRIMARY KEY, incident_id INTEGER NOT NULL, document_id INTEGER)''')

    def remembered(key):
        with store.connect() as db:
            return db.execute('SELECT * FROM training_imports WHERE key=?', (key,)).fetchone()

    def remember(key, incident_id, document_id=None):
        with store.connect() as db:
            db.execute('INSERT OR IGNORE INTO training_imports VALUES (?,?,?)', (key, incident_id, document_id))

    def attach(incident_id, filename):
        key = f'{incident_id}:{filename}'
        if remembered(key):
            return
        # Recover a previous partial import without duplicating an existing attachment.
        existing = next((d for d in store.incident(incident_id)['documents']
                         if d['synthetic'] and d['name'] == filename), None)
        document_id = existing['id'] if existing else store.add_document(
            incident_id, filename, (TRAINING / filename).read_bytes(), synthetic=True)
        remember(key, incident_id, document_id)

    def case(key, data):
        previous = remembered(key)
        if previous:
            return previous['incident_id']
        existing = next((i for i in store.list_incidents() if i['synthetic'] and i['title'] == data['title']), None)
        incident_id = existing['id'] if existing else store.create_incident(data, synthetic=True)
        remember(key, incident_id)
        return incident_id

    # Only supplement the original synthetic case, never a user's unrelated incident.
    original = next((i for i in store.list_incidents() if i['synthetic'] and
        i['title'] == 'Vibración y temperatura elevadas en bomba de recirculación'), None)
    if original:
        attach(original['id'], '00-criterios-de-cierre.txt')
        attach(original['id'], 'bc104-mediciones-pendientes.txt')

    opened = case('bc205-v1', {
        'title': 'Bajo caudal en recirculación · ejercicio para resolver',
        'equipment': 'Bomba centrífuga · BC-205', 'priority': 'Media', 'status': 'Abierta',
        'symptoms': 'Aviso de bajo caudal. Lecturas de 31 y 30 L/min frente a una referencia previa de 42 L/min. El expediente contiene observaciones, criterios y un ensayo posterior ya simulado.',
        'conditions': 'Planta Norte ficticia. Banco a 1450 rpm, V-205 abierta al 100 %, nivel 50 cm y agua a 22 °C. Todas las cifras y actuaciones son inventadas para practicar.',
        'notes': 'TU EJERCICIO: pasa a En investigación al comenzar. Compara BC205-B01, F01 y T01. Escribe una hipótesis principal, una alternativa y evidencia a favor/en contra. Después decide si puedes cerrar; no inventes datos faltantes. Revisión contigo pendiente.'
    })
    for filename in ('00-criterios-de-cierre.txt', 'bc205-ficha-y-criterios.txt',
                     'bc205-bitacora-inicial.txt', 'bc205-intervencion-y-ensayo.txt'):
        attach(opened, filename)

    resolved = case('pt310-v1', dict({
        'title': 'Discrepancia de presión en pantalla · ejemplo resuelto',
        'equipment': 'Canal de presión · PT-310', 'priority': 'Media', 'status': 'Resuelta',
        'symptoms': 'La pantalla mostraba aproximadamente 1,00 bar más que una referencia independiente. Se investigó si la diferencia correspondía al proceso físico o a la representación del dato.',
        'conditions': 'Planta Norte ficticia. Ensayo del 18/09/2026. Referencia considerada verificada para la simulación. Los límites internos del ejercicio se definen en PT310-R01.',
        'notes': 'EJEMPLO GUIADO: observa cómo cada afirmación de la ficha de cierre remite a un registro. La coincidencia de una palabra no demuestra una causa; el contraste de configuración y las lecturas antes/después sostienen esta conclusión.'
    }, **PT_CLOSURE))
    for filename in ('00-criterios-de-cierre.txt', 'pt310-criterios-y-reporte.txt',
                     'pt310-configuracion-y-correccion.txt', 'pt310-verificacion.txt'):
        attach(resolved, filename)
    return {'exercise': opened, 'resolved_example': resolved,
            'investigation': original['id'] if original else None}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=ROOT / 'data' / 'faro.sqlite3')
    args = parser.parse_args()
    print(load_training(Store(args.db)))
