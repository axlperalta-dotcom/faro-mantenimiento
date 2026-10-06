# Decisiones iniciales

## ADR-001 · Aplicación local ligera

Contexto: computadora con 8 GB RAM, CPU AMD Ryzen y gráficos Radeon; aprendizaje de ingeniería de software aplicada a IA. Se busca una entrega ejecutable sin infraestructura de pago.

Decisión: Python 3.11+, servidor HTTP de la biblioteca estándar, SQLite FTS5 y HTML/CSS/JavaScript. La única dependencia externa de ejecución es pypdf para extraer texto. No se requiere GPU, Node, Docker ni una API de modelos para esta entrega.

Consecuencia: inicio y pruebas simples. A cambio, el servidor es de desarrollo; migrar a un servidor de aplicaciones con autenticación, límites de recursos y un procesador de documentos aislado antes de exponerlo públicamente. La interfaz puede migrar a TypeScript cuando exista una necesidad concreta.

## Flujo de datos

Navegador → API local → validación → SQLite.

Carga de documento → extracción PDF/TXT → conservación del original y páginas en una transacción → índice FTS5.

Consulta → términos escapados → filtro por incidencia → ranking BM25 → fragmento y página → apertura de la fuente original.

Los PDF usan números de página físicos desde 1, que pueden diferir de los números impresos. Los TXT usan secciones separadas por el carácter de salto de página; normalmente son una sola sección.

## Tablas

- `incidents`: observaciones, condiciones, prioridad, estado, notas y marcas temporales UTC.
- `documents`: archivo original BLOB, relación con el caso, tipo, páginas, páginas vacías y procedencia sintética.
- `passages`: tabla virtual FTS5, una entrada por página con texto.

Se usan parámetros SQL y una transacción por carga para evitar documentos parcialmente indexados. Cada operación obtiene su propia conexión. El navegador renderiza datos como texto escapado. Host y Origin restringen solicitudes al servidor local; no se habilita CORS.

## Próximas decisiones, aún pendientes

1. Dataset representativo y permisos de los manuales.
2. Criterios de aceptación para recuperación de evidencia y abstención del modelo.
3. API de LLM, presupuesto y política de envío de documentos.
4. Despliegue de demostración y autenticación.
5. Historial de revisión y evaluación con usuarios.
