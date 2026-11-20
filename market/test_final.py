from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, TransactionTestCase, Client
from django.urls import reverse
from .tests import Fixtures
from .models import Notification, OfferModeration, Offer
from .services import moderate_offer, transition


class FinalScopeTests(Fixtures, TestCase):
    def test_notification_creation_transition_and_no_duplicate_retry(self):
        booking = self.request()
        self.assertEqual(Notification.objects.filter(recipient=self.owner).count(), 1)
        self.request(token=booking.token)
        self.assertEqual(Notification.objects.count(), 1)
        transition(self.owner, booking.pk, 'confirm')
        self.assertTrue(Notification.objects.filter(recipient=self.tourist, booking=booking, message__contains='Confirmada').exists())

    def test_notification_is_private_and_read_is_post_only(self):
        self.request()
        notice = Notification.objects.get()
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(reverse('notifications')), notice.message)
        self.assertEqual(self.client.post(reverse('read_notification', args=[notice.pk])).status_code, 404)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse('read_notification', args=[notice.pk])).status_code, 405)
        self.assertRedirects(self.client.post(reverse('read_notification', args=[notice.pk])), reverse('notifications'))
        notice.refresh_from_db()
        self.assertIsNotNone(notice.read_at)
        first = notice.read_at
        self.client.post(reverse('read_notification', args=[notice.pk]))
        notice.refresh_from_db()
        self.assertEqual(notice.read_at, first)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.post(reverse('read_notification', args=[notice.pk])).status_code, 403)

    def test_moderation_requires_permission_reason_and_preserves_bookings(self):
        booking = self.request()
        with self.assertRaises(PermissionDenied): moderate_offer(self.owner, self.offer.pk, 'Motivo')
        admin = User.objects.create_superuser('moderator', 'moderator@example.invalid', 'Test-password-123')
        with self.assertRaises(ValidationError): moderate_offer(admin, self.offer.pk, '  ')
        moderate_offer(admin, self.offer.pk, 'Condiciones incompletas')
        self.assertFalse(Offer.objects.available().filter(pk=self.offer.pk).exists())
        event = OfferModeration.objects.get()
        self.assertEqual(event.actor, admin)
        self.assertEqual(event.reason, 'Condiciones incompletas')
        self.assertEqual(event.previous, 'published')
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'pending')
        self.assertTrue(Notification.objects.filter(recipient=self.owner, message__contains='retiró').exists())
        with self.assertRaises(ValidationError): transition(self.owner, booking.pk, 'confirm')
        with self.assertRaises(ValidationError): moderate_offer(admin, self.offer.pk, 'Otra vez')
        self.assertEqual(OfferModeration.objects.count(), 1)

    def test_admin_moderation_page(self):
        admin = User.objects.create_superuser('moderator', 'moderator@example.invalid', 'Test-password-123')
        self.client.force_login(admin)
        url = reverse('admin:market_offer_moderate', args=[self.offer.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertContains(self.client.post(url, {'reason': ''}), 'Este campo es obligatorio')
        self.assertEqual(self.client.post(url, {'reason':'Revisión de condiciones'}).status_code, 302)
        self.assertEqual(OfferModeration.objects.count(), 1)

    def test_moderated_offer_cannot_be_republished(self):
        admin = User.objects.create_superuser('moderator', 'moderator@example.invalid', 'Test-password-123')
        moderate_offer(admin, self.offer.pk, 'Corregir datos')
        self.offer.refresh_from_db()
        self.offer.status = 'published'
        with self.assertRaises(ValidationError): self.offer.full_clean()

    def test_price_order_requires_currency_and_does_not_mix_currencies(self):
        self.offer.currency = 'USD'
        self.offer.save()
        response = self.client.get(reverse('catalog'), {'order':'price'})
        self.assertContains(response, 'Elegí una moneda')
        response = self.client.get(reverse('catalog'), {'order':'price', 'currency':'ARS'})
        self.assertNotContains(response, 'Beagle')
        response = self.client.get(reverse('catalog'), {'order':'price', 'currency':'USD'})
        self.assertContains(response, 'Beagle')
        self.assertEqual(response.context['order'], 'price')

    def test_offer_preview_does_not_persist_changes(self):
        self.client.force_login(self.owner)
        from .forms import OfferForm
        form = OfferForm(instance=self.offer)
        data = {name: form[name].value() for name in form.fields}
        data = {name: value for name, value in data.items() if value is not None}
        data['title'] = 'Título revisado'
        data['intent'] = 'preview'
        response = self.client.post(reverse('edit_offer', args=[self.offer.pk]), data)
        self.assertContains(response, 'Confirmar y guardar')
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.title, 'Beagle')
        data['intent'] = 'save'
        self.assertEqual(self.client.post(reverse('edit_offer', args=[self.offer.pk]), data).status_code, 302)
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.title, 'Título revisado')


    def test_admin_general_form_cannot_close_without_a_reason(self):
        from .admin import AdminOfferForm
        from .forms import OfferForm
        source = OfferForm(instance=self.offer)
        data = {name:source[name].value() for name in source.fields if source[name].value() is not None}
        data.update(provider=self.provider.pk, status='closed')
        form = AdminOfferForm(data, instance=self.offer)
        self.assertFalse(form.is_valid())
        self.assertIn('motivo', str(form.non_field_errors()))

    def test_catalog_paginates_and_preserves_filters(self):
        from copy import copy
        offers = []
        for index in range(25):
            offer = copy(self.offer)
            offer.pk = None
            offer.title = f'Oferta {index}'
            offers.append(offer)
        Offer.objects.bulk_create(offers)
        response = self.client.get(reverse('catalog'), {'category':'tour','currency':'ARS'})
        self.assertEqual(len(response.context['offers']), 24)
        self.assertContains(response, 'category=tour&amp;currency=ARS&amp;page=2')


class BackupTests(Fixtures, TransactionTestCase):
    def test_backup_private_no_overwrite_and_datetime_precision(self):
        import io
        import json
        import tempfile
        from pathlib import Path
        from django.core.management import call_command, CommandError
        from django.db import connection
        self.request()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'snapshot.backup.json'
            call_command('backup_project', output=str(path), stdout=io.StringIO())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            rows = json.loads(path.read_text())
            offer = next(row for row in rows if row['model'] == 'market.offer')
            self.assertEqual(offer['fields']['starts_at'], self.offer.starts_at.isoformat())
            self.assertFalse(any(row['model'] == 'sessions.session' for row in rows))
            with self.assertRaises(CommandError):
                call_command('backup_project', output=str(path), stdout=io.StringIO())
