# Aceptación final — USH Last Minute

Fecha de revisión: 21/11/2026. Responsable: Rodrigo Herrainz.

## Criterio de cierre

El 100 % significa completar el alcance aprobado y registrar su evaluación. No equivale a cobertura de pruebas del 100 %, ausencia de defectos ni preparación comercial ilimitada. La entrega incluye excursiones, estadías fijas y autos en Ushuaia, con solicitudes y confirmación manual. Pagos, inventarios externos, guías freelance y otros destinos son exclusiones desde el módulo 1.

La ponderación de avance técnico del README no sustituye la aceptación de todos los requisitos iniciales. Los resultados no ejecutados permanecen abiertos.

## Evaluación funcional sintética (RNF-03 revisado)

**Estado: aprobado, cinco de cinco escenarios.**

El 21/11/2026 se acordó sustituir el criterio inicial de usabilidad con cinco participantes por una evaluación funcional sintética. La participación de personas reales era una meta propuesta por el proyecto, no una exigencia de la consigna de la materia. Se conserva esta nota para identificar el cambio respecto del plan inicial; no se presenta la simulación como evidencia de una prueba humana.

**Criterio vigente:** los cinco escenarios automatizados deben completar el circuito de registro, búsqueda, revisión del total, solicitud pendiente y confirmación; verificar inventario, historial, avisos y lectura; y aprobar las variantes de errores, permisos, reenvío idempotente y ordenamiento definidas en la tabla de resultados. No deben producir fallos de las aserciones ni modificar producción.

### Procedimiento reproducible

1. Preparar el entorno de desarrollo según el README.
2. Ejecutar `python scripts/synthetic_acceptance.py` desde la raíz del repositorio.
3. El script crea una base SQLite temporal y las cuentas y ofertas ficticias de las tres categorías. Ejecuta los recorridos HTTP con protección CSRF.
4. Cada recorrido comprueba sus resultados mediante aserciones. El proceso falla si alguna no se cumple.
5. Revisar `evidencias/aceptacion-sintetica.json`: deben constar cinco escenarios aprobados, cero participantes humanos y ausencia de modificaciones productivas. La base temporal se elimina al finalizar.

Los resultados ejecutados y las variantes se detallan al final de este documento. Los tiempos de ejecución automática no representan tiempos de interacción humana. La comprensión, la facilidad de uso y la adaptación visual no se infieren de esta evaluación; las verificaciones de interfaz se registran por separado.

## Verificaciones restantes de aceptación

- RNF-01: medición realizada: 500 ofertas, 20 clientes, 100 consultas, p95 2,27 segundos y cero errores (ver `evidencias/rendimiento.json`). Para repetir, cargar 500 ofertas ficticias en una base aislada y simular 20 usuarios de consulta; registrar entorno, duración, cantidad de solicitudes, errores y percentil 95. Meta: p95 inferior a 3 segundos. No ejecutar carga sobre el sitio productivo sin evaluar su impacto.
- RNF-02: comprobar catálogo, detalle y formularios a 360 y 1366 píxeles en dos navegadores actuales. El recorrido previo a 390 píxeles acredita solo una parte de esta meta.
- RNF-06: ensayos lógicos local y PostgreSQL realizados (ver `evidencias/recuperacion.json` y `evidencias/recuperacion-postgresql.json`); configurar respaldo diario, sin publicar copias ni credenciales. Registrar proveedor, retención y fecha de la restauración.
- RNF-07: pedir a otra persona preparar el entorno siguiendo el README, registrar dificultades y corregir las instrucciones.
- RNF-08: recorrer con Tab, Shift+Tab, Enter y Espacio: filtros, login, solicitud y panel; comprobar foco visible, etiquetas y errores comprensibles.

## Diferencias de diseño que requieren cierre explícito

El diseño del módulo 2 proponía fotografías, vista previa de publicación y orden por precio condicionado a moneda. La revisión final incorporó la vista previa y el orden por precio dentro de una moneda. Las ilustraciones CSS locales se conservan como decisión visual de la demostración y no se presentan como fotografías de servicios reales.

El piloto con prestadores reales del módulo 1 tampoco se acredita con cuentas ficticias: la evaluación técnica actual es una demostración académica. Registrar entrevistas y validación si forman parte de la entrega acordada con la cátedra.


## Pruebas sintéticas ejecutadas — 21/11/2026

Se ejecutaron cinco recorridos HTTP automatizados con cuentas ficticias y una base SQLite temporal, eliminada al finalizar. Se aplicó la protección CSRF real de Django. No se modificaron datos productivos.

En todos se verificaron registro e inicio de sesión, filtrado, detalle, total de dos unidades (ARS 140,00), solicitud pendiente sin descuento de cupo, aviso al prestador, lectura del aviso, confirmación, descuento de dos unidades, historial y aviso al turista.

| Escenario | Categoría | Variante adicional | Resultado |
|---|---|---|---|
| S1 | Excursión | Circuito principal completo | Aprobado |
| S2 | Alojamiento | Cantidad cero rechazada; corrección y envío válido | Aprobado |
| S3 | Auto | Intento de operar una solicitud ajena denegado; listado privado | Aprobado |
| S4 | Excursión | Reenvío del formulario sin duplicar solicitud | Aprobado |
| S5 | Alojamiento | Filtro de moneda y orden por precio | Aprobado |

**Resultado: cinco de cinco escenarios sintéticos aprobados. Participantes humanos: cero.** Esta evidencia acredita funcionamiento HTTP secuencial, no comprensión, facilidad de uso, adaptación visual ni la meta de cuatro de cinco personas en menos de cinco minutos. Los tiempos registrados corresponden a ejecución automática. RNF-03 queda aprobado conforme al criterio sintético revisado; la meta inicial con personas reales fue sustituida y ya no es un pendiente de este criterio.

Repetir desde la raíz con `python scripts/synthetic_acceptance.py`. El script impone una base temporal local, prepara datos ficticios y genera [el registro JSON](../evidencias/aceptacion-sintetica.json). No requiere credenciales de producción. La concurrencia PostgreSQL y JavaScript conservan sus evidencias separadas.
