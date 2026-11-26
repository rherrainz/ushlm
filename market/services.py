"""All inventory and booking transitions lock provider → offer → booking."""
from decimal import Decimal
import hashlib
import json
from django.core import signing
from django.db.models import F
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from .models import Booking, BookingHistory, Offer, Provider, Notification, OfferModeration

def record(booking, state, actor=None, reason=''):
    previous = booking.status
    booking.status = state
    booking.save(update_fields=['status', 'updated_at', 'stock_returned'])
    BookingHistory.objects.create(booking=booking, actor=actor, previous=previous, current=state, reason=reason)
    recipients = {booking.tourist_id, booking.offer.provider.owner_id}
    if actor: recipients.discard(actor.pk)
    Notification.objects.bulk_create([Notification(recipient_id=pk, booking=booking, offer_id=booking.offer_id, message=f'Solicitud #{booking.pk}: {booking.get_status_display()}.') for pk in recipients])

def live(offer):
    now = timezone.now()
    return not offer.moderated and offer.status == 'published' and offer.provider.enabled and offer.provider.owner.is_active and offer.expires_at > now and offer.starts_at > now

def locked_offer(pk):
    provider_id = Offer.objects.values_list('provider_id', flat=True).get(pk=pk)
    provider = Provider.objects.select_for_update().get(pk=provider_id)
    offer = Offer.objects.select_for_update().get(pk=pk)
    offer.provider = provider
    return offer

class OfferChanged(ValidationError):
    """The visitor must review the current offer before sending again."""


def quote_payload(offer):
    fields = ['title', 'description', 'conditions', 'location', 'starts_at', 'ends_at',
              'expires_at', 'unit', 'occupancy', 'price', 'reference_price', 'currency', 'category_id']
    data = {field: str(getattr(offer, field)) for field in fields}
    for field in ('price', 'reference_price'):
        data[field] = format(Decimal(str(getattr(offer, field))), '.2f')
    data.update(provider=offer.provider.name, provider_contact=offer.provider.contact)
    digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    return {'offer_id': offer.pk, 'digest': digest}


def offer_quote(offer):
    return signing.dumps(quote_payload(offer), salt='market.offer-quote')


def validate_quote(offer, quote):
    try:
        accepted = signing.loads(quote, salt='market.offer-quote')
    except (signing.BadSignature, TypeError):
        raise OfferChanged('La información enviada no es válida. Revisá la oferta actualizada antes de solicitar.')
    if accepted != quote_payload(offer):
        raise OfferChanged('La oferta cambió. Revisá el precio, el total y las condiciones actualizadas antes de volver a solicitar.')


@transaction.atomic
def adjust_inventory(user, offer_id, new_stock, expected_version, *, as_admin=False):
    offer = locked_offer(offer_id)
    allowed = (user.is_staff and user.has_perm('market.change_offer')) if as_admin else offer.provider.owner_id == user.pk
    if not user.is_active or not allowed:
        raise PermissionDenied('No tenés permiso para ajustar este inventario.')
    if type(new_stock) is not int or not 0 <= new_stock <= 2147483647:
        raise ValidationError('El cupo debe ser un entero entre 0 y 2147483647.')
    if type(expected_version) is not int or expected_version < 0:
        raise ValidationError('La versión del inventario no es válida.')
    # Compare and swap in addition to row locks: a stale form cannot restore sold units.
    changed = Offer.objects.filter(pk=offer.pk, stock_version=expected_version).update(
        stock=new_stock, stock_version=F('stock_version') + 1)
    if not changed:
        raise ValidationError('El inventario cambió desde que abriste el formulario. Revisá el cupo actual y volvé a ajustar.')
    offer.refresh_from_db()
    return offer


