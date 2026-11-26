import io
from datetime import datetime, timedelta, timezone as datetime_timezone
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from .demo_renewal import INTERVAL, current_cycle, renew_demo_offers
from .models import Booking, DemoRefreshState, Offer
from .services import offer_quote, request_booking, transition
from django.contrib.auth.models import User


@override_settings(DEMO_RENEWAL_ENABLED=True, VERCEL_ENVIRONMENT='production', CRON_SECRET='test-cron')
class DemoRenewalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_demo', password='Test-local-only-123!', stdout=io.StringIO())
        cls.source_ids = tuple(Offer.objects.order_by('pk').values_list('pk', flat=True))

    def setUp(self):
        self.config = override_settings(DEMO_SOURCE_OFFER_IDS=self.source_ids)
        self.config.enable()
        self.addCleanup(self.config.disable)
        self.now = timezone.now()

    def run_at(self, now):
        with patch('django.utils.timezone.now', return_value=now):
            return renew_demo_offers(now)

    def test_new_edition_visible_and_original_dates_and_prices_preserved(self):
        originals = list(Offer.objects.order_by('pk').values('starts_at', 'ends_at', 'price', 'stock'))
        result = self.run_at(self.now)
        self.assertTrue(result['renewed'])
        self.assertEqual(len(result['offer_ids']), 3)
        self.assertFalse(set(result['offer_ids']) & set(self.source_ids))
        self.assertEqual(Offer.objects.available().count(), 3)
        for index, offer in enumerate(Offer.objects.filter(pk__in=result['offer_ids']).order_by('pk')):
            self.assertEqual(offer.starts_at, self.now + timedelta(hours=64 + 2 * index))
            self.assertEqual(offer.expires_at, self.now + timedelta(hours=60))
            self.assertEqual(offer.price, originals[index]['price'])
            self.assertEqual(offer.stock, originals[index]['stock'])
            self.assertEqual(offer.ends_at - offer.starts_at,
                             originals[index]['ends_at'] - originals[index]['starts_at'])
        sources = Offer.objects.filter(pk__in=self.source_ids).order_by('pk')
        self.assertEqual(list(sources.values('starts_at', 'ends_at', 'price', 'stock')), originals)
        self.assertEqual(set(sources.values_list('status', flat=True)), {'closed'})

    def test_retries_and_alternate_day_checks_only_publish_every_48_hour_cycle(self):
        now = current_cycle(self.now) + timedelta(hours=2)
        first = self.run_at(now)
        for offset in (0, 1, 24, 45):
            repeated = self.run_at(now + timedelta(hours=offset))
            self.assertFalse(repeated['renewed'])
            self.assertEqual(repeated['offer_ids'], first['offer_ids'])
        self.assertEqual(Offer.objects.count(), 6)
        second = self.run_at(now + INTERVAL)
        self.assertTrue(second['renewed'])
        self.assertEqual(Offer.objects.count(), 9)
        self.assertEqual(set(Offer.objects.filter(pk__in=first['offer_ids']).values_list('status', flat=True)), {'closed'})
        self.assertEqual(DemoRefreshState.objects.get().active_offer_ids, second['offer_ids'])

    def test_calendar_cycle_stays_48_hours_across_month_and_year(self):
        for value in (datetime(2026, 1, 31, 10, tzinfo=datetime_timezone.utc),
                      datetime(2026, 12, 31, 10, tzinfo=datetime_timezone.utc)):
            self.assertEqual(current_cycle(value + INTERVAL) - current_cycle(value), INTERVAL)

    def test_bookings_keep_history_and_old_cancellation_cannot_refill_new_edition(self):
        source = Offer.objects.get(pk=self.source_ids[0])
        tourist = User.objects.get(username='turista_demo')
        owner = source.provider.owner
        from uuid import uuid4
        confirmed = request_booking(tourist, source.pk, 1, 'demo@example.invalid', uuid4(), offer_quote(source))
        transition(owner, confirmed.pk, 'confirm')
        pending = request_booking(tourist, source.pk, 1, 'demo@example.invalid', uuid4(), offer_quote(source))
        snapshot = confirmed.service.copy()
        result = self.run_at(self.now)
        confirmed.refresh_from_db()
        pending.refresh_from_db()
        self.assertEqual(confirmed.service, snapshot)
        self.assertEqual(confirmed.status, Booking.Status.CONFIRMED)
        self.assertEqual(pending.status, Booking.Status.EXPIRED)
        stocks = list(Offer.objects.filter(pk__in=result['offer_ids']).values_list('stock', flat=True))
        transition(owner, confirmed.pk, 'cancel_confirmed', 'Fin de prueba')
        self.assertEqual(list(Offer.objects.filter(pk__in=result['offer_ids']).values_list('stock', flat=True)), stocks)
        self.assertEqual(confirmed.history.count(), 3)

    def test_refuses_real_or_moderated_offers_and_disabled_provider(self):
        source = Offer.objects.get(pk=self.source_ids[0])
        for field, value in (('description', 'Oferta comercial'), ('moderated', True)):
            with self.subTest(field=field):
                before = getattr(source, field)
                setattr(source, field, value)
                source.save(update_fields=[field])
                with self.assertRaises(ValidationError): self.run_at(self.now)
                self.assertEqual(Offer.objects.count(), 3)
                setattr(source, field, before)
                source.save(update_fields=[field])
        source.provider.enabled = False
        source.provider.save(update_fields=['enabled'])
        with self.assertRaises(ValidationError): self.run_at(self.now)

    def test_rotated_moderated_offer_is_not_republished(self):
        first = self.run_at(self.now)
        Offer.objects.filter(pk=first['offer_ids'][0]).update(moderated=True)
        with self.assertRaises(ValidationError): self.run_at(self.now + INTERVAL)
        self.assertEqual(Offer.objects.count(), 6)

    def test_failed_validation_rolls_back_closures_and_partial_edition(self):
        Offer.objects.filter(pk=self.source_ids[2]).update(unit='unidad incorrecta')
        with self.assertRaises(ValidationError): self.run_at(self.now)
        self.assertEqual(Offer.objects.count(), 3)
        self.assertEqual(set(Offer.objects.values_list('status', flat=True)), {'published'})
        self.assertIsNone(DemoRefreshState.objects.get().cycle_started_at)

    def test_disabled_or_invalid_allowlist_never_touches_database(self):
        with override_settings(DEMO_RENEWAL_ENABLED=False):
            with self.assertRaises(ValidationError): renew_demo_offers()
        for ids in ((), self.source_ids[:2], (self.source_ids[0],) * 3):
            with override_settings(DEMO_SOURCE_OFFER_IDS=ids):
                with self.assertRaises(ValidationError): renew_demo_offers()
        self.assertFalse(DemoRefreshState.objects.exists())

    def test_endpoint_authorization_method_environment_and_safe_errors(self):
        url = '/internal/cron/renew-demo/'
        auth = {'HTTP_AUTHORIZATION': 'Bearer test-cron'}
        self.assertEqual(self.client.get(url).status_code, 401)
        self.assertEqual(self.client.get(url, HTTP_AUTHORIZATION='Bearer wrong').status_code, 401)
        self.assertEqual(self.client.post(url, **auth).status_code, 405)
        with override_settings(VERCEL_ENVIRONMENT='preview'):
            self.assertEqual(self.client.get(url, **auth).status_code, 503)
        with override_settings(CRON_SECRET=''):
            self.assertEqual(self.client.get(url, **auth).status_code, 401)
        self.assertFalse(DemoRefreshState.objects.exists())
        response = self.client.get(url, **auth)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['renewed'])
        self.assertIn('no-store', response['Cache-Control'])
        self.assertFalse(self.client.get(url, **auth).json()['renewed'])
        with patch('market.demo_renewal.renew_demo_offers', side_effect=RuntimeError('secret-database-url')):
            with self.assertLogs('market.views', level='ERROR') as logs:
                response = self.client.get(url, **auth)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b'secret-database-url', response.content)
        self.assertNotIn('secret-database-url', str(logs.output))
