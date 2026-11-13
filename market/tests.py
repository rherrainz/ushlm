import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier
from unittest import skipUnless
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, connections
from django.db.models.deletion import ProtectedError
from django.test import TestCase, TransactionTestCase, Client
from django.urls import reverse
from django.utils import timezone
from .models import Booking, BookingHistory, Category, Offer, Provider
from .services import adjust_inventory, expire_pending, offer_quote, request_booking, transition

class Fixtures:
    def setUp(self):
        self.tourist = User.objects.create_user('tourist', password='DemoPass-12345')
        self.other = User.objects.create_user('other', password='DemoPass-12345')
        self.owner = User.objects.create_user('owner', password='DemoPass-12345')
        self.provider = Provider.objects.create(owner=self.owner, name='DEMO', contact='demo@example.invalid', enabled=True)
        self.category = Category.objects.create(kind='tour')
        now = timezone.now()
        self.offer = Offer.objects.create(provider=self.provider, category=self.category, title='Beagle', description='Original', location='Ushuaia', starts_at=now+timedelta(hours=24), ends_at=now+timedelta(hours=26), expires_at=now+timedelta(hours=20), unit='persona', reference_price=100, price=70, currency='ARS', stock=2, conditions='Condiciones originales', status='published')
    def request(self, user=None, quantity=1, token=None):
        return request_booking(user or self.tourist, self.offer.pk, quantity, 'demo@example.invalid', token or uuid.uuid4(), offer_quote(Offer.objects.get(pk=self.offer.pk)))