@transaction.atomic
def request_booking(user, offer_id, quantity, contact, token, quote):
    if not user.is_active or user.is_staff or Provider.objects.filter(owner=user).exists():
        raise PermissionDenied('Las solicitudes son exclusivas del perfil turista.')
    offer = locked_offer(offer_id)
    existing = Booking.objects.filter(token=token).first()
    if existing:
        if existing.tourist_id != user.pk or existing.offer_id != offer.pk:
            raise PermissionDenied
        return existing
    validate_quote(offer, quote)
    if type(quantity) is not int or quantity <= 0:
        raise ValidationError('La cantidad debe ser un entero positivo.')
    if not contact.strip() or len(contact) > 200:
        raise ValidationError('Indicá un contacto válido de hasta 200 caracteres.')
    if not live(offer) or offer.stock < quantity:
        raise ValidationError('La oferta ya no está disponible o no tiene cupo suficiente.')
    booking = Booking.objects.create(tourist=user, offer=offer, quantity=quantity, contact=contact, token=token, price=offer.price, currency=offer.currency, description=offer.description, conditions=offer.conditions, service={'title': offer.title, 'starts_at': offer.starts_at.isoformat(), 'ends_at': offer.ends_at.isoformat(), 'location': offer.location, 'unit': offer.unit, 'occupancy': offer.occupancy, 'provider': offer.provider.name, 'provider_contact': offer.provider.contact})
    BookingHistory.objects.create(booking=booking, actor=user, previous='', current='pending', reason='Solicitud creada; no reserva cupo.')
    Notification.objects.create(recipient=offer.provider.owner, booking=booking, offer=offer, message=f'Nueva solicitud #{booking.pk} para {offer.title}.'[:300])
    return booking

def can_manage_all_bookings(user):
    return user.is_active and user.is_staff and user.has_perm('market.change_booking')


@transaction.atomic
def transition(user, booking_id, action, reason=''):
    offer_id = Booking.objects.values_list('offer_id', flat=True).get(pk=booking_id)
    offer = locked_offer(offer_id)
    booking = Booking.objects.select_for_update().get(pk=booking_id)
    owner = offer.provider.owner_id == user.pk
    tourist = booking.tourist_id == user.pk
    if action in ('confirm', 'reject', 'cancel_confirmed'):
        if not user.is_active or not (owner or can_manage_all_bookings(user)):
            raise PermissionDenied
    elif action == 'cancel_pending':
        if not tourist: raise PermissionDenied
    else: raise ValidationError('Acción desconocida.')
    if booking.status == 'pending' and offer.expires_at <= timezone.now():
        record(booking, 'expired', reason='Venció la oferta.')
        return booking
    if action == 'cancel_confirmed':
        if booking.status != 'confirmed': raise ValidationError('Solo se puede cancelar una confirmación una vez.')
        if not reason.strip(): raise ValidationError('Indicá el motivo de cancelación.')
        if live(offer) and not booking.stock_returned:
            offer.stock += booking.quantity
            offer.stock_version += 1
            offer.save(update_fields=['stock', 'stock_version'])
            booking.stock_returned = True
        record(booking, 'cancelled', user, reason)
    else:
        if booking.status != 'pending': raise ValidationError('La solicitud ya no está pendiente.')
        if action == 'confirm':
            if not live(offer) or offer.stock < booking.quantity:
                raise ValidationError('No se puede confirmar: revisá habilitación, vigencia y cupo.')
            offer.stock -= booking.quantity
            offer.stock_version += 1
            offer.save(update_fields=['stock', 'stock_version'])
            record(booking, 'confirmed', user, 'Aceptada por el prestador.' if owner else 'Aceptada por administración.')
        elif action == 'reject': record(booking, 'rejected', user, reason)
        else: record(booking, 'cancelled', user, 'Cancelada por el turista.')
    return booking

def expire_pending():
    count = 0
    for pk in Booking.objects.filter(status='pending', offer__expires_at__lte=timezone.now()).values_list('pk', flat=True):
        with transaction.atomic():
            offer_id = Booking.objects.values_list('offer_id', flat=True).get(pk=pk)
            offer = locked_offer(offer_id)
            booking = Booking.objects.select_for_update().get(pk=pk)
            if booking.status == 'pending' and offer.expires_at <= timezone.now():
                record(booking, 'expired', reason='Venció la oferta.')
                count += 1
    return count

@transaction.atomic
def moderate_offer(user, offer_id, reason):
    if not user.is_active or not user.is_staff or not user.has_perm('market.change_offer'):
        raise PermissionDenied
    if not reason.strip():
        raise ValidationError('Indicá el motivo del retiro.')
    offer = locked_offer(offer_id)
    if offer.status == Offer.Status.CLOSED:
        raise ValidationError('La oferta ya está cerrada.')
    OfferModeration.objects.create(offer=offer, actor=user, reason=reason.strip(), previous=offer.status)
    offer.status = Offer.Status.CLOSED
    offer.moderated = True
    offer.save(update_fields=['status', 'moderated'])
    Notification.objects.create(recipient=offer.provider.owner, offer=offer,
                                message=f'La administración retiró la oferta #{offer.pk}. Motivo: {reason.strip()}'[:300])
    return offer
