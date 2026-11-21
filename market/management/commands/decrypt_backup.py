import os
from pathlib import Path
from django.core.management import BaseCommand, CommandError
from market.daily_backup import decrypt_snapshot


class Command(BaseCommand):
    help = 'Descifra una copia descargada a un archivo privado nuevo; no modifica la base.'

    def add_arguments(self, parser):
        parser.add_argument('--input', required=True)
        parser.add_argument('--output', required=True)

    def handle(self, *args, **options):
        try:
            raw = decrypt_snapshot(Path(options['input']).read_bytes())
        except Exception as exc:
            raise CommandError('No se pudo autenticar y descifrar la copia. Revisá la clave y el archivo.') from None
        try:
            descriptor = os.open(Path(options['output']), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except OSError:
            raise CommandError('El destino debe ser un archivo nuevo en una carpeta privada.') from None
        with os.fdopen(descriptor, 'wb') as output:
            output.write(raw)
        self.stdout.write(self.style.SUCCESS('Copia descifrada. Restaurá únicamente en una base aislada.'))
