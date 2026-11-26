from django.template import Context, Template
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .templatetags.market_quantities import quantity_unit
from .tests import Fixtures


class QuantityLabelsTests(SimpleTestCase):
    def test_singular_plural_and_zero(self):
        for unit, plural in [('persona', 'personas'), ('habitación', 'habitaciones'), ('auto', 'autos')]:
            for count in (0, 1, 2):
                with self.subTest(unit=unit, count=count):
                    self.assertEqual(quantity_unit(count, unit), f'{count} {unit if count == 1 else plural}')

    def test_custom_units_are_not_pluralized_by_guessing_and_remain_escaped(self):
        self.assertEqual(quantity_unit(1, 'habitación familiar'), '1 habitación familiar')
        self.assertEqual(quantity_unit(2, 'habitación familiar'), '2 unidades de habitación familiar')
        rendered = Template('{% load market_quantities %}{{ count|quantity_unit:unit }}').render(
            Context({'count': 2, 'unit': '<script>bad</script>'}))
        self.assertNotIn('<script>', rendered)
        self.assertIn('&lt;script&gt;', rendered)


class QuantityRenderingTests(Fixtures, TestCase):
    def test_catalog_and_detail_agree_on_units_and_availability(self):
        self.assertContains(self.client.get(reverse('catalog')), '2 personas disponibles')
        self.offer.stock = 1
        self.offer.save(update_fields=['stock'])
        self.assertContains(self.client.get(reverse('detail', args=[self.offer.pk])), '1 persona disponible')
        self.category.kind = 'car'
        self.category.save(update_fields=['kind'])
        self.offer.unit = 'auto'
        self.offer.save(update_fields=['unit'])
        catalog = self.client.get(reverse('catalog'))
        self.assertContains(catalog, '1 auto disponible')
        self.assertNotContains(catalog, '1 auto disponibles')
        self.category.kind = 'stay'
        self.category.save(update_fields=['kind'])
        self.offer.unit = 'habitación'
        self.offer.stock = 2
        self.offer.occupancy = 1
        self.offer.save(update_fields=['unit', 'stock', 'occupancy'])
        self.assertContains(self.client.get(reverse('catalog')), '2 habitaciones disponibles')
        self.assertContains(self.client.get(reverse('catalog')), 'Hasta 1 persona por unidad')

    def test_booking_snapshot_and_inventory_use_counted_units(self):
        booking = self.request(quantity=2)
        self.client.force_login(self.tourist)
        self.assertContains(self.client.get(reverse('bookings')), '2 personas')
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(reverse('inventory', args=[self.offer.pk])), '2 personas')
        self.assertEqual(booking.service['unit'], 'persona')

    def test_request_explains_when_stock_is_deducted(self):
        self.client.force_login(self.tourist)
        response = self.client.get(reverse('detail', args=[self.offer.pk]))
        self.assertContains(response, 'Enviar la solicitud no reserva cupo.')
        self.assertContains(response, 'La disponibilidad se descuenta cuando el prestador la acepta.')
