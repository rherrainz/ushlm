import uuid
from datetime import date
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import DecimalField, ExpressionWrapper, F
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from .forms import BookingForm, InventoryForm, OfferForm, SignupForm
from .models import Booking, Category, Offer, Provider, Notification
from .services import (OfferChanged, adjust_inventory, expire_pending, offer_quote,
                       request_booking, transition, validate_quote)

def catalog(request):
    offers = Offer.objects.available().select_related('provider', 'category')
    category = request.GET.get('category', '')
    if category: offers = offers.filter(category__kind=category)
    selected_date = request.GET.get('date', '')
    error = ''
    if selected_date:
        try: offers = offers.filter(starts_at__date=date.fromisoformat(selected_date))
        except ValueError: error = 'Ingresá una fecha válida.'
    order = request.GET.get('order', 'discount')
    if order not in ('discount', 'expires', 'price'):
        order = 'discount'
    currency = request.GET.get('currency', '')
    if currency in ('ARS', 'USD'): offers = offers.filter(currency=currency)
    elif order == 'price':
        error = 'Elegí una moneda para ordenar por precio.'
        order = 'discount'
    if order == 'price':
        offers = offers.order_by('price', 'expires_at', 'pk')
    elif order == 'discount':
        offers = offers.annotate(ratio=ExpressionWrapper(F('price') * 1.0 / F('reference_price'), output_field=DecimalField())).order_by('ratio', 'expires_at', 'pk')
    else: offers = offers.order_by('expires_at', 'pk')
    page = Paginator(offers, 24).get_page(request.GET.get('page'))
    filters = request.GET.copy()
    filters.pop('page', None)
    return render(request, 'market/catalog.html', {'offers': page, 'page_obj': page, 'filter_query':filters.urlencode(), 'categories': Category.objects.all(), 'error':error, 'order':order, 'currency':currency})

def detail_context(offer, form):
    try:
        quantity = form.fields['quantity'].clean(form['quantity'].value())
    except ValidationError:
        quantity = None
    return {'offer': offer, 'form': form, 'preview_quantity': quantity,
            'preview_total': offer.price * quantity if quantity else None,
            'unit_cents': int(offer.price * 100)}


def detail(request, pk):
    offer = get_object_or_404(Offer.objects.available().select_related('provider', 'category'), pk=pk)
    form = BookingForm(initial={'token':uuid.uuid4(), 'quantity':1, 'quote':offer_quote(offer)})
    return render(request, 'market/detail.html', detail_context(offer, form))

def signup(request):
    form = SignupForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect('catalog')
    return render(request, 'market/form.html', {'form':form, 'title':'Creá tu cuenta de turista'})

@login_required
@require_POST
def book(request, pk):
    offer = get_object_or_404(Offer, pk=pk)
    form = BookingForm(request.POST)
    status = 400
    if form.is_valid():
        try:
            if request.POST.get('intent') == 'preview':
                validate_quote(offer, form.cleaned_data['quote'])
                return render(request, 'market/detail.html', detail_context(offer, form))
            request_booking(request.user, pk, **form.cleaned_data)
            messages.success(request, 'Solicitud enviada. Está pendiente: todavía no garantiza disponibilidad. El pago se coordina con el prestador.')
            return redirect('bookings')
        except OfferChanged as exc:
            # Preserve quantity, contact and idempotency token, but require a fresh review.
            offer.refresh_from_db()
            data = request.POST.copy()
            data['quote'] = offer_quote(offer)
            form = BookingForm(data)
            form.is_valid()
            form.add_error(None, exc)
            status = 409
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(request, 'market/detail.html', detail_context(offer, form), status=status)

@login_required
def bookings(request):
    expire_pending()
    items = Booking.objects.filter(tourist=request.user).select_related('offer').prefetch_related('history')
    return render(request, 'market/bookings.html', {'bookings':items.order_by('-created_at')})

def own_provider(user):
    provider = get_object_or_404(Provider, owner=user)
    return provider

@login_required
def dashboard(request):
    provider = own_provider(request.user)
    expire_pending()
    return render(request, 'market/dashboard.html', {'provider':provider, 'offers':Offer.objects.filter(provider=provider), 'bookings':Booking.objects.filter(offer__provider=provider).select_related('tourist','offer').prefetch_related('history').order_by('-created_at')})

@login_required
def edit_offer(request, pk=None):
    provider = own_provider(request.user)
    # Lock on POST, using the same provider-first order as inventory operations.
    with transaction.atomic():
        if request.method == 'POST': provider = Provider.objects.select_for_update().get(pk=provider.pk)
        instance = get_object_or_404(Offer, pk=pk, provider=provider) if pk else Offer(provider=provider)
        if request.method == 'POST' and pk:
            instance = Offer.objects.select_for_update().get(pk=pk, provider=provider)
        instance.provider = provider
        form = OfferForm(request.POST or None, instance=instance)
        if request.method == 'POST' and form.is_valid():
            offer = form.save(commit=False)
            if request.POST.get('intent') == 'preview':
                return render(request, 'market/offer_preview.html', {'offer':offer, 'form':form, 'title':'Revisá tu publicación'})
            if offer.pk:
                offer.save(update_fields=list(form.fields))
            else:
                offer.save()
            messages.success(request, 'Oferta guardada. El cupo se modifica por separado en Ajustar disponibilidad.')
            return redirect('dashboard')
    return render(request, 'market/form.html', {'form':form, 'title':'Editar oferta' if pk else 'Nueva oferta', 'offer':instance, 'inventory_separate':True})

@login_required
@require_POST
def action(request, pk, action):
    booking = get_object_or_404(Booking, pk=pk)
    try:
        transition(request.user, booking.pk, action, request.POST.get('reason',''))
        messages.success(request, 'Estado actualizado.')
    except ValidationError as exc: messages.error(request, ' '.join(exc.messages))
    return redirect('bookings' if action == 'cancel_pending' else 'dashboard')


@login_required
def inventory(request, pk):
    provider = own_provider(request.user)
    offer = get_object_or_404(Offer, pk=pk, provider=provider)
    return inventory_form_view(request, offer)


def inventory_form_view(request, offer, *, as_admin=False):
    form = InventoryForm(request.POST if request.method == 'POST' else None,
                         initial={'new_stock':offer.stock, 'expected_version':offer.stock_version})
    status = 200
    if request.method == 'POST':
        if form.is_valid():
            try:
                adjust_inventory(request.user, offer.pk, as_admin=as_admin, **form.cleaned_data)
                messages.success(request, 'Disponibilidad actualizada.')
                return redirect('admin:market_offer_change', offer.pk) if as_admin else redirect('dashboard')
            except ValidationError as exc:
                form.add_error(None, exc)
                status = 409
        else:
            status = 400
        offer.refresh_from_db()
        # Keep the submitted version on failure. Reopening is an explicit review step;
        # a second blind submit must not turn a stale adjustment into a valid one.
    template = 'admin/market/inventory.html' if as_admin else 'market/inventory.html'
    return render(request, template, {'form':form, 'offer':offer, 'title':'Ajustar disponibilidad'}, status=status)


def about(request):
    return render(request, "market/about.html")


@login_required
def notifications(request):
    items = Notification.objects.filter(recipient=request.user).select_related('offer', 'booking')
    return render(request, 'market/notifications.html', {'notifications': items})

@login_required
@require_POST
def read_notification(request, pk):
    item = get_object_or_404(Notification, pk=pk, recipient=request.user)
    Notification.objects.filter(pk=item.pk, read_at__isnull=True).update(read_at=timezone.now())
    return redirect('notifications')
