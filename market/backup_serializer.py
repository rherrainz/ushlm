"""JSON backup serializer preserving all datetime microseconds."""
from datetime import datetime, time
from django.core.serializers.json import DjangoJSONEncoder, Serializer as JSONSerializer, Deserializer


class PreciseEncoder(DjangoJSONEncoder):
    def default(self, value):
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, time) and not value.tzinfo:
            return value.isoformat()
        return super().default(value)


class Serializer(JSONSerializer):
    def _init_options(self):
        super()._init_options()
        self.json_kwargs['cls'] = PreciseEncoder