class RulesTests(Fixtures, TestCase):
    def test_invalid_prices(self):
        for price in [0, -1, 100, 110]:
            with self.subTest(price=price):
                self.offer.price = price
                with self.assertRaises(ValidationError): self.offer.full_clean()
    def test_invalid_dates(self):
        now = timezone.now()
        cases = [('starts_at',now+timedelta(hours=74)), ('expires_at',now-timedelta(seconds=1)), ('expires_at',now+timedelta(hours=25)), ('ends_at',now)]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                offer = Offer.objects.get(pk=self.offer.pk)
                setattr(offer, field, value)
                with self.assertRaises(ValidationError): offer.full_clean()
    def test_invalid_quantities(self):
        for quantity in [0,-1,1.5,'1',True,3]:
            with self.subTest(quantity=quantity):
                with self.assertRaises(ValidationError): self.request(quantity=quantity)
    def test_negative_stock_and_stay_occupancy(self):
        self.offer.stock = -1
        with self.assertRaises(ValidationError): self.offer.full_clean()
        self.offer.stock = 2
        self.category.kind = 'stay'; self.category.save()
        with self.assertRaises(ValidationError): self.offer.full_clean()
    def test_category_units(self):
        self.offer.unit = 'grupo'
        with self.assertRaises(ValidationError): self.offer.full_clean()
        self.category.kind = 'car'; self.category.save()
        with self.assertRaises(ValidationError): self.offer.full_clean()
        self.offer.unit = 'auto'
        self.offer.full_clean()
    def test_suspended_cannot_publish(self):
        self.provider.enabled = False; self.provider.save()
        self.offer.refresh_from_db()
        with self.assertRaises(ValidationError): self.offer.full_clean()
    def test_unavailable_catalog_and_request(self):
        for fields in [{'stock':0}, {'expires_at':timezone.now()-timedelta(seconds=1)}, {'status':'closed'}]:
            with self.subTest(fields=fields):
                original = {key:getattr(self.offer,key) for key in fields}
                Offer.objects.filter(pk=self.offer.pk).update(**fields)
                self.assertFalse(Offer.objects.available().exists())
                with self.assertRaises(ValidationError): self.request()
                Offer.objects.filter(pk=self.offer.pk).update(**original)
        self.provider.enabled=False; self.provider.save()
        self.assertFalse(Offer.objects.available().exists())
        with self.assertRaises(ValidationError): self.request()
    def test_pending_does_not_take_stock_and_retry_is_idempotent(self):
        token = uuid.uuid4()
        booking = self.request(token=token)
        self.assertEqual(self.request(token=token).pk, booking.pk)
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.stock, 2)
        self.assertEqual(Booking.objects.count(), 1)
        self.assertEqual(booking.history.count(), 1)
    def test_historical_snapshot(self):
        booking = self.request(quantity=2)
        Offer.objects.filter(pk=self.offer.pk).update(price=50, conditions='Nueva', description='Otra', unit='grupo')
        booking.refresh_from_db()
        self.assertEqual(booking.price, Decimal('70'))
        self.assertEqual(booking.total, Decimal('140'))
        self.assertEqual(booking.conditions, 'Condiciones originales')
        self.assertEqual(booking.description, 'Original')
        self.assertEqual(booking.service['unit'], 'persona')
    def test_confirm_only_once(self):
        booking = self.request()
        transition(self.owner, booking.pk, 'confirm')
        with self.assertRaises(ValidationError): transition(self.owner, booking.pk, 'confirm')
        self.offer.refresh_from_db(); booking.refresh_from_db()
        self.assertEqual(self.offer.stock, 1)
        self.assertEqual(booking.status,'confirmed')
        self.assertEqual(booking.history.count(),2)
    def test_insufficient_stock_rollback(self):
        first = self.request(quantity=2)
        second = self.request(self.other)
        transition(self.owner, first.pk, 'confirm')
        with self.assertRaises(ValidationError): transition(self.owner, second.pk, 'confirm')
        second.refresh_from_db()
        self.assertEqual(second.status,'pending')
        self.assertEqual(second.history.count(),1)
    def test_reject(self):
        booking = self.request()
        transition(self.owner, booking.pk, 'reject', 'Sin disponibilidad')
        booking.refresh_from_db(); self.offer.refresh_from_db()
        self.assertEqual(booking.status, 'rejected')
        self.assertEqual(self.offer.stock,2)
    def test_expire_idempotently(self):
        booking = self.request()
        Offer.objects.filter(pk=self.offer.pk).update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(expire_pending(),1)
        self.assertEqual(expire_pending(),0)
        booking.refresh_from_db()
        self.assertEqual(booking.status,'expired')
        self.assertIsNone(booking.history.last().actor)
    def test_accept_expired_records_expiry_without_sale(self):
        booking = self.request()
        Offer.objects.filter(pk=self.offer.pk).update(expires_at=timezone.now()-timedelta(seconds=1))
        transition(self.owner, booking.pk,'confirm')
        booking.refresh_from_db(); self.offer.refresh_from_db()
        self.assertEqual(booking.status,'expired')
        self.assertEqual(self.offer.stock,2)
    def test_pending_cancel(self):
        booking = self.request()
        transition(self.tourist, booking.pk,'cancel_pending')
        booking.refresh_from_db(); self.offer.refresh_from_db()
        self.assertEqual(booking.status,'cancelled')
        self.assertEqual(self.offer.stock,2)
    def test_confirmed_cancel_reason_and_one_refund(self):
        booking = self.request()
        transition(self.owner, booking.pk,'confirm')
        with self.assertRaises(ValidationError): transition(self.owner,booking.pk,'cancel_confirmed','')
        transition(self.owner,booking.pk,'cancel_confirmed','Motivo')
        with self.assertRaises(ValidationError): transition(self.owner,booking.pk,'cancel_confirmed','Otra vez')
        booking.refresh_from_db(); self.offer.refresh_from_db()
        self.assertTrue(booking.stock_returned)
        self.assertEqual(self.offer.stock,2)
    def test_no_refund_when_expired_or_suspended(self):
        booking = self.request()
        transition(self.owner,booking.pk,'confirm')
        Offer.objects.filter(pk=self.offer.pk).update(expires_at=timezone.now()-timedelta(seconds=1))
        transition(self.owner,booking.pk,'cancel_confirmed','Cancelación posterior')
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.stock,1)
    def test_suspended_provider_cancellation_does_not_return_stock(self):
        booking = self.request()
        transition(self.owner,booking.pk,'confirm')
        self.provider.enabled=False; self.provider.save()
        transition(self.owner,booking.pk,'cancel_confirmed','Prestador suspendido')
        self.offer.refresh_from_db(); booking.refresh_from_db()
        self.assertEqual(self.offer.stock,1)
        self.assertFalse(booking.stock_returned)
    def test_inactive_provider_hidden(self):
        self.owner.is_active=False; self.owner.save()
        self.assertFalse(Offer.objects.available().exists())
        with self.assertRaises(ValidationError): self.request()
    def test_permission_checks(self):
        booking = self.request()
        for user, action in [(self.other,'confirm'),(self.tourist,'reject'),(self.owner,'cancel_pending'),(self.other,'cancel_pending')]:
            with self.subTest(action=action,user=user):
                with self.assertRaises(PermissionDenied): transition(user,booking.pk,action)
        with self.assertRaises(PermissionDenied): self.request(self.owner)
    def test_token_cannot_be_reused_by_other_account(self):
        token = uuid.uuid4(); self.request(token=token)
        with self.assertRaises(PermissionDenied): self.request(self.other,token=token)
    def test_suspension_blocks_acceptance(self):
        booking = self.request(); self.provider.enabled=False; self.provider.save()
        with self.assertRaises(ValidationError): transition(self.owner,booking.pk,'confirm')
    def test_protected_history(self):
        booking = self.request()
        for obj in [self.offer, self.provider, self.tourist, booking]:
            with self.assertRaises(ProtectedError): obj.delete()

