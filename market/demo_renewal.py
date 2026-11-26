"""Publish a new edition of three demo offers without rewriting bookings."""
from datetime import datetime, timedelta, timezone as datetime_timezone

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Booking, DemoRefreshState, Offer, Provider
from .services import record

INTERVAL = timedelta(hours=48)
# A fixed epoch, rather than */2 in day-of-month, survives month/year boundaries.
ANCHOR = datetime(2026, 1, 1, 9, tzinfo=datetime_timezone.utc)
STATE_KEY = 'public-demo'


def current_cycle(now):
    return ANCHOR + ((now - ANCHOR) // INTERVAL) * INTERVAL


def _is_demo(offer):
    return (offer.provider.owner.username == 'prestador_demo'
            and offer.provider.owner.email.endswith('@example.invalid')
            and 'fictici' in offer.description.lower())


def renew_demo_offers(now=None):
    if not settings.DEMO_RENEWAL_ENABLED:
        raise ValidationError('La renovación demo está desactivada.')
    source_ids = settings.DEMO_SOURCE_OFFER_IDS
    if len(source_ids) != 3 or len(set(source_ids)) != 3:
        raise ValidationError('Configurá exactamente tres ofertas demo distintas.')
    now = now or timezone.now()
    cycle = current_cycle(now)
    # get_or_create handles simultaneous first invocations through the unique PK.
    DemoRefreshState.objects.get_or_create(key=STATE_KEY)
    with transaction.atomic():
        state = DemoRefreshState.objects.select_for_update().get(pk=STATE_KEY)
        if state.cycle_started_at is not None and cycle <= state.cycle_started_at:
            return {'renewed': False, 'offer_ids': state.active_offer_ids,
                    'next_refresh_at': (state.cycle_started_at + INTERVAL).isoformat()}

        # Match the provider -> offer -> booking lock order used by services.
        provider_ids = set(Offer.objects.filter(pk__in=source_ids).values_list('provider_id', flat=True))
        if len(provider_ids) != 1:
            raise ValidationError('Las ofertas demo deben pertenecer al mismo prestador.')
        provider = Provider.objects.select_for_update().select_related('owner').get(pk=provider_ids.pop())
        if not provider.enabled or not provider.owner.is_active:
            raise ValidationError('El prestador demo no está habilitado.')
        previous_ids = state.active_offer_ids or list(source_ids)
        all_ids = set(source_ids) | set(previous_ids)
        offers = {offer.pk: offer for offer in Offer.objects.select_for_update()
                  .filter(pk__in=all_ids).select_related('category').order_by('pk')}
        if set(offers) != all_ids:
            raise ValidationError('Falta una oferta demo configurada.')
        for offer in offers.values():
            if offer.provider_id != provider.pk:
                raise ValidationError('La edición anterior no pertenece al prestador demo.')
            offer.provider = provider
            if not _is_demo(offer) or offer.moderated:
                raise ValidationError('No se renuevan ofertas reales ni publicaciones moderadas.')
        sources = [offers[pk] for pk in source_ids]
        if {offer.category.kind for offer in sources} != {'tour', 'stay', 'car'}:
            raise ValidationError('La demo debe incluir excursión, alojamiento y auto.')
        if any(offer.stock <= 0 for offer in sources):
            raise ValidationError('Las plantillas demo necesitan cupo positivo.')

        for previous_id in previous_ids:
            previous = offers[previous_id]
            # Expire pending requests against their original edition before closing.
            for booking in Booking.objects.select_for_update().filter(
                    offer=previous, status=Booking.Status.PENDING).order_by('pk'):
                record(booking, Booking.Status.EXPIRED,
                       reason='Finalizó la edición de demostración; consultá las nuevas ofertas.')
            previous.status = Offer.Status.CLOSED
            previous.save(update_fields=['status'])

        active_ids = []
        excluded = {'id', 'starts_at', 'ends_at', 'expires_at', 'stock_version', 'status'}
        for index, source in enumerate(sources):
            data = {field.attname: getattr(source, field.attname)
                    for field in Offer._meta.concrete_fields if field.name not in excluded}
            starts_at = now + timedelta(hours=64 + index * 2)
            offer = Offer(**data, starts_at=starts_at,
                          ends_at=starts_at + (source.ends_at - source.starts_at),
                          expires_at=now + timedelta(hours=60), status=Offer.Status.PUBLISHED)
            offer.provider = provider
            offer.full_clean()
            offer.save()
            active_ids.append(offer.pk)
        state.cycle_started_at = cycle
        state.refreshed_at = now
        state.active_offer_ids = active_ids
        state.save(update_fields=['cycle_started_at', 'refreshed_at', 'active_offer_ids'])
        return {'renewed': True, 'offer_ids': active_ids,
                'next_refresh_at': (cycle + INTERVAL).isoformat()}
