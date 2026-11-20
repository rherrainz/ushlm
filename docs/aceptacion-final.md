# Aceptación final — USH Last Minute

Fecha de revisión: 20/11/2026. Responsable: Rodrigo Herrainz.

## Criterio de cierre

El 100 % significa completar el alcance aprobado y registrar su evaluación. No equivale a cobertura de pruebas del 100 %, ausencia de defectos ni preparación comercial ilimitada. La entrega incluye excursiones, estadías fijas y autos en Ushuaia, con solicitudes y confirmación manual. Pagos, inventarios externos, guías freelance y otros destinos son exclusiones desde el módulo 1.

La ponderación de avance técnico del README no sustituye la aceptación de todos los requisitos iniciales. Los resultados no ejecutados permanecen abiertos.

## Prueba con cinco participantes (RNF-03)

Estado: **pendiente de ejecución con personas reales**. No registrar cuentas demo ni agentes automatizados como participantes.

1. Preparar cinco cuentas de turista con datos ficticios y ofertas vigentes con cupo suficiente. Usar una base aislada de evaluación. No solicitar documentos ni tarjetas.
2. Explicar únicamente: «Esta plataforma permite encontrar ofertas turísticas de último momento en Ushuaia. Una solicitud requiere confirmación posterior del prestador». No explicar dónde hacer clic.
3. Entregar la tarea: «Encontrá una excursión, revisá su precio total para dos personas y enviá una solicitud. Explicá si el envío ya garantiza tu lugar».
4. Iniciar el cronómetro al mostrar la portada y detenerlo cuando la persona identifique su solicitud pendiente. Registrar si requirió ayuda, errores y duración. No corregir durante el intento; si se brinda ayuda, consignarla.
5. Preguntar: «¿Cuánto pagarías? ¿Cuándo vence la oferta? ¿Tu lugar ya está confirmado?». Registrar confusiones sin nombres ni contactos.
6. Criterio original: al menos cuatro de cinco participantes completan sin ayuda en menos de cinco minutos. Si falla, corregir la interfaz y repetir la ronda, conservando ambos resultados.

| Participante anónimo | Dispositivo / navegador y versión | Duración | Sin ayuda | Completó | Comprendió pendiente | Observaciones |
|---|---|---|---|---|---|---|
| P1 | Pendiente | — | — | — | — | — |
| P2 | Pendiente | — | — | — | — | — |
| P3 | Pendiente | — | — | — | — | — |
| P4 | Pendiente | — | — | — | — | — |
| P5 | Pendiente | — | — | — | — | — |

Fecha de ejecución: pendiente. Resultado: pendiente. No sustituir esta tabla por resultados estimados.

## Verificaciones restantes de aceptación

- RNF-01: medición realizada: 500 ofertas, 20 clientes, 100 consultas, p95 2,27 segundos y cero errores (ver `evidencias/rendimiento.json`). Para repetir, cargar 500 ofertas ficticias en una base aislada y simular 20 usuarios de consulta; registrar entorno, duración, cantidad de solicitudes, errores y percentil 95. Meta: p95 inferior a 3 segundos. No ejecutar carga sobre el sitio productivo sin evaluar su impacto.
- RNF-02: comprobar catálogo, detalle y formularios a 360 y 1366 píxeles en dos navegadores actuales. El recorrido previo a 390 píxeles acredita solo una parte de esta meta.
- RNF-06: ensayos lógicos local y PostgreSQL realizados (ver `evidencias/recuperacion.json` y `evidencias/recuperacion-postgresql.json`); configurar respaldo diario, sin publicar copias ni credenciales. Registrar proveedor, retención y fecha de la restauración.
- RNF-07: pedir a otra persona preparar el entorno siguiendo el README, registrar dificultades y corregir las instrucciones.
- RNF-08: recorrer con Tab, Shift+Tab, Enter y Espacio: filtros, login, solicitud y panel; comprobar foco visible, etiquetas y errores comprensibles.

## Diferencias de diseño que requieren cierre explícito

El diseño del módulo 2 proponía fotografías, vista previa de publicación y orden por precio condicionado a moneda. La revisión final incorporó la vista previa y el orden por precio dentro de una moneda. Las ilustraciones CSS locales se conservan como decisión visual de la demostración y no se presentan como fotografías de servicios reales.

El piloto con prestadores reales del módulo 1 tampoco se acredita con cuentas ficticias: la evaluación técnica actual es una demostración académica. Registrar entrevistas y validación si forman parte de la entrega acordada con la cátedra.
