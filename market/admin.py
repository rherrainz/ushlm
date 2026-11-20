from django.contrib import admin
from django.db import transaction
from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from .services import moderate_offer
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils.html import format_html
from .views import inventory_form_view
from .models import Provider, Category, Offer, Booking, BookingHistory, Notification, OfferModeration

class NoDeleteAdmin(admin.ModelAdmin):
    def has_delete_permission(self, request, obj=None): return False

@admin.register(Provider)
class ProviderAdmin(NoDeleteAdmin):
    list_display = ['name', 'owner', 'enabled']
    list_filter = ['enabled']

@admin.register(Category)
class CategoryAdmin(NoDeleteAdmin): pass

class AdminOfferForm(forms.ModelForm):
    class Meta:
        model = Offer
        fields = '__all__'

    def clean(self):
        data = super().clean()
        if self.instance.pk and data.get('status') == Offer.Status.CLOSED:
            previous = Offer.objects.get(pk=self.instance.pk).status
            if previous != Offer.Status.CLOSED:
                raise ValidationError('Para retirar una oferta usá Retirar publicación con motivo; el retiro debe conservar su justificación.')
        return data


@admin.register(Offer)
class OfferAdmin(NoDeleteAdmin):
    form = AdminOfferForm
    list_display = ['title', 'provider', 'status', 'stock', 'expires_at']
    list_filter = ['status', 'category']
    def get_readonly_fields(self, request, obj=None):
        return ['stock', 'stock_version', 'inventory_link', 'moderation_link', 'moderated'] + (['provider'] if obj else [])
    @admin.display(description='Disponibilidad')
    def inventory_link(self, obj):
        if not obj or not obj.pk:
            return 'Guardá la oferta y luego ajustá su disponibilidad (cupo inicial: 0).'
        return format_html('<a href="{}">Ajustar disponibilidad</a>', reverse('admin:market_offer_inventory', args=[obj.pk]))

    @admin.display(description='Moderación')
    def moderation_link(self, obj):
        if not obj or not obj.pk: return 'Guardá primero la oferta.'
        return format_html('<a href="{}">Retirar publicación con motivo</a>', reverse('admin:market_offer_moderate', args=[obj.pk]))

    def moderation_view(self, request, object_id):
        offer = get_object_or_404(Offer, pk=object_id)
        if not self.has_change_permission(request, offer): raise PermissionDenied
        class ReasonForm(forms.Form):
            reason = forms.CharField(label='Motivo del retiro', widget=forms.Textarea, max_length=2000)
        form = ReasonForm(request.POST if request.method == 'POST' else None)
        if request.method == 'POST' and form.is_valid():
            try:
                moderate_offer(request.user, offer.pk, form.cleaned_data['reason'])
                messages.success(request, 'Publicación retirada; motivo e historial conservados.')
                return redirect('admin:market_offer_change', offer.pk)
            except ValidationError as exc: form.add_error(None, exc)
        return render(request, 'admin/market/moderate.html', {**self.admin_site.each_context(request), 'form':form, 'offer':offer, 'title':'Retirar publicación'})

    def get_urls(self):
        return [path('<int:object_id>/moderar/', self.admin_site.admin_view(self.moderation_view), name='market_offer_moderate'), path('<int:object_id>/inventario/', self.admin_site.admin_view(self.inventory_view),
                     name='market_offer_inventory')] + super().get_urls()

    def inventory_view(self, request, object_id):
        offer = get_object_or_404(Offer, pk=object_id)
        if not self.has_change_permission(request, offer):
            raise PermissionDenied
        return inventory_form_view(request, offer, as_admin=True)

    def save_model(self, request, obj, form, change):
        if change:
            # Even a crafted POST or stale instance cannot write inventory here.
            fields = [field.name for field in obj._meta.concrete_fields
                      if not field.primary_key and field.name not in ('provider', 'stock', 'stock_version', 'moderated')]
            obj.save(update_fields=fields)
        else:
            obj.stock = 0
            obj.stock_version = 0
            super().save_model(request, obj, form, change)

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        # The admin shares the inventory lock order with the provider panel.
        with transaction.atomic():
            if request.method == 'POST' and object_id:
                provider_id = Offer.objects.filter(pk=object_id).values_list('provider_id', flat=True).first()
                if provider_id:
                    Provider.objects.select_for_update().get(pk=provider_id)
                    Offer.objects.select_for_update().get(pk=object_id)
            return super().changeform_view(request, object_id, form_url, extra_context)


class ReadOnlyAdmin(NoDeleteAdmin):
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False

admin.site.register(Booking, ReadOnlyAdmin)
admin.site.register(BookingHistory, ReadOnlyAdmin)
admin.site.site_header = 'USH Last Minute · Administración'

admin.site.register(OfferModeration, ReadOnlyAdmin)
admin.site.register(Notification, ReadOnlyAdmin)
