from rest_framework import serializers
from django.contrib.auth.models import User
from .models import UserProfile, Property, Unit, Tenant, Payment, MaintenanceRequest, TenancyDocument, Reminder, QuitNotice


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['id', 'role', 'phone', 'company_name', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'profile']


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'first_name', 'last_name']

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data.get('email', ''),
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
        )
        return user


class PropertySerializer(serializers.ModelSerializer):
    owner = UserSerializer(read_only=True)
    owner_id = serializers.IntegerField(write_only=True, required=False)
    units_count = serializers.SerializerMethodField()

    class Meta:
        model = Property
        fields = ['id', 'name', 'address', 'property_type', 'description', 'total_units', 'image_url', 'owner', 'owner_id', 'units_count', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

    def get_units_count(self, obj):
        return obj.units.count()


class PropertyListSerializer(serializers.ModelSerializer):
    owner = UserSerializer(read_only=True)
    units_count = serializers.SerializerMethodField()

    class Meta:
        model = Property
        fields = ['id', 'name', 'address', 'property_type', 'total_units', 'image_url', 'owner', 'units_count', 'created_at']

    def get_units_count(self, obj):
        return obj.units.count()


class UnitSerializer(serializers.ModelSerializer):
    property = PropertyListSerializer(read_only=True)
    property_id = serializers.IntegerField(write_only=True)
    tenant_name = serializers.SerializerMethodField()

    class Meta:
        model = Unit
        fields = ['id', 'property', 'property_id', 'unit_number', 'bedrooms', 'toilets', 'bathrooms',
                  'size_sqft', 'price_sale', 'price_rent', 'status', 'tenant_name', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

    def get_tenant_name(self, obj):
        if hasattr(obj, 'tenant') and obj.tenant.is_active:
            return obj.tenant.name
        return None


class UnitListSerializer(serializers.ModelSerializer):
    property_name = serializers.SerializerMethodField()
    tenant_name = serializers.SerializerMethodField()

    class Meta:
        model = Unit
        fields = ['id', 'property_name', 'unit_number', 'bedrooms', 'bathrooms', 'price_rent', 'status', 'tenant_name']

    def get_property_name(self, obj):
        return obj.property.name

    def get_tenant_name(self, obj):
        if hasattr(obj, 'tenant') and obj.tenant.is_active:
            return obj.tenant.name
        return None


class TenantSerializer(serializers.ModelSerializer):
    unit = UnitListSerializer(read_only=True)
    unit_id = serializers.IntegerField(write_only=True)
    unit_number = serializers.SerializerMethodField()
    property_name = serializers.SerializerMethodField()

    class Meta:
        model = Tenant
        fields = ['id', 'unit', 'unit_id', 'name', 'phone', 'email', 'address', 'annual_rent',
                  'tenancy_status', 'unit_number', 'property_name',
                  'lease_start_date', 'lease_renewal_date', 'lease_expiry_date', 'move_in_date',
                  'is_active', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']
        extra_kwargs = {
            'phone': {'required': False, 'allow_blank': True},
            'email': {'required': False, 'allow_blank': True},
            'annual_rent': {'required': False, 'allow_null': True},
            'lease_start_date': {'required': False, 'allow_null': True},
            'lease_expiry_date': {'required': False, 'allow_null': True},
            'move_in_date': {'required': False, 'allow_null': True},
        }

    def get_unit_number(self, obj):
        return obj.unit.unit_number

    def get_property_name(self, obj):
        return obj.unit.property.name


class TenantListSerializer(serializers.ModelSerializer):
    unit_number = serializers.SerializerMethodField()
    property_name = serializers.SerializerMethodField()

    class Meta:
        model = Tenant
        fields = ['id', 'name', 'email', 'phone', 'unit_number', 'property_name', 'annual_rent',
                  'tenancy_status', 'lease_expiry_date', 'is_active']

    def get_unit_number(self, obj):
        return obj.unit.unit_number

    def get_property_name(self, obj):
        return obj.unit.property.name


class PaymentSerializer(serializers.ModelSerializer):
    tenant = TenantListSerializer(read_only=True)
    tenant_id = serializers.IntegerField(write_only=True)
    tenant_name = serializers.SerializerMethodField()
    unit_number = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = ['id', 'tenant', 'tenant_id', 'tenant_name', 'unit_number', 'amount',
                  'payment_date', 'payment_method', 'period_start', 'period_end',
                  'years_covered', 'reference', 'notes', 'created_at']
        read_only_fields = ['created_at']
        extra_kwargs = {
            'period_start': {'required': False, 'allow_null': True},
            'period_end': {'required': False, 'allow_null': True},
        }

    def get_tenant_name(self, obj):
        return obj.tenant.name

    def get_unit_number(self, obj):
        return obj.tenant.unit.unit_number


class PaymentListSerializer(serializers.ModelSerializer):
    tenant_name = serializers.SerializerMethodField()
    unit_number = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = ['id', 'tenant_name', 'unit_number', 'amount', 'payment_date',
                  'payment_method', 'period_start', 'period_end', 'years_covered', 'reference']

    def get_tenant_name(self, obj):
        return obj.tenant.name

    def get_unit_number(self, obj):
        return obj.tenant.unit.unit_number


class MaintenanceRequestSerializer(serializers.ModelSerializer):
    unit = UnitListSerializer(read_only=True)
    unit_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = MaintenanceRequest
        fields = ['id', 'unit', 'unit_id', 'title', 'description', 'priority', 'status',
                  'reported_by', 'resolved_at', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']
        extra_kwargs = {
            'reported_by': {'required': False, 'allow_blank': True},
        }


class MaintenanceRequestListSerializer(serializers.ModelSerializer):
    unit_number = serializers.SerializerMethodField()
    property_name = serializers.SerializerMethodField()

    class Meta:
        model = MaintenanceRequest
        fields = ['id', 'title', 'priority', 'status', 'unit_number', 'property_name', 'reported_by', 'created_at']

    def get_unit_number(self, obj):
        return obj.unit.unit_number

    def get_property_name(self, obj):
        return obj.unit.property.name


class TenancyDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenancyDocument
        fields = ['id', 'tenant', 'document_type', 'status', 'document_data', 'file_url',
                  'signed_file_url', 'access_token', 'sent_at', 'signed_at', 'created_at', 'updated_at']
        read_only_fields = ['id', 'access_token', 'sent_at', 'signed_at', 'created_at', 'updated_at']


class TenancyDocumentDetailSerializer(serializers.ModelSerializer):
    tenant_name = serializers.SerializerMethodField()
    property_name = serializers.SerializerMethodField()
    unit_number = serializers.SerializerMethodField()

    class Meta:
        model = TenancyDocument
        fields = ['id', 'tenant', 'tenant_name', 'property_name', 'unit_number',
                  'document_type', 'status', 'document_data', 'file_url',
                  'signed_file_url', 'access_token', 'sent_at', 'signed_at', 'created_at', 'updated_at']
        read_only_fields = fields

    def get_tenant_name(self, obj):
        return obj.tenant.name

    def get_property_name(self, obj):
        return obj.tenant.unit.property.name

    def get_unit_number(self, obj):
        return obj.tenant.unit.unit_number


class ReminderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reminder
        fields = ['id', 'tenant', 'channel', 'reminder_type', 'sent_at', 'delivery_status', 'message']
        read_only_fields = ['id', 'sent_at']


class QuitNoticeSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuitNotice
        fields = ['id', 'tenant', 'notice_date', 'effective_date', 'reason', 'status',
                  'document_url', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class DashboardPaymentSerializer(serializers.Serializer):
    tenant = serializers.CharField()
    amount = serializers.FloatField()
    date = serializers.DateField()
    period_start = serializers.DateField()
    period_end = serializers.DateField()


class DashboardStatsSerializer(serializers.Serializer):
    total_properties = serializers.IntegerField()
    total_units = serializers.IntegerField()
    occupied_units = serializers.IntegerField()
    occupancy_rate = serializers.FloatField()
    total_revenue = serializers.FloatField()
    upcoming_lease_expirations = serializers.ListField()
    recent_payments = DashboardPaymentSerializer(many=True)
    open_maintenance = serializers.IntegerField()
