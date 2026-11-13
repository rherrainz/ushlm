from django.contrib import admin
from django.db import transaction
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
        return ['provider'] if obj else []
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
