# Evaluación de rendimiento

20/11/2026: 500 ofertas publicadas ficticias, 20 clientes de consulta y 100 solicitudes HTTP al catálogo paginado. Entorno: macOS arm64, Python 3.14.6, Django 5.2.19, servidor local y base aislada en Neon PostgreSQL (iad1). Se incluye latencia de la base remota. No se midieron CDN, TLS ni capacidad de producción Vercel.

Resultado válido: p95 2,269 s, mediana 2,143 s, 100 respuestas HTTP 200, cero errores. Se cumple RNF-01 en este entorno. [Registro de solicitudes](../evidencias/rendimiento.json).

La primera corrida tuvo rechazos por el límite de cola de conexiones del servidor de desarrollo. Se descartó como acreditación de la meta y se repitió con una cola de 128 conexiones. No se ocultaron errores dentro del cálculo del percentil. La medición no representa una recomendación de usar `runserver` en producción.

Para repetir: preparar una base vacía **de evaluación**, migrarla y crear 500 ofertas con fechas futuras, precio y cupo válidos. El catálogo devuelve 24 por página. Arrancar el servidor local sobre esa base. Para evitar que la cola del servidor de desarrollo rechace los 20 clientes antes de evaluar Django:

```sh
python -c "from django.core.servers.basehttp import WSGIServer; WSGIServer.request_queue_size=128; from django.core.management import execute_from_command_line; execute_from_command_line(['manage.py','runserver','127.0.0.1:8766','--noreload'])"
```

Desde otra terminal, luego de comprobar que la portada responde:

```sh
python scripts/benchmark_catalog.py --output /tmp/ushlm-rendimiento.json
```

El script acepta únicamente un servidor local para evitar carga accidental sobre el sitio publicado. Registrar también configuración de equipo, versión, cantidad de ofertas y cambios entre mediciones. La salida no contiene contactos ni cadenas de conexión.
