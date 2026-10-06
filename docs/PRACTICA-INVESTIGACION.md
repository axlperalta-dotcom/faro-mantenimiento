# Práctica de investigación · Planta Norte ficticia

Todos los expedientes, mediciones y criterios son inventados. Los ensayos ya registrados se consideran hechos de la simulación; no se requiere intervenir equipos ni inventar nuevas mediciones.

## Cómo saber cuándo cerrar

Las notas son tu cuaderno de trabajo. La ficha de cierre explica qué concluyes, con qué evidencia, qué acción consta, cómo se verificó y quién revisa. En la práctica, anota tu nombre con «revisión de ejercicio». La aplicación verifica campos completos; la revisión técnica la hacemos juntos. No autentica al revisor ni comprueba automáticamente referencias o diagnósticos.

Abierta = reporte pendiente de análisis. En investigación = contraste de hipótesis o comprobaciones pendientes. Resuelta = conclusión sustentada y resultado verificado según el criterio del ejercicio. No es obligatorio resolver todos los expedientes: detenerse ante evidencia insuficiente es una respuesta válida.

## Orden recomendado

1. **PT-310, ejemplo resuelto.** Lee el reporte, la auditoría de configuración y la verificación. Recorre su ficha de cierre: comprueba cada número y referencia.
2. **BC-205, tu ejercicio.** Cambia a En investigación al comenzar. Lee los cuatro documentos. Completa las notas antes de redactar el cierre.
3. **BC-104, evidencia insuficiente.** Lee la adenda y decide qué datos pedir. Las mediciones nuevas no sustituyen ni contradicen el reporte inicial: se incorporaron después y siguen siendo incompletas.

## Plantilla para las notas de BC-205

Observación: qué variable se salió del rango y por cuánto.

Hipótesis principal: explicación concreta del incidente operativo.

Alternativa: otra explicación plausible y evidencia que la apoya o debilita.

Comparación: condiciones del antecedente, del reporte y de la prueba posterior.

Evidencia: nombres de documentos y secciones o registros; valores y unidades.

Decisión: cerrar o continuar investigando, con justificación.

Limitaciones: qué no puede concluirse todavía y qué tarea queda separada.

## Revisión conjunta

Cuando hayas guardado tu propuesta, pide: «Revisa mi investigación de BC-205». Leeremos lo que escribiste en Faro y lo contrastaremos con el expediente. No hay evaluador LLM automático conectado a la aplicación.

Evaluaremos cinco dimensiones, de 0 a 2 cada una:

- Separación entre observaciones e hipótesis.
- Comparación numérica con unidades y condiciones equivalentes.
- Referencias que realmente respaldan la conclusión.
- Verificación frente a los criterios previos, incluida su duración.
- Reconocimiento de límites y claridad al decidir el estado.

La puntuación es una rúbrica de aprendizaje, no una certificación profesional. Una buena conclusión puede reconocer incertidumbre; una conclusión sin evidencia no mejora por estar redactada con seguridad.

## Reproducir los expedientes

En una instalación vacía, inicia una vez `python app.py --demo` y detén el servidor. Después ejecuta `python training.py` e inicia `python app.py`. El importador añade dos casos y documentos; no sobrescribe notas o estados de casos existentes. Sus claves de importación evitan duplicados y respetan documentos eliminados después de cargarlos.
