# Ofertas demo disponibles para evaluación

Las tres ofertas académicas originales (IDs 1, 2 y 3) se usan como plantillas
explícitas. Cada ciclo publica nuevas copias con los mismos títulos, precios,
condiciones, duración e inventario de las plantillas. No se recrean cuentas.
Las fechas de las solicitudes y publicaciones anteriores no se sobrescriben.

## Programación

- Vercel invoca `/internal/cron/renew-demo/` diariamente a las 09:00 UTC
  (06:00 en Ushuaia; la plataforma puede demorar la ejecución).
- El servidor usa ciclos continuos de 48 horas a partir del 1/1/2026 a las
  09:00 UTC. La base guarda el último ciclo y bloquea la fila durante la tarea.
  Una comprobación intermedia o reintento no publica otra edición.
- El primer ciclo se publica al activar la función; el siguiente se alinea a
  la programación fija. Los ciclos posteriores se separan por 48 horas.
- Las ofertas vencen 60 horas después de publicarse. Sus servicios empiezan
  64, 66 y 68 horas después, dentro de la ventana de 72 horas de la aplicación.
  Hay 12 horas de margen respecto de la frecuencia programada.
- Se cierran las publicaciones de la edición anterior y vencen sus solicitudes
  pendientes con registro de historial y aviso interno. Las confirmadas se
  conservan y una cancelación posterior no devuelve cupo a la nueva edición.
- Una suspensión del prestador o moderación de una oferta detiene la renovación;
  la tarea no revierte decisiones administrativas. No toca otras publicaciones.

El cron no garantiza disponibilidad continua si el proveedor falla o se consume
el cupo de la edición. No modifica el comportamiento de ofertas reales.

## Configuración

Solo en Production:

```text
DEMO_RENEWAL_ENABLED=1
DEMO_SOURCE_OFFER_IDS=1,2,3
CRON_SECRET=<secreto privado ya configurado>
```

Aplicar primero `python manage.py migrate` para crear `DemoRefreshState` y ejecutar
`python manage.py renew_demo` una vez con esas variables y la conexión adecuada.
Después desplegar el commit con la entrada `crons` de `vercel.json`.
No ejecutar la semilla sobre la base pública existente.

La ruta requiere `Authorization: Bearer <CRON_SECRET>`, acepta GET, exige Production
y no permite caché. Los errores no devuelven datos ni credenciales. La tarea diaria
de respaldo sigue desactivada: esta programación solo renueva la demostración.

Para desactivar, establecer `DEMO_RENEWAL_ENABLED=0` en Production y redesplegar.
Las publicaciones y sus reservas se conservan; no hay limpieza destructiva.

## Pruebas

`python manage.py test market.test_demo_renewal` verifica publicación, vigencia,
reintentos, periodicidad, límites de calendario, conservación del historial,
aislamiento de inventario, bloqueos por moderación/habilitación, rollback y
protección de la ruta. La suite completa sigue siendo obligatoria antes de publicar.
