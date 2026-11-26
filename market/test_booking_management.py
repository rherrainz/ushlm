from django.contrib.auth.models import Permission, User
from django.core.exceptions import PermissionDenied
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from .models import Booking, BookingHistory, Notification, Offer, Provider
from .services import transition
from .tests import Fixtures


class BookingManagementTests(Fixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.administrator = User.objects.create_user('administrator', password='Local-test-123!',
                                                     is_staff=True, is_superuser=True)
        self.staff = User.objects.create_user('staff', password='Local-test-123!', is_staff=True)
        self.booking = self.request()
        self.url = reverse('booking_management')
        self.confirm = reverse('action', args=[self.booking.pk, 'confirm'])

    def test_admin_can_approve_from_site_with_stock_history_and_notices(self):
        self.client.force_login(self.administrator)
        self.assertContains(self.client.get(reverse('catalog')), 'Gestionar solicitudes')
        page = self.client.get(self.url)
        self.assertContains(page, 'Aceptar solicitud')
        self.assertContains(page, 'demo@example.invalid')
        self.assertNotContains(page, 'Cancelar solicitud pendiente')
        response = self.client.post(self.confirm, {'return_to': 'booking_management'})
        self.assertRedirects(response, self.url)
        self.booking.refresh_from_db()
        self.offer.refresh_from_db()
        self.assertEqual(self.booking.status, 'confirmed')
        self.assertEqual(self.offer.stock, 1)
        self.assertEqual(self.offer.stock_version, 1)
        event = BookingHistory.objects.get(booking=self.booking, current='confirmed')
        self.assertEqual(event.actor_id, self.administrator.pk)
        self.assertEqual(event.reason, 'Aceptada por administración.')
        recipients = Notification.objects.filter(booking=self.booking, message__contains='Confirmada').values_list('recipient_id', flat=True)
        self.assertCountEqual(recipients, [self.tourist.pk, self.owner.pk])
        self.client.post(self.confirm)
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.stock, 1)
        self.assertEqual(self.offer.stock_version, 1)
        self.assertEqual(self.booking.history.filter(current='confirmed').count(), 1)

    def test_provider_can_approve_from_same_page_and_keeps_existing_dashboard(self):
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(self.url), 'Aceptar solicitud')
        self.assertContains(self.client.get(reverse('dashboard')), 'Gestionar solicitudes')
        self.assertRedirects(self.client.post(self.confirm, {'return_to':'booking_management'}), self.url)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'confirmed')
        self.assertEqual(self.booking.history.get(current='confirmed').reason, 'Aceptada por el prestador.')

    def test_provider_isolation_and_tourist_cannot_manage(self):
        Provider.objects.create(owner=self.other, name='Otro prestador', contact='otro@example.invalid', enabled=True)
        self.client.force_login(self.other)
        page = self.client.get(self.url)
        self.assertNotContains(page, self.offer.title)
        self.assertNotContains(page, self.booking.contact)
        self.assertNotContains(page, 'Aceptar solicitud')
        self.assertEqual(self.client.post(self.confirm).status_code, 403)
        self.client.force_login(self.tourist)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.confirm).status_code, 403)
        self.assertNotContains(self.client.get(reverse('catalog')), 'Gestionar solicitudes')

    def test_staff_requires_explicit_permission_and_inactive_admin_is_denied(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.confirm).status_code, 403)
        self.staff.user_permissions.add(Permission.objects.get(codename='change_booking'))
        self.assertContains(self.client.get(self.url), 'Aceptar solicitud')
        self.assertRedirects(self.client.post(self.confirm), self.url)
        self.administrator.is_active = False
        self.administrator.save(update_fields=['is_active'])
        with self.assertRaises(PermissionDenied):
            transition(self.administrator, self.booking.pk, 'reject')

    def test_admin_views_all_providers_and_cannot_cancel_as_tourist(self):
        other_provider = Provider.objects.create(owner=self.other, name='Otro', contact='otro', enabled=True)
        self.offer.pk = None
        self.offer.provider = other_provider
        self.offer.title = 'Otra experiencia'
        self.offer.save()
        from uuid import uuid4
        from .services import offer_quote, request_booking
        other_booking = request_booking(self.tourist, self.offer.pk, 1, 'otro-contacto', uuid4(), offer_quote(self.offer))
        self.client.force_login(self.administrator)
        page = self.client.get(self.url)
        self.assertContains(page, 'Beagle')
        self.assertContains(page, 'Otra experiencia')
        self.assertEqual(self.client.post(reverse('action', args=[other_booking.pk,'cancel_pending'])).status_code, 403)
        self.client.force_login(self.owner)
        self.assertNotContains(self.client.get(self.url), 'Otra experiencia')

    def test_filters_and_safe_redirect(self):
        transition(self.owner, self.booking.pk, 'confirm')
        self.client.force_login(self.administrator)
        self.assertNotContains(self.client.get(self.url), 'Beagle')
        self.assertContains(self.client.get(self.url, {'status':'confirmed'}), 'Beagle')
        self.assertContains(self.client.get(self.url, {'status':'all'}), 'Beagle')
        self.assertNotContains(self.client.get(self.url, {'status':'invalid'}), 'Beagle')
        self.client.force_login(self.owner)
        response = self.client.post(reverse('action',args=[self.booking.pk,'cancel_confirmed']),
                                    {'reason':'Prueba', 'return_to':'https://example.invalid'})
        self.assertRedirects(response, reverse('dashboard'))

    def test_post_and_csrf_required(self):
        self.client.force_login(self.administrator)
        self.assertEqual(self.client.get(self.confirm).status_code, 405)
        secure = Client(enforce_csrf_checks=True)
        secure.force_login(self.administrator)
        self.assertEqual(secure.post(self.confirm).status_code, 403)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'pending')

    def test_admin_cannot_bypass_expiry_stock_moderation_or_provider_suspension(self):
        self.client.force_login(self.administrator)
        for changes in ({'stock':0}, {'moderated':True}):
            before = {field:getattr(self.offer,field) for field in changes}
            Offer.objects.filter(pk=self.offer.pk).update(**changes)
            self.client.post(self.confirm)
            self.booking.refresh_from_db()
            self.assertEqual(self.booking.status, 'pending')
            Offer.objects.filter(pk=self.offer.pk).update(**before)
        self.provider.enabled = False
        self.provider.save(update_fields=['enabled'])
        self.client.post(self.confirm)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'pending')
        self.provider.enabled = True
        self.provider.save(update_fields=['enabled'])
        Offer.objects.filter(pk=self.offer.pk).update(expires_at=timezone.now()-timedelta(seconds=1))
        self.client.post(self.confirm)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'expired')
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.stock, 2)

    def test_admin_reject_and_cancellation_follow_existing_rules(self):
        self.client.force_login(self.administrator)
        self.client.post(reverse('action',args=[self.booking.pk,'reject']), {'reason':'Sin disponibilidad'})
        self.booking.refresh_from_db()
        self.offer.refresh_from_db()
        self.assertEqual(self.booking.status, 'rejected')
        self.assertEqual(self.offer.stock, 2)
        second = self.request()
        transition(self.administrator, second.pk, 'confirm')
        cancel = reverse('action',args=[second.pk,'cancel_confirmed'])
        self.client.post(cancel, {'reason':''})
        second.refresh_from_db()
        self.assertEqual(second.status, 'confirmed')
        self.client.post(cancel, {'reason':'Cancelación de prueba'})
        self.client.post(cancel, {'reason':'Reintento'})
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.stock, 2)
        self.assertEqual(second.history.filter(current='cancelled').count(), 1)

    def test_pagination_keeps_status(self):
        for _ in range(24): self.request()
        self.client.force_login(self.administrator)
        first = self.client.get(self.url, {'status':'all'})
        self.assertContains(first, '?status=all&amp;page=2')
        second = self.client.get(self.url, {'status':'all', 'page':2})
        self.assertEqual(len(second.context['bookings']), 1)
