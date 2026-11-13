import uuid
from datetime import date, timedelta
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import DecimalField, ExpressionWrapper, F
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from .forms import BookingForm, OfferForm, SignupForm
from .models import Booking, Category, Offer, Provider
from .services import expire_pending, request_booking, transition

def catalog(request):
    offers = Offer.objects.available().select_related('provider', 'category')
    category = request.GET.get('category', '')
    if category: offers = offers.filter(category__kind=category)
    selected_date = request.GET.get('date', '')
    error = ''
    if selected_date:
        try: offers = offers.filter(starts_at__date=date.fromisoformat(selected_date))
        except ValueError: error = 'Ingresá una fecha válida.'
    order = request.GET.get('order', 'expires')
    if order == 'discount':
        offers = offers.annotate(ratio=ExpressionWrapper(F('price') * 1.0 / F('reference_price'), output_field=DecimalField())).order_by('ratio', 'expires_at')
    else: offers = offers.order_by('expires_at')
    return render(request, 'market/catalog.html', {'offers': offers, 'categories': Category.objects.all(), 'error':error})

def detail(request, pk):
    offer = get_object_or_404(Offer.objects.available().select_related('provider', 'category'), pk=pk)
    return render(request, 'market/detail.html', {'offer': offer, 'form': BookingForm(initial={'token':uuid.uuid4(), 'quantity':1})})

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
    if form.is_valid():
        try:
            request_booking(request.user, pk, **form.cleaned_data)
            messages.success(request, 'Solicitud enviada. Está pendiente: todavía no garantiza disponibilidad. El pago se coordina con el prestador.')
            return redirect('bookings')
        except ValidationError as exc: form.add_error(None, exc)
    return render(request, 'market/detail.html', {'offer':offer, 'form':form}, status=400)

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
            form.save()
            messages.success(request, 'Oferta guardada.')
            return redirect('dashboard')
    return render(request, 'market/form.html', {'form':form, 'title':'Editar oferta' if pk else 'Nueva oferta'})

@login_required
@require_POST
def action(request, pk, action):
    booking = get_object_or_404(Booking, pk=pk)
    try:
        transition(request.user, booking.pk, action, request.POST.get('reason',''))
        messages.success(request, 'Estado actualizado.')
    except ValidationError as exc: messages.error(request, ' '.join(exc.messages))
    return redirect('bookings' if action == 'cancel_pending' else 'dashboard')
