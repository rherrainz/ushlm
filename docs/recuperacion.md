# Respaldo y recuperación

Una copia contiene contactos y hashes de contraseñas. Nunca se publica en Git ni como evidencia académica. El comando crea un archivo nuevo con permisos 0600 y una instantánea transaccional consistente. Excluye sesiones: una restauración requiere volver a iniciar sesión.

```sh
mkdir -p backups
python manage.py backup_project --output "backups/ushlm-$(date +%Y%m%d-%H%M%S).backup.json"
```

Usar las variables privadas de la base correcta, sin escribirlas en scripts ni logs. Cifrar la copia antes de transferirla a un almacenamiento privado. Mantener al menos siete copias diarias y una anterior a cada migración. Comprobar su fecha y resultado; disponer de un comando no acredita una programación diaria activa.

Para restaurar, crear una base **distinta y vacía** con la misma versión del código. Configurar `DATABASE_URL` de esa base en un entorno aislado, ejecutar `migrate` y luego `loaddata /ruta/privada/copia.backup.json`. Verificar cantidades de usuarios, prestadores, ofertas, solicitudes, historiales, moderaciones y avisos; comparar importes y estados. Ejecutar la guía de demostración. No restaurar sobre el sitio público.

El rollback de Vercel solo cambia código. No revierte datos. Ante un incidente: suspender las escrituras, conservar la base afectada, restaurar y verificar en otra base; recién después decidir el cambio de conexión. El objetivo del piloto es disponer de una copia diaria (pérdida máxima objetivo de 24 horas); el tiempo de recuperación se registra durante el ensayo, no se presume.

**Programación diaria:** pendiente de configurar en un ejecutor privado con almacenamiento y credenciales protegidos. No habilitar un endpoint público de descarga de respaldos ni entregar la conexión productiva a un preview. La recuperación histórica del proveedor puede complementar las copias, pero no sustituye un ensayo de restauración acreditado.

## Ensayos registrados

El 20/11/2026 se restauró una copia lógica en otra base PostgreSQL Neon aislada: 500 ofertas ficticias, un usuario, un prestador y una categoría; igualdad de todos los campos comparados, en 321,580 segundos. La muestra PostgreSQL no tenía solicitudes. El ensayo SQLite complementario incluyó una solicitud, su historial y un aviso, también con igualdad de campos. Ver los registros privados de datos solo localmente; las evidencias públicas contienen únicamente cantidades y resultados: [PostgreSQL](../evidencias/recuperacion-postgresql.json) y [SQLite](../evidencias/recuperacion.json).