class WebTests(Fixtures, TestCase):
    def test_catalog_detail_filters(self):
        response = self.client.get('/')
        self.assertContains(response,'Beagle')
        self.assertNotContains(self.client.get('/?category=car'), 'Beagle')
        self.assertContains(self.client.get('/?date=bad'), 'Ingresá una fecha válida')
        self.assertEqual(self.client.get('/?order=discount').status_code,200)
        self.assertContains(self.client.get(reverse('detail',args=[self.offer.pk])),'Condiciones originales')
    def test_auth_and_csrf_and_post_only(self):
        url = reverse('book',args=[self.offer.pk])
        self.assertEqual(self.client.post(url).status_code,302)
        self.client.force_login(self.tourist)
        self.assertEqual(self.client.get(url).status_code,405)
        secure = Client(enforce_csrf_checks=True); secure.force_login(self.tourist)
        self.assertEqual(secure.post(url,{}).status_code,403)
        self.assertEqual(self.client.get('/cuenta/logout/').status_code,405)
    def test_book_form_preserves_errors_and_values(self):
        self.client.force_login(self.tourist)
        url = reverse('book',args=[self.offer.pk])
        response = self.client.post(url, {'quantity':0,'contact':'guardado','token':uuid.uuid4()})
        self.assertEqual(response.status_code,400)
        self.assertContains(response,'guardado',status_code=400)
        self.assertEqual(Booking.objects.count(),0)
    def test_full_flow_and_private_lists(self):
        self.client.force_login(self.tourist)
        self.client.post(reverse('book', args=[self.offer.pk]), dict(quantity=1, contact='privado@example.invalid', token=uuid.uuid4(), quote=offer_quote(Offer.objects.get(pk=self.offer.pk))))
        booking = Booking.objects.get()
        self.assertContains(self.client.get('/mis-solicitudes/'),'Pendiente')
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get('/mis-solicitudes/'),'Beagle')
        self.assertEqual(self.client.post(reverse('action',args=[booking.pk,'confirm'])).status_code,403)
        self.client.force_login(self.owner)
        self.assertContains(self.client.get('/prestador/'),'privado@example.invalid')
        self.client.post(reverse('action',args=[booking.pk,'confirm']))
        booking.refresh_from_db(); self.assertEqual(booking.status,'confirmed')
    def test_provider_isolation(self):
        other_provider = Provider.objects.create(owner=self.other,name='Otro',contact='otro',enabled=True)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse('edit_offer',args=[self.offer.pk])).status_code,404)
        self.assertNotContains(self.client.get('/prestador/'),'Beagle')
    def test_provider_can_create_and_edit_valid_offer(self):
        self.client.force_login(self.owner)
        data = {field: getattr(self.offer, field) for field in ['title','description','location','unit','reference_price','price','currency','stock','conditions','status']}
        data['category'] = self.category.pk
        for field in ['starts_at','ends_at','expires_at']:
            data[field] = timezone.localtime(getattr(self.offer,field)).strftime('%Y-%m-%dT%H:%M')
        data['title'] = 'Nueva oferta'
        self.assertRedirects(self.client.post('/prestador/nueva/',data), '/prestador/')
        created = Offer.objects.get(title='Nueva oferta')
        self.assertEqual(created.provider,self.provider)
        data['price'] = '55'
        self.assertRedirects(self.client.post(reverse('edit_offer',args=[created.pk]),data),'/prestador/')
        created.refresh_from_db(); self.assertEqual(created.price,Decimal('55'))
    def test_admin_login_and_read_only_history(self):
        self.owner.is_staff=True; self.owner.is_superuser=True; self.owner.save()
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get('/admin/market/offer/').status_code,200)
        self.assertEqual(self.client.get('/admin/market/booking/add/').status_code,403)
    def test_registration(self):
        response = self.client.post('/registro/', {'username':'nuevo','first_name':'Demo','email':'nuevo@example.invalid','password1':'DemoPass-12345','password2':'DemoPass-12345'})
        self.assertRedirects(response,'/')
        self.assertTrue(User.objects.get(username='nuevo').is_active)

