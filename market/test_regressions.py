import uuid
from datetime import timedelta
from decimal import Decimal
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from .models import Booking, Offer, Provider
from .services import adjust_inventory, offer_quote, request_booking, transition
from .tests import Fixtures


class InventoryRegressionTests(Fixtures, TestCase):
    def edit_data(self, admin=False):
        data = {name: getattr(self.offer,name) for name in
                ['title','description','location','unit','reference_price','price','currency','conditions','status']}
        data.update(category=self.category.pk)
        for name in ['starts_at','ends_at','expires_at']:
            value = timezone.localtime(getattr(self.offer,name))
            if admin:
                data[name+'_0'] = value.strftime('%Y-%m-%d')
                data[name+'_1'] = value.strftime('%H:%M:%S')
            else:
                data[name] = value.strftime('%Y-%m-%dT%H:%M')
        return data

    def make_admin(self):
        self.owner.is_staff = True
        self.owner.is_superuser = True
        self.owner.save()
        self.client.force_login(self.owner)

    def test_old_provider_form_cannot_restore_sold_stock(self):
        self.client.force_login(self.owner)
        url = reverse('edit_offer',args=[self.offer.pk])
        opened = self.client.get(url)
        self.assertNotIn('stock',opened.context['form'].fields)
        data = self.edit_data()
        data.update(stock=2, stock_version=0, description='Solo cambió descripción')
        booking = self.request()
        transition(self.owner,booking.pk,'confirm')
        self.assertRedirects(self.client.post(url,data),reverse('dashboard'))
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.stock,1)
        self.assertEqual(self.offer.stock_version,1)
        self.assertEqual(self.offer.description,'Solo cambió descripción')

    def test_old_admin_form_cannot_restore_sold_stock(self):
        # The tourist creates the booking before the owner becomes an administrator.
        booking = self.request()
        self.make_admin()
        url = reverse('admin:market_offer_change',args=[self.offer.pk])
        opened = self.client.get(url)
        self.assertNotIn('stock',opened.context['adminform'].form.fields)
        data = self.edit_data(admin=True)
        data.update(stock=2,stock_version=0,description='Cambio administrativo',_save='Guardar')
        transition(self.owner,booking.pk,'confirm')
        response = self.client.post(url,data)
        self.assertEqual(response.status_code,302)
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.stock,1)
        self.assertEqual(self.offer.stock_version,1)
        self.assertEqual(self.offer.description,'Cambio administrativo')

    def test_general_post_injected_inventory_ignored(self):
        self.client.force_login(self.owner)
        data = self.edit_data()
        data.update(stock=999,stock_version=999,new_stock=999,expected_version=0)
        self.client.post(reverse('edit_offer',args=[self.offer.pk]),data)
        self.offer.refresh_from_db()
        self.assertEqual((self.offer.stock,self.offer.stock_version),(2,0))

    def test_new_offer_general_post_starts_at_zero(self):
        self.client.force_login(self.owner)
        data = self.edit_data()
        data.update(title='Nueva sin inventario',stock=999,stock_version=99)
        self.assertEqual(self.client.post(reverse('new_offer'),data).status_code,302)
        created = Offer.objects.get(title='Nueva sin inventario')
        self.assertEqual((created.stock,created.stock_version),(0,0))

    def test_two_adjustments_from_same_version_conflict(self):
        self.client.force_login(self.owner)
        url = reverse('inventory',args=[self.offer.pk])
        first = self.client.get(url).context['form'].initial
        second = self.client.get(url).context['form'].initial
        self.assertEqual(self.client.post(url,{**first,'new_stock':5}).status_code,302)
        response = self.client.post(url,{**second,'new_stock':8})
        self.assertContains(response,'El inventario cambió',status_code=409)
        self.assertEqual(response.context['form']['new_stock'].value(), '8')
        self.assertEqual(self.client.post(url,{**second,'new_stock':8}).status_code,409)
        self.offer.refresh_from_db()
        self.assertEqual((self.offer.stock,self.offer.stock_version),(5,1))

    def test_confirmation_and_refund_invalidate_inventory_form(self):
        booking = self.request()
        transition(self.owner,booking.pk,'confirm')
        with self.assertRaises(ValidationError): adjust_inventory(self.owner,self.offer.pk,7,0)
        transition(self.owner,booking.pk,'cancel_confirmed','Devolución')
        with self.assertRaises(ValidationError): adjust_inventory(self.owner,self.offer.pk,7,1)
        self.offer.refresh_from_db()
        self.assertEqual((self.offer.stock,self.offer.stock_version),(2,2))
        self.assertEqual(booking.history.count(),3)

    def test_inventory_invalid_values_and_permissions(self):
        for stock in [-1,1.5,'1',True,2147483648]:
            with self.subTest(stock=stock), self.assertRaises(ValidationError):
                adjust_inventory(self.owner,self.offer.pk,stock,0)
        for version in [-1,0.5,'0',True]:
            with self.subTest(version=version), self.assertRaises(ValidationError):
                adjust_inventory(self.owner,self.offer.pk,1,version)
        for user in [self.other,self.tourist]:
            with self.assertRaises(PermissionDenied): adjust_inventory(user,self.offer.pk,5,0)
        with self.assertRaises(PermissionDenied): adjust_inventory(self.other,self.offer.pk,5,0,as_admin=True)
        self.offer.refresh_from_db()
        self.assertEqual((self.offer.stock,self.offer.stock_version),(2,0))

    def test_inventory_endpoint_validation_ownership_and_csrf(self):
        url=reverse('inventory',args=[self.offer.pk])
        self.client.force_login(self.owner)
        for stock in ['-1','1.5','abc','2147483648']:
            self.assertEqual(self.client.post(url,{'new_stock':stock,'expected_version':0}).status_code,400)
        secure=Client(enforce_csrf_checks=True); secure.force_login(self.owner)
        self.assertEqual(secure.post(url,{'new_stock':3,'expected_version':0}).status_code,403)
        Provider.objects.create(owner=self.other,name='Otro',contact='Otro',enabled=True)
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(url,{'new_stock':5,'expected_version':0}).status_code,404)
        self.offer.refresh_from_db(); self.assertEqual(self.offer.stock,2)

    def test_admin_inventory_adjustment_conflict_and_permissions(self):
        self.make_admin()
        url=reverse('admin:market_offer_inventory',args=[self.offer.pk])
        self.assertEqual(self.client.get(url).status_code,200)
        self.assertEqual(self.client.post(url,{'new_stock':4,'expected_version':0}).status_code,302)
        self.assertEqual(self.client.post(url,{'new_stock':8,'expected_version':0}).status_code,409)
        self.assertEqual(self.client.post(url,{'new_stock':-1,'expected_version':1}).status_code,400)
        self.other.is_staff=True; self.other.save()
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(url,{'new_stock':8,'expected_version':1}).status_code,403)
        self.offer.refresh_from_db(); self.assertEqual((self.offer.stock,self.offer.stock_version),(4,1))
        self.other.user_permissions.add(Permission.objects.get(codename='change_offer'))
        self.assertEqual(self.client.post(url,{'new_stock':0,'expected_version':1}).status_code,302)
        self.offer.refresh_from_db(); self.assertEqual((self.offer.stock,self.offer.stock_version),(0,2))


