# Primera práctica guiada

Objetivo: entender un recorrido completo desde la interfaz hasta la base de datos.

1. Abre Faro y revisa el caso de demostración. Identifica qué es una observación y qué datos siguen faltando.
2. Crea una incidencia sintética de un equipo que conozcas. Conserva las unidades en las condiciones de operación.
3. Adjunta una fuente de práctica y busca un término. Comprueba personalmente que el fragmento existe en la página indicada.
4. Guarda una nota, cambia el estado y recarga la página.
5. Ejecuta las pruebas desde la raíz del proyecto.

## Lectura de código, en este orden

1. `static/app.js`: creación del caso mediante `fetch`.
2. `app.py`, método `Handler.dispatch`: recepción de la solicitud.
3. `Store.validate` y `Store.create_incident`: validación y escritura.
4. `Store.search`: recuperación de evidencia.
5. `tests/test_app.py`: prueba que comprueba una cita en la segunda página de un PDF.

## Preguntas para poder defender el trabajo

- ¿Por qué se valida en el servidor aunque el formulario tenga campos obligatorios?
- ¿Qué sucede si el PDF no tiene texto?
- ¿Cómo evita la búsqueda devolver documentos de otro caso?
- ¿Por qué una coincidencia textual no confirma la causa de la falla?
- ¿Qué se necesitaría para ofrecer esta aplicación a varios usuarios?

## Primer cambio que harás con acompañamiento

Añadir el campo «fecha y hora de la observación». Antes de programar, define qué significa, cómo se diferencia de la fecha de creación y qué debe ocurrir con los casos existentes. Después seguiremos el cambio desde el formulario hasta una prueba de persistencia.
