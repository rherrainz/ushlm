from datetime import timedelta
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q, F
from django.utils import timezone

class Provider(models.Model):
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='provider')
    name = models.CharField('nombre comercial', max_length=120)
    contact = models.CharField('contacto comercial', max_length=200)
    enabled = models.BooleanField('habilitado', default=False)
    def __str__(self): return self.name

class Category(models.Model):
    class Kind(models.TextChoices):
        TOUR = 'tour', 'Excursiones'
        STAY = 'stay', 'Alojamientos'
        CAR = 'car', 'Autos'
    kind = models.CharField(max_length=10, choices=Kind.choices, unique=True)
    def __str__(self): return self.get_kind_display()

class OfferQuerySet(models.QuerySet):
    def available(self):
        now = timezone.now()
        return self.filter(status='published', moderated=False, provider__enabled=True, provider__owner__is_active=True, expires_at__gt=now, starts_at__gt=now, stock__gt=0)

class Offer(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Borrador'
        PUBLISHED = 'published', 'Publicada'
        CLOSED = 'closed', 'Cerrada'
    provider = models.ForeignKey(Provider, on_delete=models.PROTECT)
    category = models.ForeignKey(Category, on_delete=models.PROTECT)
    title = models.CharField('título', max_length=160)
    description = models.TextField('descripción')
    location = models.CharField('ubicación', max_length=180)
    starts_at = models.DateTimeField('inicio del servicio')
    ends_at = models.DateTimeField('fin del servicio')
    expires_at = models.DateTimeField('vencimiento de publicación')
    unit = models.CharField('unidad de venta', max_length=60)
    occupancy = models.PositiveIntegerField('ocupación por unidad', null=True, blank=True, validators=[MinValueValidator(1)])
    reference_price = models.DecimalField('precio anterior', max_digits=12, decimal_places=2)
    price = models.DecimalField('precio promocional', max_digits=12, decimal_places=2)
    currency = models.CharField('moneda', max_length=3, choices=[('ARS','ARS'),('USD','USD')], default='ARS')
    stock = models.PositiveIntegerField('cupo disponible', default=0)
    stock_version = models.PositiveBigIntegerField('versión del inventario', default=0, editable=False)
    conditions = models.TextField('condiciones')
    moderated = models.BooleanField('retirada por administración', default=False, editable=False)
    status = models.CharField('estado', max_length=12, choices=Status.choices, default=Status.DRAFT)
    objects = OfferQuerySet.as_manager()
    class Meta:
        indexes = [models.Index(fields=['status', 'expires_at'], name='offer_live_idx'), models.Index(fields=['starts_at'], name='offer_start_idx')]
        constraints = [models.CheckConstraint(condition=Q(price__gt=0) & Q(reference_price__gt=F('price')), name='valid_offer_prices'), models.CheckConstraint(condition=Q(stock__gte=0), name='nonnegative_stock'), models.CheckConstraint(condition=Q(ends_at__gt=F('starts_at')) & Q(expires_at__lte=F('starts_at')), name='valid_offer_dates')]
    def clean(self):
        errors = {}
        now = timezone.now()
        if self.price is not None and self.reference_price is not None and not 0 < self.price < self.reference_price:
            errors['price'] = 'El precio debe ser positivo y menor al anterior, para las mismas condiciones y moneda.'
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            errors['ends_at'] = 'El fin debe ser posterior al inicio.'
        if self.expires_at and self.starts_at and self.expires_at > self.starts_at:
            errors['expires_at'] = 'El vencimiento no puede superar el inicio.'
        # Validate every published save, including republication and edits.
        if self.status == self.Status.PUBLISHED:
            if self.moderated:
                errors['status'] = 'Esta oferta fue retirada por administración. Creá una nueva publicación con las correcciones.'
            if not self.provider_id or not self.provider.enabled or not self.provider.owner.is_active:
                errors['status'] = 'Solo prestadores habilitados y activos pueden publicar.'
            if self.starts_at and not now < self.starts_at <= now + timedelta(hours=72):
                errors['starts_at'] = 'El servicio debe comenzar dentro de las próximas 72 horas.'
            if self.expires_at and self.expires_at <= now:
                errors['expires_at'] = 'El vencimiento debe ser futuro al publicar.'
        if self.category_id and self.category.kind == Category.Kind.TOUR and self.unit != 'persona':
            errors['unit'] = 'Las excursiones se venden por persona (unidad: persona).'
        if self.category_id and self.category.kind == Category.Kind.CAR and self.unit != 'auto':
            errors['unit'] = 'El período de alquiler se vende por auto (unidad: auto).'
        if self.category_id and self.category.kind == Category.Kind.STAY and not self.occupancy:
            errors['occupancy'] = 'Indicá la ocupación de la estadía fija.'
        if errors: raise ValidationError(errors)
    @property
    def discount(self):
        return int((1 - self.price / self.reference_price) * 100) if self.reference_price else 0
    def __str__(self): return self.title

class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pendiente'
        CONFIRMED = 'confirmed', 'Confirmada'
        REJECTED = 'rejected', 'Rechazada'
        EXPIRED = 'expired', 'Vencida'
        CANCELLED = 'cancelled', 'Cancelada'
    tourist = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    offer = models.ForeignKey(Offer, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    contact = models.CharField(max_length=200)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    token = models.UUIDField(unique=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    description = models.TextField()
    conditions = models.TextField()
    service = models.JSONField(default=dict)
    stock_returned = models.BooleanField(default=False)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(quantity__gt=0), name='positive_quantity')]
    @property
    def total(self): return self.price * self.quantity

class BookingHistory(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.PROTECT, related_name='history')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)
    previous = models.CharField(max_length=12, blank=True)
    current = models.CharField(max_length=12)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['created_at', 'pk']

class OfferModeration(models.Model):
    offer = models.ForeignKey(Offer, on_delete=models.PROTECT, related_name='moderations')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.TextField('motivo')
    previous = models.CharField(max_length=12)
    current = models.CharField(max_length=12, default=Offer.Status.CLOSED)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-created_at', '-pk']

class Notification(models.Model):
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='notifications')
    booking = models.ForeignKey(Booking, null=True, blank=True, on_delete=models.PROTECT)
    offer = models.ForeignKey(Offer, on_delete=models.PROTECT)
    message = models.CharField(max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        ordering = ['-created_at', '-pk']
        indexes = [models.Index(fields=['recipient', 'read_at'], name='notification_unread_idx')]