class CatalogOrderingTests(Fixtures, TestCase):
    def test_default_discount_order_tie_break_and_expiry_option(self):
        # Absolute price: 20, 70, 500. Discount: 80%, 30%, 50%.
        # Expiry: 500 first, 20 second, 70 last. A fourth 50% tests the tie.
        self.offer.title='Descuento 30'; self.offer.save()
        def clone(title,price,reference,hours):
            offer=Offer.objects.get(pk=self.offer.pk)
            offer.pk=None
            offer.title=title; offer.price=Decimal(price); offer.reference_price=Decimal(reference)
            offer.expires_at=timezone.now()+timedelta(hours=hours)
            offer.save()
            return offer
        cheap=clone('Descuento 80','20','100',8)
        expensive=clone('Descuento 50 temprano','500','1000',2)
        tie=clone('Descuento 50 tarde','100','200',10)
        response=self.client.get('/')
        self.assertEqual(list(response.context['offers']),[cheap,expensive,tie,self.offer])
        self.assertEqual(response.context['order'],'discount')
        self.assertContains(response,'value="discount" selected')
        response=self.client.get('/?order=expires')
        self.assertEqual(list(response.context['offers']),[expensive,cheap,tie,self.offer])
        self.assertContains(response,'value="expires" selected')
        self.assertEqual(self.client.get('/?order=invalid').context['order'],'discount')


