from django.contrib import admin
from django.db import transaction
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils.html import format_html
from .views import inventory_form_view
from .models import Provider, Category, Offer, Booking, BookingHistory

class NoDeleteAdmin(admin.ModelAdmin):
    def has_delete_permission(self, request, obj=None): return False

@admin.register(Provider)
class ProviderAdmin(NoDeleteAdmin):
    list_display = ['name', 'owner', 'enabled']
    list_filter = ['enabled']

@admin.register(Category)
class CategoryAdmin(NoDeleteAdmin): pass

@admin.register(Offer)
class OfferAdmin(NoDeleteAdmin):
    list_display = ['title', 'provider', 'status', 'stock', 'expires_at']
    list_filter = ['status', 'category']
    def get_readonly_fields(self, request, obj=None):
        return ['stock', 'stock_version', 'inventory_link'] + (['provider'] if obj else [])
    @admin.display(description='Disponibilidad')
    def inventory_link(self, obj):
        if not obj or not obj.pk:
            return 'Guardá la oferta y luego ajustá su disponibilidad (cupo inicial: 0).'
        return format_html('<a href="{}">Ajustar disponibilidad</a>', reverse('admin:market_offer_inventory', args=[obj.pk]))

    def get_urls(self):
        return [path('<int:object_id>/inventario/', self.admin_site.admin_view(self.inventory_view),
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
                      if not field.primary_key and field.name not in ('provider', 'stock', 'stock_version')]
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
