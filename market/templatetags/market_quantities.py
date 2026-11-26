"""Quantity labels shared by offers and immutable booking snapshots."""
from django import template

register = template.Library()

# Do not guess the plural of arbitrary provider-supplied accommodation units.
UNIT_PLURALS = {
    'persona': 'personas',
    'habitación': 'habitaciones',
    'auto': 'autos',
    'unidad': 'unidades',
}


@register.filter
def quantity_unit(quantity, unit):
    unit = str(unit or 'unidad').strip()
    if quantity == 1:
        return f'{quantity} {unit}'
    plural = UNIT_PLURALS.get(unit.lower())
    if plural is None:
        return f'{quantity} unidades de {unit}'
    return f'{quantity} {plural}'
