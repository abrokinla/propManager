from rest_framework import serializers

from workspaces.models import AgentKYC, Organization, OrganizationMembership, Subscription


class AgentKYCSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentKYC
        fields = [
            'id',
            'status',
            'license_number',
            'documents',
            'rejection_reason',
            'reviewed_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'status',
            'rejection_reason',
            'reviewed_at',
            'created_at',
            'updated_at',
        ]


class AgentProfileSerializer(serializers.ModelSerializer):
    """Public-facing agent profile backing /agents/<slug>."""

    organization_name = serializers.CharField(source='organization.name', read_only=True)
    property_count = serializers.SerializerMethodField()
    city = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = [
            'name',
            'organization_name',
            'slug',
            'city',
            'bio',
            'whatsapp',
            'logo_url',
            'brand_color',
            'property_count',
            'created_at',
        ]
        read_only_fields = ['slug', 'organization_name', 'property_count', 'city', 'created_at']

    def get_property_count(self, org):
        return org.properties.filter(is_published=True).count()

    def get_city(self, org):
        first = org.properties.first()
        return first.address.split(',')[0].strip() if first else ''