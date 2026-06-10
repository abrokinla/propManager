from rest_framework import viewsets, status, serializers, filters
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.models import User
from django.db.models import Count, F, Sum, Q
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from datetime import datetime, timedelta
import logging
logger = logging.getLogger(__name__)
from .models import Property, Unit, Tenant, Payment, MaintenanceRequest, TenancyDocument, QuitNotice, Reminder
from .serializers import (
    PropertySerializer, PropertyListSerializer, UnitSerializer, UnitListSerializer,
    TenantSerializer, TenantListSerializer, PaymentSerializer, PaymentListSerializer,
    MaintenanceRequestSerializer, MaintenanceRequestListSerializer,
    RegisterSerializer, UserSerializer, UserProfileSerializer,
    TenancyDocumentSerializer, TenancyDocumentDetailSerializer,
    ReminderSerializer, QuitNoticeSerializer,
    PublicPropertyListSerializer, PublicPropertyDetailSerializer,
    TenantSelfSerializer, TenantProfileUpdateSerializer,
)
from .services.document_service import send_tenancy_document
from .services.notice_service import issue_quit_notice
from .services.reminder_service import send_reminder as send_reminder_svc
from .services.storage_service import upload_file_bytes
from .services.invitation_service import send_invitation, resend_invitation
from .utils import generate_unit_prefix


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
    total_properties = Property.objects.filter(owner=request.user).count()
    total_units = Unit.objects.filter(property__owner=request.user).count()
    total_capacity = Property.objects.filter(owner=request.user).aggregate(total=Sum('total_units'))['total'] or 0
    active_tenants = Tenant.objects.filter(unit__property__owner=request.user, is_active=True).count()
    occupancy_rate = (active_tenants / total_capacity * 100) if total_capacity > 0 else 0

    total_revenue = Payment.objects.filter(
        tenant__unit__property__owner=request.user,
        payment_date__gte=datetime.now().date() - timedelta(days=365),
    ).aggregate(total=Sum('amount'))['total'] or 0

    thirty_days_later = datetime.now().date() + timedelta(days=30)
    upcoming_expirations = Tenant.objects.filter(
        unit__property__owner=request.user,
        lease_expiry_date__lte=thirty_days_later,
        lease_expiry_date__gte=datetime.now().date(),
        is_active=True
    ).select_related('unit', 'unit__property')

    upcoming_list = [{
        'tenant': t.name,
        'unit': t.unit.unit_number,
        'property': t.unit.property.name,
        'expiry_date': t.lease_expiry_date,
    } for t in upcoming_expirations]

    recent_payments = Payment.objects.filter(
        tenant__unit__property__owner=request.user
    ).order_by('-payment_date')[:5]

    payments_list = [{
        'tenant': p.tenant.name,
        'amount': float(p.amount),
        'date': p.payment_date,
        'period_start': p.period_start,
        'period_end': p.period_end,
    } for p in recent_payments]

    open_maintenance = MaintenanceRequest.objects.filter(
        unit__property__owner=request.user
    ).exclude(status='Completed').count()

    return Response({
        'total_properties': total_properties,
        'total_units': total_units,
        'occupied_units': active_tenants,
        'occupancy_rate': round(occupancy_rate, 1),
        'total_revenue': float(total_revenue),
        'upcoming_lease_expirations': upcoming_list,
        'recent_payments': payments_list,
        'open_maintenance': open_maintenance,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_image(request):
    """Upload an image to Cloudinary and return the URL"""
    image = request.FILES.get('image')
    if not image:
        return Response({'error': 'No image file provided'}, status=400)
    allowed_types = ['image/jpeg', 'image/png', 'image/webp', 'image/gif']
    if image.content_type not in allowed_types:
        return Response({'error': f'Invalid file type: {image.content_type}. Allowed: JPEG, PNG, WebP, GIF'}, status=400)
    if image.size > 10 * 1024 * 1024:
        return Response({'error': 'File too large. Maximum size is 10MB'}, status=400)
    url = upload_file_bytes(image.read(), image.name, image.content_type, folder='properties')
    return Response({'image_url': url})


@api_view(['GET'])
@permission_classes([AllowAny])
def public_properties_list(request):
    props = Property.objects.filter(is_published=True).annotate(
        active_count=Count('units__tenant', filter=Q(units__tenant__is_active=True))
    ).filter(active_count__lt=F('total_units')).distinct()
    serializer = PublicPropertyListSerializer(props, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([AllowAny])
def public_property_detail(request, pk):
    prop = get_object_or_404(Property, pk=pk, is_published=True)
    serializer = PublicPropertyDetailSerializer(prop)
    return Response(serializer.data)


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
        prop = serializer.save(owner=self.request.user)
        prefix = generate_unit_prefix(prop.name)
        existing_count = Unit.objects.filter(property=prop).count()
        units = []
        for i in range(1, prop.total_units + 1):
            units.append(Unit(property=prop, unit_number=f"{prefix}{i:03d}"))
        Unit.objects.bulk_create(units)

    def perform_update(self, serializer):
        prop = serializer.save()
        prefix = generate_unit_prefix(prop.name)
        existing_count = Unit.objects.filter(property=prop).count()
        if prop.total_units > existing_count:
            units = []
            for i in range(existing_count + 1, prop.total_units + 1):
                units.append(Unit(property=prop, unit_number=f"{prefix}{i:03d}"))
            if units:
                Unit.objects.bulk_create(units)


class UnitViewSet(viewsets.ModelViewSet):
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['property_id']
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
    ordering_fields = ['name', 'annual_rent', 'lease_expiry_date', 'created_at', 'tenancy_status']
    ordering = ['-created_at']

    def get_queryset(self):
        return Tenant.objects.filter(unit__property__owner=self.request.user).select_related(
            'unit', 'unit__property'
        )

    def get_serializer_class(self):
        if self.action == 'list':
            return TenantListSerializer
        return TenantSerializer

    def perform_create(self, serializer):
        unit = serializer.validated_data.get('unit_id')
        try:
            unit_obj = Unit.objects.select_related('property').get(id=unit)
        except Unit.DoesNotExist:
            raise serializers.ValidationError({'unit_id': 'Unit not found.'})
        property_obj = unit_obj.property
        active_count = Tenant.objects.filter(unit__property=property_obj, is_active=True).count()
        if active_count >= property_obj.total_units:
            raise serializers.ValidationError(
                f'Property "{property_obj.name}" has reached its capacity of {property_obj.total_units} active tenant(s). '
                'Mark an existing tenant as inactive before adding a new one.'
            )
        tenant = serializer.save()
        tenant.unit.status = 'Occupied'
        tenant.unit.save(update_fields=['status'])
        if tenant.email:
            frontend_url = self.request.data.get('frontend_url', None)
            try:
                send_invitation(tenant, frontend_url)
            except Exception as e:
                logger.exception(f"Failed to send invitation to tenant {tenant.id}: {e}")

    def perform_update(self, serializer):
        old_tenant = self.get_object()
        tenant = serializer.save()
        if not tenant.is_active:
            tenant.unit.status = 'Available'
            tenant.unit.save(update_fields=['status'])
        elif tenant.is_active and not old_tenant.is_active:
            property_obj = tenant.unit.property
            active_count = Tenant.objects.filter(unit__property=property_obj, is_active=True).count()
            if active_count >= property_obj.total_units:
                raise serializers.ValidationError(
                    f'Property "{property_obj.name}" has reached its capacity of {property_obj.total_units} active tenant(s).'
                )

    @action(detail=True, methods=['get'])
    def documents(self, request, pk=None):
        tenant = self.get_object()
        docs = tenant.documents.all()
        serializer = TenancyDocumentSerializer(docs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def send_document(self, request, pk=None):
        tenant = self.get_object()
        document_data = request.data.get('document_data', {})
        document = TenancyDocument.objects.create(
            tenant=tenant,
            document_data=document_data,
            status='draft',
        )
        upload_base_url = request.data.get(
            'upload_base_url',
            request.build_absolute_uri('/')[:-1]
        )
        document = send_tenancy_document(document, upload_base_url)
        serializer = TenancyDocumentSerializer(document)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='documents/(?P<doc_id>[^/.]+)/upload-signed')
    def upload_signed(self, request, pk=None, doc_id=None):
        tenant = self.get_object()
        document = get_object_or_404(TenancyDocument, id=doc_id, tenant=tenant)
        signed_file = request.FILES.get('signed_file')
        if not signed_file:
            return Response({'error': 'signed_file is required'}, status=status.HTTP_400_BAD_REQUEST)
        file_bytes = signed_file.read()
        url = upload_file_bytes(file_bytes, signed_file.name, signed_file.content_type)
        document.signed_file_url = url
        document.status = 'signed'
        document.signed_at = datetime.now()
        document.save()
        tenant.tenancy_status = 'document_signed'
        tenant.save(update_fields=['tenancy_status'])
        serializer = TenancyDocumentSerializer(document)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def quit_notice(self, request, pk=None):
        tenant = self.get_object()
        reason = request.data.get('reason')
        notice = issue_quit_notice(tenant, reason)
        serializer = QuitNoticeSerializer(notice)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def quit_notices(self, request, pk=None):
        tenant = self.get_object()
        notices = tenant.quit_notices.all()
        serializer = QuitNoticeSerializer(notices, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def send_reminder(self, request, pk=None):
        tenant = self.get_object()
        reminder_type = request.data.get('reminder_type')
        channel = request.data.get('channel', 'email')
        if reminder_type not in ['lease_expiry', 'rent_due', 'document_sign', 'rent_renewal']:
            return Response({'error': 'Invalid reminder_type'}, status=status.HTTP_400_BAD_REQUEST)
        reminder = send_reminder_svc(tenant, reminder_type, channel)
        serializer = ReminderSerializer(reminder)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def reminders(self, request, pk=None):
        tenant = self.get_object()
        reminders = tenant.reminders.all()
        serializer = ReminderSerializer(reminders, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def resend_invite(self, request, pk=None):
        tenant = self.get_object()
        frontend_url = request.data.get('frontend_url', None)
        try:
            success = resend_invitation(tenant, frontend_url)
            if success:
                return Response({'status': 'invitation sent'})
            return Response({'error': 'Failed to send invitation'}, status=500)
        except Exception as e:
            return Response({'error': str(e)}, status=500)


class PaymentViewSet(viewsets.ModelViewSet):
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['reference', 'payment_method', 'notes']
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


@api_view(['GET'])
@permission_classes([AllowAny])
def public_document_detail(request, token):
    document = get_object_or_404(TenancyDocument, access_token=token)
    if document.status == 'signed':
        return Response({'error': 'Document already signed'}, status=status.HTTP_400_BAD_REQUEST)
    serializer = TenancyDocumentDetailSerializer(document)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([AllowAny])
def public_document_sign(request, token):
    document = get_object_or_404(TenancyDocument, access_token=token)
    if document.status == 'signed':
        return Response({'error': 'Document already signed'}, status=status.HTTP_400_BAD_REQUEST)
    signed_file = request.FILES.get('signed_file')
    if not signed_file:
        return Response({'error': 'signed_file is required'}, status=status.HTTP_400_BAD_REQUEST)
    file_bytes = signed_file.read()
    url = upload_file_bytes(file_bytes, signed_file.name, signed_file.content_type)
    document.signed_file_url = url
    document.status = 'signed'
    document.signed_at = datetime.now()
    document.save()
    tenant = document.tenant
    tenant.tenancy_status = 'document_signed'
    tenant.save(update_fields=['tenancy_status'])
    return Response({'status': 'signed', 'signed_file_url': url})


# ── Tenant Self-Service Endpoints ──────────────────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])
def tenant_login(request):
    email = request.data.get('email')
    password = request.data.get('password')
    if not email or not password:
        return Response({'error': 'Email and password are required'}, status=400)
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response({'error': 'Invalid credentials'}, status=401)
    if not user.check_password(password):
        return Response({'error': 'Invalid credentials'}, status=401)
    if not hasattr(user, 'tenant_profile') or not user.tenant_profile:
        return Response({'error': 'Not a tenant user'}, status=403)
    refresh = RefreshToken.for_user(user)
    tenant = user.tenant_profile
    return Response({
        'access': str(refresh.access_token),
        'refresh': str(refresh),
        'tenant': TenantSelfSerializer(tenant).data,
    })


@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def tenant_me(request):
    if not hasattr(request.user, 'tenant_profile') or not request.user.tenant_profile:
        return Response({'error': 'Not a tenant user'}, status=403)
    tenant = request.user.tenant_profile
    if request.method == 'GET':
        serializer = TenantSelfSerializer(tenant)
        return Response(serializer.data)
    serializer = TenantProfileUpdateSerializer(tenant, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        if tenant.tenancy_status == 'invited':
            tenant.tenancy_status = 'profile_pending'
            tenant.save(update_fields=['tenancy_status'])
        return Response(TenantSelfSerializer(tenant).data)
    return Response(serializer.errors, status=400)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def tenant_complete_profile(request):
    if not hasattr(request.user, 'tenant_profile') or not request.user.tenant_profile:
        return Response({'error': 'Not a tenant user'}, status=403)
    tenant = request.user.tenant_profile
    tenant.profile_completed = True
    if tenant.tenancy_status in ('invited', 'profile_pending'):
        tenant.tenancy_status = 'document_pending'
    tenant.save(update_fields=['profile_completed', 'tenancy_status'])
    return Response(TenantSelfSerializer(tenant).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def tenant_sign_document(request, doc_id):
    if not hasattr(request.user, 'tenant_profile') or not request.user.tenant_profile:
        return Response({'error': 'Not a tenant user'}, status=403)
    tenant = request.user.tenant_profile
    document = get_object_or_404(TenancyDocument, id=doc_id, tenant=tenant)
    if document.status == 'signed':
        return Response({'error': 'Document already signed'}, status=400)
    document.status = 'signed'
    document.signed_at = datetime.now()
    document.save(update_fields=['status', 'signed_at'])
    tenant.tenancy_status = 'document_signed'
    tenant.save(update_fields=['tenancy_status'])
    return Response({'status': 'signed', 'signed_at': document.signed_at})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def tenant_documents(request):
    if not hasattr(request.user, 'tenant_profile') or not request.user.tenant_profile:
        return Response({'error': 'Not a tenant user'}, status=403)
    tenant = request.user.tenant_profile
    docs = tenant.documents.all()
    serializer = TenancyDocumentSerializer(docs, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def tenant_payments(request):
    if not hasattr(request.user, 'tenant_profile') or not request.user.tenant_profile:
        return Response({'error': 'Not a tenant user'}, status=403)
    tenant = request.user.tenant_profile
    payments = tenant.payments.all().order_by('-payment_date')
    from .serializers import PaymentListSerializer
    serializer = PaymentListSerializer(payments, many=True)
    return Response(serializer.data)
