from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from market.demo_renewal import renew_demo_offers


class Command(BaseCommand):
    help = 'Publica la edición vigente de las tres ofertas demo configuradas, una vez por ciclo de 48 h.'

    def handle(self, *args, **options):
        try:
            result = renew_demo_offers()
        except ValidationError as exc:
            raise CommandError('; '.join(exc.messages)) from exc
        self.stdout.write(str(result))
