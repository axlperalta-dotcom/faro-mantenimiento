# Faro Mantenimiento

Aplicación local para investigar incidencias de equipos: registrar observaciones, adjuntar fuentes y recuperar evidencia con su página de origen.

**Estado: v0.1, primera entrega funcional.** La recuperación actual utiliza palabras clave (SQLite FTS5); todavía no hay generación con LLM, diagnóstico automático ni llamadas a APIs. Proyecto independiente de portafolio en desarrollo, sin usuarios de producción ni resultados de campo acreditados.

## Problema y usuario

Un técnico recibe un reporte de ruido o vibración. Necesita conservar las condiciones de operación, consultar documentación y anotar qué evidencia apoya o contradice una hipótesis. Faro reúne ese trabajo en un expediente persistente.

## Funciones de esta entrega

- Crear incidencias con equipo, síntomas, condiciones y prioridad.
- Filtrar por estado, título o equipo; guardar notas y estado de investigación.
- Guardar una ficha de cierre con conclusión, evidencia, acción, verificación y responsable. Marcar Resuelta exige completar esos campos; la validez técnica requiere revisión humana.
- Adjuntar PDF con texto o TXT UTF-8 (10 MB, máximo 150 páginas o secciones).
- Buscar fragmentos dentro de los documentos del caso y abrir el original en la página citada.
- Resaltar en amarillo las coincidencias dentro de los fragmentos al pulsar Enter o Buscar, respetando acentos y mayúsculas.
- Eliminar adjuntos con confirmación: se quitan la copia almacenada y su índice de búsqueda; el archivo original de la computadora se conserva.
- Conservar archivos originales y registros en SQLite, incluso después del reinicio.
- Exportar un registro JSON; el exportado enumera documentos, pero no incluye sus bytes ni evidencia seleccionada.
- Caso inicial y guía **sintéticos**, para practicar. Nunca se mezclan silenciosamente con datos reales.

## Ejecutar en esta computadora (Windows)

Abre `Iniciar.cmd` y visita **http://127.0.0.1:8765**. Conserva abierta la terminal; Ctrl+C detiene el servidor. El lanzador prefiere `.venv` y, en esta computadora, puede usar el Python incluido con Codex. No instala paquetes automáticamente.

## Instalación reproducible en otra computadora

Requiere Python 3.11+ con SQLite FTS5 (las distribuciones habituales de Python lo incluyen).

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py --demo
```

En Linux/macOS usa `.venv/bin/python` en lugar de `.\.venv\Scripts\python.exe`.

`--demo` incorpora el caso sintético únicamente si la base está vacía. Para empezar vacío, omite esa opción. Puedes usar `--port 8766` y `--db ruta/otra.sqlite3`. La base por defecto se guarda en `data/faro.sqlite3` y está excluida de Git. En una carpeta sincronizada por OneDrive, sus archivos podrían sincronizarse: aquí se usarán ejemplos públicos o sintéticos. No abras simultáneamente una misma base desde dos computadoras.

## Recorrido de demostración

1. Abre la incidencia sintética de la bomba BC-104.
2. Busca `vibración temperatura` y abre la guía referenciada.
3. Escribe una nota que separe observaciones de hipótesis y pulsa **Guardar revisión**.
4. Crea un caso propio con datos sintéticos y adjunta un PDF con texto seleccionable.
5. Busca un término que figure en la segunda página y comprueba la referencia.
6. Reinicia el servidor y comprueba que el caso, documento y nota siguen presentes.

## Verificación

```powershell
python -m unittest discover -s tests -v
node tests/test_frontend.cjs
```

Las pruebas usan bases temporales: verifican persistencia, aislamiento entre casos, referencia exacta de página, acentos, PDF sin texto, cargas inválidas, validación, recorrido HTTP, descarga, eliminación transaccional y protección de origen. Las pruebas de interfaz requieren Node.js y comprueban resaltado seguro, cancelación de eliminación y conservación de notas sin guardar; Node no es necesario para ejecutar la aplicación. No necesitan red externa ni claves. El flujo de GitHub Actions queda preparado; solo se ejecutará al publicar este directorio como raíz de un repositorio.

## Estructura

```text
app.py                 Servidor HTTP, validación, almacenamiento y búsqueda
static/                Interfaz web sin dependencias de compilación
examples/              Fuentes sintéticas para la demostración
tests/                 Pruebas de integración y almacenamiento
docs/                  Arquitectura, plan de trabajo y guía de aprendizaje
data/                  Base local y documentos (ignorado por Git)
```

## Límites actuales

- Versión local de un solo usuario. No publicar este servidor directamente en Internet: usa `http.server` para desarrollo, sin autenticación, permisos de usuario ni aislamiento del procesador PDF.
- No tiene OCR: los PDF escaneados sin texto se rechazan; las páginas sin texto de documentos mixtos se señalan.
- La búsqueda es léxica, no semántica; usa coincidencias de términos, omite algunas palabras comunes y limita los resultados a 12 fragmentos. Sinónimos pueden no coincidir. No hay métricas de calidad sobre un conjunto independiente todavía.
- Una coincidencia documental no demuestra una causa ni autoriza mantenimiento. La fuente original y la revisión humana siguen siendo necesarias.
- Las notas y el estado se sobrescriben al guardar; aún no existe historial de versiones ni control de edición simultánea. La interfaz advierte al salir con cambios sin guardar.
- El tamaño y número de páginas están limitados, pero aún no hay un proceso aislado con límite duro de memoria/CPU para archivos hostiles. Adjunta únicamente documentos de confianza.
- No se envían documentos a un proveedor de IA. La integración futura requerirá definir credenciales, presupuesto y datos permitidos.

## Portafolio y atribución

Desarrollado con asistencia de IA. El objetivo de aprendizaje es que el autor pueda explicar, probar y modificar cada componente. El historial de decisiones y la evidencia de pruebas son parte del proyecto; no se deben presentar métricas simuladas como resultados de producción.

Código del proyecto bajo MIT, ver `LICENSE`. La guía de ejemplo se publica con la misma licencia; es contenido sintético creado para este proyecto. Los documentos que adjunte cada usuario conservan sus propios derechos.

Siguiente entrega: seleccionar evidencia para un borrador de reporte y construir un conjunto pequeño de evaluación antes de conectar un LLM. Ver `docs/PLAN.md` y `docs/PRIMERA-SESION.md`.

## Casos de práctica

Ejecuta `python training.py` para añadir los expedientes sintéticos de Planta Norte a una base existente. Con el caso inicial BC-104 disponible, quedan tres situaciones: BC-104 En investigación, BC-205 Abierta para que el alumno la resuelva y PT-310 Resuelta como ejemplo completo. El importador conserva el progreso previo; no impone esos estados si ya fueron cambiados. Los documentos son TXT UTF-8 buscables y sus valores no representan especificaciones reales.

Ver `docs/PRACTICA-INVESTIGACION.md`. El importador no se ejecuta automáticamente al reiniciar la aplicación.
