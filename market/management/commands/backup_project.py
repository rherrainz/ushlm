"""Logical snapshot. Keep private: includes contact information and password hashes."""
import os
from pathlib import Path
from django.core.management import BaseCommand, CommandError, call_command
from django.db import transaction


class Command(BaseCommand):
    help = 'Crea una copia lógica privada; el destino debe ser nuevo y quedar fuera de Git.'

    def add_arguments(self, parser):
        parser.add_argument('--output', required=True)

    def handle(self, *args, **options):
        destination = Path(options['output']).expanduser().resolve()
        try:
            descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except OSError as exc:
            raise CommandError('No se pudo crear una copia nueva. Verificá carpeta y permisos.') from exc
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                # PostgreSQL READ COMMITTED changes snapshots between statements;
                # REPEATABLE READ makes all serialized tables share one snapshot.
                from django.core import serializers
                serializers.register_serializer('precise_json', 'market.backup_serializer')
                from django.db import connection
                with transaction.atomic():
                    if connection.vendor == 'postgresql':
                        with connection.cursor() as cursor:
                            cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                    call_command('dumpdata', format='precise_json', natural_foreign=True, natural_primary=True,
                                 exclude=['sessions.session'], stdout=stream, verbosity=0)
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        self.stdout.write(self.style.SUCCESS('Copia lógica creada. Conservála privada y comprobá su restauración en otra base.'))
