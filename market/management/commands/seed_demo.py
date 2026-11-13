from datetime import timedelta
from decimal import Decimal
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from market.models import Category, Provider, Offer

class Command(BaseCommand):
    help = 'Crea datos ficticios una sola vez. No modifica usuarios ni ofertas existentes.'
    def add_arguments(self, parser):
        parser.add_argument('--password', required=True, help='Contraseña local para las tres cuentas ficticias')
    @transaction.atomic
    def handle(self, *args, **options):
        names = ['turista_demo', 'prestador_demo', 'admin_demo']
        if User.objects.filter(username__in=names).exists():
            raise CommandError('Ya hay cuentas demo. No se sobrescribieron. Usá una base nueva para reiniciar.')
        accounts = {}
        for name in names:
            accounts[name] = User.objects.create_user(name, email=f'{name}@example.invalid', password=options['password'], first_name='Cuenta ficticia')
        admin = accounts['admin_demo']
        admin.is_staff = admin.is_superuser = True
        admin.save()
        provider = Provider.objects.create(owner=accounts['prestador_demo'], name='Fin del Mundo · DEMO', contact='contacto@example.invalid', enabled=True)
        now = timezone.now()
        data = [('tour','Navegá el canal Beagle','persona',None,'85000','59000',4), ('stay','Una noche en Ushuaia','habitación',2,'150000','105000',2), ('car','Recorré la isla a tu ritmo','auto',None,'120000','84000',1)]
        for index, (kind,title,unit,occupancy,reference,price,stock) in enumerate(data):
            category, _ = Category.objects.get_or_create(kind=kind)
            offer = Offer(provider=provider, category=category, title=title, description='Oferta ficticia para la demostración académica. Prestación de fecha y duración fijas.', location='Ushuaia, Tierra del Fuego', starts_at=now + timedelta(hours=24+index*4), ends_at=now + timedelta(hours=48+index*4), expires_at=now + timedelta(hours=20+index*4), unit=unit, occupancy=occupancy, reference_price=Decimal(reference), price=Decimal(price), currency='ARS', stock=stock, conditions='Precio por unidad indicada. Incluye únicamente el servicio descripto. Pago directo al prestador; sujeto a confirmación. Datos ficticios.', status='published')
            offer.full_clean()
            offer.save()
        self.stdout.write(self.style.SUCCESS('Demo creada: turista_demo, prestador_demo y admin_demo. Fechas relativas al momento de ejecución.'))
