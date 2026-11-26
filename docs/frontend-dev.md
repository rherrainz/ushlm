# Revisión del frontend en dev

La rama `dev` moderniza la interfaz manteniendo Django y los flujos de solicitud.
No incorpora cambios de esquema ni servicios de imágenes externos.

## Ejecutar con datos locales nuevos

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
export DJANGO_SECRET_KEY=local-dev-preview-only
export DJANGO_DEBUG=1
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_demo --password 'Elegir-una-clave-local'
.venv/bin/python manage.py runserver 127.0.0.1:8001
```

Usar una base SQLite nueva, sin `DATABASE_URL` ni variables de producción.
El comando de seed rechaza sobreescribir las cuentas existentes. Las cuentas
son `turista_demo`, `prestador_demo` y `admin_demo`, con la contraseña elegida.
Las ofertas tienen fechas relativas al seed y vencen: recrear la base demo si
se revisa en otro día, o ajustar las ofertas desde el panel local.

## Qué revisar antes del merge

- Portada horizontal en escritorio y vertical en móvil.
- Filtros, eliminación individual de filtros y estado sin resultados.
- Navegación disponible con teclado y sin JavaScript.
- Inicio de sesión, total por cantidad y envío de una solicitud pendiente.
- Panel del prestador, aceptación y avisos del turista.
- Formularios con errores que conservan lo ingresado.
- Fotos y controles sin desbordamiento a 320 px.

Los originales y la procedencia se documentan en
`static/market/images/photos/README.md`. Las fotos de categorías se identifican
como ilustrativas. La navegación usa una sola lista de enlaces, decide si cabe
en la cabecera por su ancho y mantiene los enlaces visibles si falla JavaScript.
El menú colapsado es una expansión en el flujo, sin bloqueo modal de foco.

No mergear hasta completar la revisión visual con el usuario.

## Verificación local — 25 de noviembre de 2026

- Django: 73 pruebas, 4 omitidas porque requieren PostgreSQL real; las restantes pasan en SQLite.
- JavaScript: 5 pruebas pasan; `navigation.js` pasa el chequeo de sintaxis.
- `manage.py check`, comprobación de migraciones y `git diff --check` sin errores.
- Navegador: escritorio a 1440 px; móvil a 390 px y control de desbordamiento a 320 px.
- Filtro de alojamiento devuelve una oferta; quitar el filtro recupera tres.
- Filtro USD sin ofertas muestra el estado vacío y permite volver al catálogo.
- Menú móvil abre, cierra con Escape y devuelve el foco al botón.
- Solicitud demo de 2 lugares: total ARS 118.000; confirmación del prestador;
  cupo de 4 a 2, estado persistido `confirmed` y aviso visible al turista.
- Fotografías de las tres categorías cargadas y ningún error de consola observado.

La base local incluye esa solicitud confirmada para poder revisar sus estados.
Las capturas están en `output/playwright/`, fuera del control de versiones.
