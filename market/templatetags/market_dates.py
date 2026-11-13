from django import template
from django.utils import timezone
from django.utils.dateparse import parse_datetime
register = template.Library()
@register.filter
def local_service_date(value):
    parsed = parse_datetime(value) if value else None
    return timezone.localtime(parsed).strftime('%d/%m/%Y %H:%M') if parsed else value
