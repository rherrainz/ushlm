from django.core.management.base import BaseCommand
from market.services import expire_pending
class Command(BaseCommand):
    help = 'Vence solicitudes pendientes y registra historial. Ejecutar periódicamente.'
    def handle(self, *args, **options): self.stdout.write(f'{expire_pending()} solicitudes vencidas.')
