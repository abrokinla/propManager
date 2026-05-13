from rest_framework import serializers
from django.contrib.auth.models import User
from .models import UserProfile, Property, Unit, Tenant, Payment, MaintenanceRequest


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
        fields = ['id', 'name', 'address', 'property_type', 'description', 'owner', 'owner_id', 'units_count', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

    def get_units_count(self, obj):
        return obj.units.count()


class PropertyListSerializer(serializers.ModelSerializer):
    owner = UserSerializer(read_only=True)
    units_count = serializers.SerializerMethodField()

    class Meta:
        model = Property
        fields = ['id', 'name', 'address', 'property_type', 'owner', 'units_count', 'created_at']

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

    class Meta:
        model = Tenant
        fields = ['id', 'unit', 'unit_id', 'name', 'phone', 'email', 'address', 'monthly_rent',
                  'lease_start_date', 'lease_renewal_date', 'lease_expiry_date', 'move_in_date',
                  'is_active', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


class TenantListSerializer(serializers.ModelSerializer):
    unit_number = serializers.SerializerMethodField()
    property_name = serializers.SerializerMethodField()

    class Meta:
        model = Tenant
        fields = ['id', 'name', 'email', 'phone', 'unit_number', 'property_name', 'monthly_rent', 'lease_expiry_date', 'is_active']

    def get_unit_number(self, obj):
        return obj.unit.unit_number

    def get_property_name(self, obj):
        return obj.unit.property.name


class PaymentSerializer(serializers.ModelSerializer):
    tenant = TenantListSerializer(read_only=True)
    tenant_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = Payment
        fields = ['id', 'tenant', 'tenant_id', 'amount', 'payment_date', 'payment_method', 'month_for', 'notes', 'created_at']
        read_only_fields = ['created_at']


class PaymentListSerializer(serializers.ModelSerializer):
    tenant_name = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = ['id', 'tenant_name', 'amount', 'payment_date', 'payment_method', 'month_for']

    def get_tenant_name(self, obj):
        return obj.tenant.name


class MaintenanceRequestSerializer(serializers.ModelSerializer):
    unit = UnitListSerializer(read_only=True)
    unit_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = MaintenanceRequest
        fields = ['id', 'unit', 'unit_id', 'title', 'description', 'priority', 'status',
                  'reported_by', 'resolved_at', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


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
