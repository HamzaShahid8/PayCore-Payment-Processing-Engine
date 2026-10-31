from rest_framework import serializers

from payments.services import PLAN_AMOUNTS_CENTS


class CreateCheckoutSessionSerializer(serializers.Serializer):
    plan = serializers.ChoiceField(choices=tuple(PLAN_AMOUNTS_CENTS))

    def to_internal_value(self, data):
        if hasattr(data, "keys"):
            unknown_fields = set(data.keys()) - set(self.fields)
            if unknown_fields:
                raise serializers.ValidationError(
                    {field: ["Unknown field."] for field in sorted(unknown_fields)}
                )
        return super().to_internal_value(data)
