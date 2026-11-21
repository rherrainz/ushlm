# Respaldo y recuperación — entrega académica

**Estado: tarea preparada y probada. Ejecución diaria real desactivada.**

El 21/11/2026 el responsable delimitó RNF-06 al objetivo académico: disponer de la tarea lista y demostrar que la copia y la recuperación funcionan. No se exige mantener un servicio de respaldo periódico en producción. Esta decisión sustituye la meta operativa diaria propuesta inicialmente; no se presenta una prueba manual como ejecución automática.

## Copia lógica y recuperación

```sh
mkdir -p backups
python manage.py backup_project --output "backups/ushlm-$(date +%Y%m%d-%H%M%S).backup.json"
```

Una copia contiene contactos y hashes de contraseñas. El comando crea un archivo nuevo con permisos 0600, preserva todos los microsegundos de las fechas y usa una instantánea consistente en PostgreSQL. Excluye sesiones; al restaurar se vuelve a iniciar sesión. No publica copias, cadenas de conexión ni claves en Git.

Para restaurar, crear una base **distinta y vacía** con la misma versión del código. Configurar la conexión de esa base en un entorno aislado, ejecutar `migrate` y luego `loaddata /ruta/privada/copia.backup.json`. Verificar usuarios, prestadores, ofertas, solicitudes, historiales, moderaciones y avisos, incluidos importes, fechas y estados. No restaurar sobre el sitio público. Un rollback de Vercel cambia código, no los datos.

## Tarea cifrada preparada

- Implementación: `market/daily_backup.py`; ruta autenticada `/internal/cron/daily-backup/`.
- Almacén **privado** `ushlm-backups`, región `iad1`, conectado solo a Production. Las pruebas utilizaron datos ficticios, eliminados al finalizar; no se enviaron datos de la base productiva a este almacén.
- La tarea comprime con gzip y cifra con Fernet antes de transmitir por HTTPS. La copia contiene datos de Django, no las variables de entorno ni las credenciales de Neon/Vercel.
- Requiere `CRON_SECRET`, `BACKUP_ENCRYPTION_KEY`, un almacén configurado, entorno Production y `DAILY_BACKUP_ENABLED=1`. La configuración actual mantiene **`DAILY_BACKUP_ENABLED=0`**.
- La ruta devuelve 401 sin autorización. No ofrece una descarga pública de la base. Respuestas sin caché y errores sin contactos, claves ni mensajes internos sensibles.
- Una copia por fecha UTC, sin reemplazar una existente. Se comprueba la lectura y el descifrado antes de retener las siete copias diarias más recientes. Un fallo de verificación conserva las anteriores; archivos ajenos no se eliminan.
- Límite de copia lógica de 32 MiB y función de hasta 300 segundos. Son límites de esta implementación académica, no una garantía para cualquier volumen de producción.

La planificación `0 6 * * *` (03:00–03:59 de Ushuaia en Hobby) queda en [un archivo de ejemplo](cron-backup.example.json), **sin incorporarse a `vercel.json`**. No hay cron productivo configurado para esta tarea. Una futura activación requerirá una decisión explícita sobre datos, almacenamiento, retención y seguimiento.

## Recuperar una copia cifrada

La clave preparada se conserva como Secret de Production y en `.env.backup-secrets.local`, archivo privado local de permisos 0600 excluido de Git. No se publica. Para futuras copias reales, conservar también la clave en un gestor privado: perderla impide recuperar los archivos cifrados.

Descargar el archivo desde el almacén privado con una cuenta autorizada. Cargar la clave correspondiente en un entorno de confianza y ejecutar:

```sh
python manage.py decrypt_backup --input /ruta/privada/copia.fernet --output /ruta/privada/restauracion.backup.json
```

El comando autentica y descifra a un archivo nuevo de permisos 0600; **no modifica ninguna base**. Después seguir el procedimiento de restauración aislada.

## Evidencia de las pruebas

- Copia/restauración local: usuarios, prestador, categorías, ofertas, solicitud, historial y aviso conservados con igualdad de campos. [Registro](../evidencias/recuperacion.json).
- PostgreSQL Neon aislado: 500 ofertas ficticias, usuario, prestador y categoría restaurados con igualdad de campos, en 321,580 s. Esa muestra no incluía reservas. [Registro](../evidencias/recuperacion-postgresql.json).
- Almacén privado real: archivo de una categoría ficticia cifrado, subido y recuperado; acceso anónimo rechazado con HTTP 403 y archivo de prueba eliminado. [Registro](../evidencias/almacen-respaldo.json).
- Circuito cifrado completo: base temporal con cuatro cuentas ficticias, oferta, reserva confirmada, historial, avisos y moderación; respaldo privado, repetición sin sobrescribir, descarga, descifrado y restauración en otra base. Igualdad de todos los campos en ocho modelos, en 3,269 s. Sin acceso a la base productiva ni activación de cron; copia de prueba eliminada. [Registro](../evidencias/respaldo-academico-e2e.json).
- Siete pruebas específicas: cifrado/descifrado; clave incorrecta y manipulación rechazadas; exclusión de Preview; autenticación/método/caché; reenvío sin sobrescritura; verificación previa a retención; preservación de copias ante fallos. Suite completa: 73 pruebas Django, 69 aprobadas y cuatro omitidas por requerir PostgreSQL; cinco pruebas JavaScript aprobadas. Las cuatro concurrentes tienen evidencia PostgreSQL previa en el README.

La preparación y estas pruebas cierran **RNF-06 académico revisado**. No se afirma que se haya ejecutado ni activado un respaldo diario de datos productivos. Para una operación comercial futura se deberán definir cuotas, seguimiento de fallos, retención y custodia de claves.

Fuentes oficiales consultadas el 21/11/2026: [Cron y límites Hobby](https://vercel.com/docs/schedules/cron-jobs/usage-and-pricing), [autenticación del cron](https://vercel.com/docs/schedules/cron-jobs/manage-cron-jobs), [Blob privado](https://vercel.com/docs/vercel-blob/private-storage) y [SDK Python](https://vercel.com/docs/vercel-blob/python-sdk-reference).
