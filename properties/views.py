from rest_framework import viewsets, status, serializers, filters
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.models import User
from django.db.models import Count, Sum, Q
from django_filters.rest_framework import DjangoFilterBackend
from datetime import datetime, timedelta
from .models import Property, Unit, Tenant, Payment, MaintenanceRequest
from .serializers import (
    PropertySerializer, PropertyListSerializer, UnitSerializer, UnitListSerializer,
    TenantSerializer, TenantListSerializer, PaymentSerializer, PaymentListSerializer,
    MaintenanceRequestSerializer, MaintenanceRequestListSerializer,
    RegisterSerializer, UserSerializer, UserProfileSerializer
)


@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    return Response({'status': 'ok'})


@api_view(['POST'])
@permission_classes([AllowAny])
def register_view(request):
    serializer = RegisterSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response({
            'user': UserSerializer(user).data,
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    username = request.data.get('username')
    password = request.data.get('password')

    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

    if user.check_password(password):
        refresh = RefreshToken.for_user(user)
        return Response({
            'user': UserSerializer(user).data,
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        })
    return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)


@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def profile_view(request):
    """Get or update the current user's profile."""
    if request.method == 'GET':
        serializer = UserSerializer(request.user)
        return Response(serializer.data)
    else:
        profile_serializer = UserProfileSerializer(
            request.user.profile, data=request.data, partial=True
        )
        if profile_serializer.is_valid():
            profile_serializer.save()
            return Response(UserSerializer(request.user).data)
        return Response(profile_serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_stats(request):
    # Total properties
    total_properties = Property.objects.filter(owner=request.user).count()

    # Total units
    total_units = Unit.objects.filter(property__owner=request.user).count()

    # Occupied units
    occupied_units = Unit.objects.filter(property__owner=request.user, status='Occupied').count()

    # Occupancy rate
    occupancy_rate = (occupied_units / total_units * 100) if total_units > 0 else 0

    # Monthly revenue (sum of all active tenants' monthly rent)
    monthly_revenue = Tenant.objects.filter(
        unit__property__owner=request.user,
        is_active=True
    ).aggregate(total=Sum('monthly_rent'))['total'] or 0

    # Upcoming lease expirations (next 30 days)
    thirty_days_later = datetime.now().date() + timedelta(days=30)
    upcoming_expirations = Tenant.objects.filter(
        unit__property__owner=request.user,
        lease_expiry_date__lte=thirty_days_later,
        lease_expiry_date__gte=datetime.now().date(),
        is_active=True
    ).select_related('unit', 'unit__property')

    upcoming_list = []
    for tenant in upcoming_expirations:
        upcoming_list.append({
            'tenant': tenant.name,
            'unit': tenant.unit.unit_number,
            'property': tenant.unit.property.name,
            'expiry_date': tenant.lease_expiry_date,
        })

    # Recent payments
    recent_payments = Payment.objects.filter(
        tenant__unit__property__owner=request.user
    ).order_by('-payment_date')[:5]

    payments_list = []
    for payment in recent_payments:
        payments_list.append({
            'tenant': payment.tenant.name,
            'amount': float(payment.amount),
            'date': payment.payment_date,
            'month_for': payment.month_for,
        })

    # Maintenance requests
    open_maintenance = MaintenanceRequest.objects.filter(
        unit__property__owner=request.user
    ).exclude(status='Completed').count()

    return Response({
        'total_properties': total_properties,
        'total_units': total_units,
        'occupied_units': occupied_units,
        'occupancy_rate': round(occupancy_rate, 1),
        'monthly_revenue': float(monthly_revenue),
        'upcoming_lease_expirations': upcoming_list,
        'recent_payments': payments_list,
        'open_maintenance': open_maintenance,
    })


class PropertyViewSet(viewsets.ModelViewSet):
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'address', 'property_type', 'description']
    ordering_fields = ['name', 'created_at', 'property_type', 'total_units']
    ordering = ['-created_at']

    def get_queryset(self):
        return Property.objects.filter(owner=self.request.user)

    def get_serializer_class(self):
        if self.action == 'list':
            return PropertyListSerializer
        return PropertySerializer

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class UnitViewSet(viewsets.ModelViewSet):
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['unit_number', 'status']
    ordering_fields = ['unit_number', 'bedrooms', 'price_rent', 'status', 'created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        return Unit.objects.filter(property__owner=self.request.user)

    def get_serializer_class(self):
        if self.action == 'list':
            return UnitListSerializer
        return UnitSerializer

    def perform_create(self, serializer):
        property_id = serializer.validated_data.get('property_id')
        try:
            prop = Property.objects.get(id=property_id, owner=self.request.user)
        except Property.DoesNotExist:
            raise serializers.ValidationError({'property_id': 'Property not found or not owned by you.'})
        serializer.save(property=prop)


class TenantViewSet(viewsets.ModelViewSet):
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'phone', 'email']
    ordering_fields = ['name', 'monthly_rent', 'lease_expiry_date', 'created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        return Tenant.objects.filter(unit__property__owner=self.request.user)

    def get_serializer_class(self):
        if self.action == 'list':
            return TenantListSerializer
        return TenantSerializer

    def perform_create(self, serializer):
        tenant = serializer.save()
        unit = tenant.unit
        unit.status = 'Occupied'
        unit.save()

    def perform_update(self, serializer):
        old_tenant = self.get_object()
        tenant = serializer.save()
        if not tenant.is_active:
            unit = tenant.unit
            unit.status = 'Available'
            unit.save()


class PaymentViewSet(viewsets.ModelViewSet):
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['month_for', 'reference', 'payment_method', 'notes']
    ordering_fields = ['amount', 'payment_date', 'created_at']
    ordering = ['-payment_date']

    def get_queryset(self):
        return Payment.objects.filter(tenant__unit__property__owner=self.request.user)

    def get_serializer_class(self):
        if self.action == 'list':
            return PaymentListSerializer
        return PaymentSerializer


class MaintenanceRequestViewSet(viewsets.ModelViewSet):
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'description', 'status', 'priority', 'reported_by']
    ordering_fields = ['priority', 'status', 'created_at', 'updated_at']
    ordering = ['-created_at']

    def get_queryset(self):
        return MaintenanceRequest.objects.filter(unit__property__owner=self.request.user)

    def get_serializer_class(self):
        if self.action == 'list':
            return MaintenanceRequestListSerializer
        return MaintenanceRequestSerializer

    def perform_create(self, serializer):
        reported_by = serializer.validated_data.get('reported_by')
        if not reported_by:
            user = self.request.user
            reported_by = user.get_full_name() or user.username
        serializer.save(reported_by=reported_by)
