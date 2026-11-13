"""All inventory and booking transitions lock provider → offer → booking."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from .models import Booking, BookingHistory, Offer, Provider

def record(booking, state, actor=None, reason=''):
    previous = booking.status
    booking.status = state
    booking.save(update_fields=['status', 'updated_at', 'stock_returned'])
    BookingHistory.objects.create(booking=booking, actor=actor, previous=previous, current=state, reason=reason)

def live(offer):
    now = timezone.now()
    return offer.status == 'published' and offer.provider.enabled and offer.provider.owner.is_active and offer.expires_at > now and offer.starts_at > now

def locked_offer(pk):
    provider_id = Offer.objects.values_list('provider_id', flat=True).get(pk=pk)
    provider = Provider.objects.select_for_update().get(pk=provider_id)
    offer = Offer.objects.select_for_update().get(pk=pk)
    offer.provider = provider
    return offer

@transaction.atomic
def request_booking(user, offer_id, quantity, contact, token):
    if not user.is_active or user.is_staff or Provider.objects.filter(owner=user).exists():
        raise PermissionDenied('Las solicitudes son exclusivas del perfil turista.')
    offer = locked_offer(offer_id)
    existing = Booking.objects.filter(token=token).first()
    if existing:
        if existing.tourist_id != user.pk or existing.offer_id != offer.pk:
            raise PermissionDenied
        return existing
    if type(quantity) is not int or quantity <= 0:
        raise ValidationError('La cantidad debe ser un entero positivo.')
    if not contact.strip() or len(contact) > 200:
        raise ValidationError('Indicá un contacto válido de hasta 200 caracteres.')
    if not live(offer) or offer.stock < quantity:
        raise ValidationError('La oferta ya no está disponible o no tiene cupo suficiente.')
    booking = Booking.objects.create(tourist=user, offer=offer, quantity=quantity, contact=contact, token=token, price=offer.price, currency=offer.currency, description=offer.description, conditions=offer.conditions, service={'title': offer.title, 'starts_at': offer.starts_at.isoformat(), 'ends_at': offer.ends_at.isoformat(), 'location': offer.location, 'unit': offer.unit, 'occupancy': offer.occupancy, 'provider': offer.provider.name, 'provider_contact': offer.provider.contact})
    BookingHistory.objects.create(booking=booking, actor=user, previous='', current='pending', reason='Solicitud creada; no reserva cupo.')
    return booking

@transaction.atomic
def transition(user, booking_id, action, reason=''):
    offer_id = Booking.objects.values_list('offer_id', flat=True).get(pk=booking_id)
    offer = locked_offer(offer_id)
    booking = Booking.objects.select_for_update().get(pk=booking_id)
    owner = offer.provider.owner_id == user.pk
    tourist = booking.tourist_id == user.pk
    if action in ('confirm', 'reject', 'cancel_confirmed'):
        if not owner or not user.is_active: raise PermissionDenied
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
            offer.save(update_fields=['stock'])
            booking.stock_returned = True
        record(booking, 'cancelled', user, reason)
    else:
        if booking.status != 'pending': raise ValidationError('La solicitud ya no está pendiente.')
        if action == 'confirm':
            if not live(offer) or offer.stock < booking.quantity:
                raise ValidationError('No se puede confirmar: revisá habilitación, vigencia y cupo.')
            offer.stock -= booking.quantity
            offer.save(update_fields=['stock'])
            record(booking, 'confirmed', user, 'Aceptada por el prestador.')
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
