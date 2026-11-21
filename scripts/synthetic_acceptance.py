"""Five synthetic HTTP journeys. Never represents human usability testing."""
import json
import os
import secrets
import sys
import tempfile
import time
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
os.environ['DJANGO_SECRET_KEY'] = secrets.token_urlsafe(64)
os.environ['DJANGO_DEBUG'] = '0'
os.environ.pop('VERCEL', None)
os.environ.pop('DATABASE_URL', None)
os.environ.pop('DATABASE_ENGINE', None)

from django.conf import settings


def run():
    with tempfile.TemporaryDirectory(prefix='ushlm-synthetic-') as temporary:
        settings.DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': str(Path(temporary) / 'evaluation.sqlite3')}}
        settings.ALLOWED_HOSTS = ['testserver']
        import django
        django.setup()
        from django.contrib.auth.models import User
        from django.core.management import call_command
        from django.db import connections
        from django.test import Client
        from django.test.utils import setup_test_environment
        from django.utils import timezone
        from market.models import Booking, Category, Notification, Offer, Provider
        setup_test_environment()
        call_command('migrate', interactive=False, verbosity=0)
        password = secrets.token_urlsafe(24)
        owner = User.objects.create_user('synthetic_provider', password=password)
        provider = Provider.objects.create(owner=owner, name='Prestador sintético', contact='provider@example.invalid', enabled=True)
        now = timezone.now()
        offers = {}
        for kind, unit, occupancy in [('tour', 'persona', None), ('stay', 'habitación', 2), ('car', 'auto', None)]:
            category = Category.objects.create(kind=kind)
            offers[kind] = Offer.objects.create(provider=provider, category=category, title=f'Oferta sintética {kind}', description='Servicio ficticio', location='Ushuaia', starts_at=now+timedelta(hours=24), ends_at=now+timedelta(hours=48), expires_at=now+timedelta(hours=20), unit=unit, occupancy=occupancy, reference_price=Decimal('100.00'), price=Decimal('70.00'), stock=10, conditions='Condiciones ficticias de prueba', status='published')

        def post(client, path, data):
            return client.post(path, {**data, 'csrfmiddlewaretoken': client.cookies['csrftoken'].value})

        staff = Client(enforce_csrf_checks=True)
        staff.get('/cuenta/login/')
        assert post(staff, '/cuenta/login/', {'username': owner.username, 'password': password}).status_code == 302
        results = []
        scenarios = [('S1', 'tour', 'Recorrido principal'), ('S2', 'stay', 'Cantidad inválida y corrección'), ('S3', 'car', 'Aislamiento entre turistas'), ('S4', 'tour', 'Reenvío idempotente'), ('S5', 'stay', 'Orden por precio y moneda')]
        for identifier, kind, variant in scenarios:
            start = time.perf_counter()
            client = Client(enforce_csrf_checks=True)
            client.get('/registro/')
            username = identifier.lower()
            response = post(client, '/registro/', {'username': username, 'first_name': identifier, 'email': f'{username}@example.invalid', 'password1': password, 'password2': password})
            assert response.status_code == 302, 'Registro rechazado'
            query = {'category': kind}
            if identifier == 'S5': query.update(order='price', currency='ARS')
            catalog = client.get('/', query)
            assert catalog.status_code == 200
            offer = offers[kind]
            assert offer.pk in [item.pk for item in catalog.context['offers']]
            detail = client.get(f'/ofertas/{offer.pk}/')
            assert detail.status_code == 200
            form = detail.context['form']
            data = {'quantity': 2, 'contact': f'{username}@example.invalid', 'token': str(form['token'].value()), 'quote': form['quote'].value()}
            endpoint = f'/ofertas/{offer.pk}/solicitar/'
            if identifier == 'S2':
                before = Booking.objects.count()
                assert post(client, endpoint, {**data, 'quantity': 0}).status_code == 400
                assert Booking.objects.count() == before
            if identifier == 'S3':
                previous = Booking.objects.first()
                assert post(client, f'/solicitudes/{previous.pk}/cancel_pending/', {}).status_code == 403
                assert previous.service['title'] not in client.get('/mis-solicitudes/').content.decode()
            preview = post(client, endpoint, {**data, 'intent': 'preview'})
            assert preview.status_code == 200
            assert preview.context['preview_total'] == Decimal('140.00')
            offer.refresh_from_db()
            initial_stock = offer.stock
            assert post(client, endpoint, {**data, 'intent': 'request'}).status_code == 302
            booking = Booking.objects.get(tourist__username=username)
            assert booking.status == 'pending' and booking.total == Decimal('140.00')
            offer.refresh_from_db()
            assert offer.stock == initial_stock
            assert 'Pendiente' in client.get('/mis-solicitudes/').content.decode()
            if identifier == 'S4':
                before = Booking.objects.count()
                assert post(client, endpoint, {**data, 'intent': 'request'}).status_code == 302
                assert Booking.objects.count() == before
            notice = Notification.objects.get(recipient=owner, booking=booking)
            assert 'Sin leer' in staff.get('/avisos/').content.decode()
            assert post(staff, f'/avisos/{notice.pk}/leer/', {}).status_code == 302
            notice.refresh_from_db()
            assert notice.read_at is not None
            staff.get('/prestador/')
            assert post(staff, f'/solicitudes/{booking.pk}/confirm/', {}).status_code == 302
            booking.refresh_from_db(); offer.refresh_from_db()
            assert booking.status == 'confirmed' and offer.stock == initial_stock - 2
            assert booking.history.count() == 2
            response_notice = Notification.objects.get(recipient=booking.tourist, booking=booking)
            assert 'Confirmada' in response_notice.message
            client.get('/avisos/')
            assert post(client, f'/avisos/{response_notice.pk}/leer/', {}).status_code == 302
            assert 'Confirmada' in client.get('/mis-solicitudes/').content.decode()
            results.append({'scenario': identifier, 'variant': variant, 'category': kind, 'passed': True, 'http_execution_seconds': round(time.perf_counter()-start, 3), 'total': 'ARS 140.00', 'final_status': 'confirmed', 'stock_decrement': 2})
        report = {'executed_at': timezone.now().isoformat(), 'kind': 'synthetic_http_acceptance', 'environment': 'Django Client with CSRF enforcement, isolated temporary SQLite database', 'human_participants': 0, 'scenarios_passed': len(results), 'scenarios_total': len(scenarios), 'results': results, 'limitations': ['No human usability evaluation or five-minute task completion measurement.', 'No browser rendering, JavaScript, keyboard or multi-browser verification.', 'SQLite does not verify concurrent PostgreSQL locking; see separate PostgreSQL evidence.', 'Execution times measure automated HTTP operations, not human interaction time.'], 'production_modified': False}
        destination = ROOT / 'evidencias' / 'aceptacion-sintetica.json'
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
        connections.close_all()
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    run()