class QuoteRegressionTests(Fixtures, TestCase):
    def setUp(self):
        super().setUp()
        Offer.objects.filter(pk=self.offer.pk).update(price=Decimal('19.99'),stock=5)
        self.client.force_login(self.tourist)
        self.url=reverse('book',args=[self.offer.pk])

    def opened_data(self, quantity=3):
        opened=self.client.get(reverse('detail',args=[self.offer.pk]))
        return {**opened.context['form'].initial,'quantity':quantity,'contact':'guardado@example.invalid'}

    def test_decimal_total_before_submit_and_server_preview(self):
        data=self.opened_data()
        response=self.client.post(self.url,{**data,'intent':'preview'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.context['preview_total'],Decimal('59.97'))
        self.assertContains(response,'59,97')
        self.assertContains(response,'Precio por persona: ARS')
        self.assertEqual(Booking.objects.count(),0)
        self.client.post(self.url,data)
        booking=Booking.objects.get()
        self.assertEqual((booking.price,booking.total),(Decimal('19.99'),Decimal('59.97')))

    def test_tampered_prices_and_totals_not_trusted(self):
        data=self.opened_data()
        data.update(price='0.01',total='0.03',currency='USD',conditions='Inventadas')
        self.assertEqual(self.client.post(self.url,data).status_code,302)
        booking=Booking.objects.get()
        self.assertEqual(booking.price,Decimal('19.99'))
        self.assertEqual(booking.total,Decimal('59.97'))
        self.assertEqual(booking.currency,'ARS')
        self.assertEqual(booking.conditions,'Condiciones originales')

    def test_price_change_requires_review_and_resubmission(self):
        data=self.opened_data()
        Offer.objects.filter(pk=self.offer.pk).update(price=Decimal('24.50'))
        response=self.client.post(self.url,data)
        self.assertContains(response,'La oferta cambió',status_code=409)
        self.assertEqual(Booking.objects.count(),0)
        self.assertEqual(response.context['preview_total'],Decimal('73.50'))
        self.assertEqual(response.context['form']['contact'].value(),data['contact'])
        fresh=response.context['form']['quote'].value()
        self.assertNotEqual(fresh,data['quote'])
        self.assertEqual(self.client.post(self.url,{**data,'quote':fresh}).status_code,302)
        booking=Booking.objects.get()
        self.assertEqual(booking.total,Decimal('73.50'))
        # A retry of the original request is idempotent, even after further edits.
        Offer.objects.filter(pk=self.offer.pk).update(price=Decimal('30.00'))
        self.assertEqual(self.client.post(self.url,{**data,'quote':fresh}).status_code,302)
        self.assertEqual(Booking.objects.count(),1)
        self.assertEqual(Booking.objects.get().price,Decimal('24.50'))

    def test_conditions_change_requires_review(self):
        data=self.opened_data()
        Offer.objects.filter(pk=self.offer.pk).update(conditions='Nuevas condiciones')
        response=self.client.post(self.url,data)
        self.assertContains(response,'Nuevas condiciones',status_code=409)
        self.assertEqual(Booking.objects.count(),0)
        self.client.post(self.url,{**data,'quote':response.context['form']['quote'].value()})
        self.assertEqual(Booking.objects.get().conditions,'Nuevas condiciones')

    def test_invalid_or_missing_signature_cannot_create_booking(self):
        data=self.opened_data()
        self.assertEqual(self.client.post(self.url,{**data,'quote':'tampered'}).status_code,409)
        data.pop('quote')
        self.assertEqual(self.client.post(self.url,data).status_code,400)
        self.assertEqual(Booking.objects.count(),0)

    def test_invalid_quantities_never_create_booking(self):
        for quantity in ['0','-1','1.5','abc','2147483648']:
            with self.subTest(quantity=quantity):
                response=self.client.post(self.url,self.opened_data(quantity))
                self.assertEqual(response.status_code,400)
                self.assertIsNone(response.context['preview_total'])
        self.assertEqual(Booking.objects.count(),0)

    def test_service_checks_signature_inside_transaction(self):
        data=self.opened_data(1)
        Offer.objects.filter(pk=self.offer.pk).update(conditions='Cambio posterior al GET')
        with self.assertRaises(ValidationError):
            request_booking(self.tourist,self.offer.pk,1,'demo@example.invalid',uuid.uuid4(),data['quote'])
        self.assertEqual(Booking.objects.count(),0)