@skipUnless(connection.vendor == 'postgresql', 'Requiere PostgreSQL real: SQLite no verifica bloqueos de fila.')
class PostgreSQLConcurrencyTests(Fixtures, TransactionTestCase):
    def test_last_unit_cannot_be_sold_twice(self):
        Offer.objects.filter(pk=self.offer.pk).update(stock=1)
        first = self.request(); second = self.request(self.other)
        barrier = Barrier(2)
        def accept(pk):
            try:
                user = User.objects.get(pk=self.owner.pk)
                barrier.wait(timeout=10)
                try: transition(user,pk,'confirm'); return 'confirmed'
                except ValidationError: return 'unavailable'
            finally: connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(accept,[first.pk,second.pk]))
        self.assertCountEqual(results,['confirmed','unavailable'])
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.stock,0)
        self.assertEqual(Booking.objects.filter(status='confirmed').count(),1)
    def test_same_booking_not_confirmed_twice(self):
        booking = self.request()
        barrier = Barrier(2)
        def accept(_):
            try:
                user=User.objects.get(pk=self.owner.pk)
                barrier.wait(timeout=10)
                try: transition(user,booking.pk,'confirm'); return True
                except ValidationError: return False
            finally: connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(accept,range(2)))
        self.assertCountEqual(results,[True,False])
        self.offer.refresh_from_db(); self.assertEqual(self.offer.stock,1)
        self.assertEqual(BookingHistory.objects.filter(booking=booking,current='confirmed').count(),1)

    def test_concurrent_cancellation_returns_stock_once(self):
        booking = self.request()
        transition(self.owner,booking.pk,'confirm')
        barrier = Barrier(2)
        def cancel(_):
            try:
                user=User.objects.get(pk=self.owner.pk)
                barrier.wait(timeout=10)
                try: transition(user,booking.pk,'cancel_confirmed','Motivo'); return True
                except ValidationError: return False
            finally: connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(cancel,range(2)))
        self.assertCountEqual(results,[True,False])
        self.offer.refresh_from_db(); self.assertEqual(self.offer.stock,2)

    def test_concurrent_inventory_adjustments_detect_conflict(self):
        barrier = Barrier(2)
        def adjust(stock):
            try:
                user = User.objects.get(pk=self.owner.pk)
                barrier.wait(timeout=10)
                try: adjust_inventory(user,self.offer.pk,stock,0); return True
                except ValidationError: return False
            finally: connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(adjust,[4,5]))
        self.assertCountEqual(results,[True,False])
        self.offer.refresh_from_db()
        self.assertIn(self.offer.stock,[4,5])
        self.assertEqual(self.offer.stock_version,1)
