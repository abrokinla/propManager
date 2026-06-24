from rest_framework import viewsets, status, serializers, filters
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.models import User
from django.db.models import Count, F, Sum, Q
from django.shortcuts import get_object_or_404
from django.http import HttpResponse, HttpResponseRedirect
from cloudinary.utils import cloudinary_url
from django_filters.rest_framework import DjangoFilterBackend
from datetime import datetime, timedelta, date
import logging
logger = logging.getLogger(__name__)
from .models import Property, Unit, Tenant, Payment, MaintenanceRequest, TenancyDocument, QuitNotice, Reminder, TenancyAgreementTemplate, DEFAULT_TEMPLATE_DATA, Notification, UserProfile
from .serializers import (
    PropertySerializer, PropertyListSerializer, UnitSerializer, UnitListSerializer,
    TenantSerializer, TenantListSerializer, PaymentSerializer, PaymentListSerializer,
    TenantPaymentSerializer,
    MaintenanceRequestSerializer, MaintenanceRequestListSerializer,
    RegisterSerializer, UserSerializer, UserProfileSerializer,
    TenancyDocumentSerializer, TenancyDocumentDetailSerializer,
    TenancyAgreementTemplateSerializer,
    ReminderSerializer, QuitNoticeSerializer,
    PublicPropertyListSerializer, PublicPropertyDetailSerializer,
    TenantSelfSerializer, TenantProfileUpdateSerializer,
    NotificationListSerializer, NotificationDetailSerializer,
)
from .services.document_service import send_tenancy_document
from .services.pdf_service import generate_tenancy_agreement
from .services.notice_service import issue_quit_notice
from .services.reminder_service import send_reminder as send_reminder_svc
from .services.storage_service import upload_file_bytes
from .services.invitation_service import send_invitation, resend_invitation
from .services.notification_service import notify
from .utils import generate_unit_prefix


def deep_merge(base, override):
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result


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

    profile = request.user.profile
    return Response({
        'public_slug': profile.public_slug,
        'company_name': profile.company_name,
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
def public_agent_properties(request, slug):
    profile = get_object_or_404(UserProfile, public_slug=slug)
    props = Property.objects.filter(
        owner=profile.user, is_published=True
    ).annotate(
        active_count=Count('units__tenant', filter=Q(units__tenant__is_active=True))
    ).filter(active_count__lt=F('total_units')).distinct()
    serializer = PublicPropertyListSerializer(props, many=True)
    return Response({
        'agent': {
            'company_name': profile.company_name or profile.user.get_full_name() or profile.user.username,
        },
        'properties': serializer.data,
    })


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

    def perform_update(self, serializer):
        old = self.get_object()
        old_price = old.price_rent
        unit = serializer.save()
        tenant = Tenant.objects.filter(unit=unit, is_active=True).first()
        if tenant and 'price_rent' in serializer.validated_data:
            tenant.annual_rent = unit.price_rent
            tenant.save(update_fields=['annual_rent'])
            logger.info(f"Synced Tenant {tenant.id} annual_rent to {unit.price_rent}")
        if old_price != unit.price_rent and tenant:
            notify(
                recipient=tenant.user,
                type='rent_change',
                title=f'Rent Updated — {unit.property.name}',
                message=f'Your rent for {unit.property.name} - {unit.unit_number} has changed from ₦{old_price:,.0f} to ₦{unit.price_rent:,.0f} per {unit.get_rent_cycle_display()}.',
                link='/dashboard',
                send_email_flag=True,
            )


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
        if not tenant.annual_rent and unit_obj.price_rent:
            tenant.annual_rent = unit_obj.price_rent
            tenant.save(update_fields=['annual_rent'])
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

    def perform_destroy(self, instance):
        user = instance.user
        instance.delete()
        if user and not hasattr(user, 'profile'):
            user.delete()

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

    @action(detail=True, methods=['post'], url_path='documents/(?P<doc_id>[^/.]+)/verify')
    def verify_signed(self, request, pk=None, doc_id=None):
        tenant = self.get_object()
        document = get_object_or_404(TenancyDocument, id=doc_id, tenant=tenant)
        if document.status != 'pending_verification':
            return Response({'error': 'Document is not pending verification'}, status=status.HTTP_400_BAD_REQUEST)

        action = request.data.get('action')
        if action == 'verify':
            document.status = 'signed'
            document.signed_at = datetime.now()
            document.save(update_fields=['status', 'signed_at'])
            tenant.tenancy_status = 'document_signed'
            tenant.save(update_fields=['tenancy_status'])
            notify(
                recipient=tenant.user,
                type='document_verified',
                title='Agreement Verified',
                message=f'Your tenancy agreement for {document.tenant.unit.property.name} - {document.tenant.unit.unit_number} has been verified.',
                link='/tenancy-agreement',
                send_email_flag=True,
                email_subject='Tenancy Agreement Verified',
                email_body=(
                    f'<p>Dear {tenant.name},</p>'
                    f'<p>Your tenancy agreement for {document.tenant.unit.property.name} - '
                    f'{document.tenant.unit.unit_number} has been verified as signed.</p>'
                ),
            )
        elif action == 'reject':
            reason = request.data.get('reason', '')
            document.status = 'sent'
            document.verification_note = reason
            document.save(update_fields=['status', 'verification_note'])
            notify(
                recipient=tenant.user,
                type='document_rejected',
                title='Agreement Verification Failed',
                message=f'Your signed tenancy agreement for {document.tenant.unit.property.name} - {document.tenant.unit.unit_number} was not accepted. Reason: {reason}',
                link='/tenancy-agreement',
                send_email_flag=True,
                email_subject='Tenancy Agreement Verification Failed',
                email_body=(
                    f'<p>Dear {tenant.name},</p>'
                    f'<p>Your signed tenancy agreement for {document.tenant.unit.property.name} - '
                    f'{document.tenant.unit.unit_number} was not accepted.</p>'
                    f'<p><b>Reason:</b> {reason}</p>'
                    f'<p>Please re-upload your signed copy.</p>'
                ),
            )
        else:
            return Response({'error': 'action must be "verify" or "reject"'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = TenancyDocumentSerializer(document)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def quit_notice(self, request, pk=None):
        tenant = self.get_object()
        reason = request.data.get('reason')
        notice = issue_quit_notice(tenant, reason)

        notify(
            recipient=tenant.user,
            type='quit_notice',
            title='Quit Notice Issued',
            message=f'A quit notice has been issued for {tenant.unit.property.name} - {tenant.unit.unit_number}. Reason: {reason}',
            link='/dashboard',
            send_email_flag=True,
        )

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
    filterset_fields = ['tenant']
    search_fields = ['reference', 'payment_method', 'notes', 'status']
    ordering_fields = ['amount', 'payment_date', 'created_at']
    ordering = ['-payment_date']

    def get_queryset(self):
        return Payment.objects.filter(tenant__unit__property__owner=self.request.user)

    def get_serializer_class(self):
        if self.action == 'list':
            return PaymentListSerializer
        return PaymentSerializer

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        import calendar
        payment = self.get_object()
        if payment.status != 'pending':
            return Response({'error': f'Payment is already {payment.status}'}, status=400)
        payment.status = 'approved'
        payment.approved_by = request.user
        payment.approved_at = datetime.now()
        payment.save(update_fields=['status', 'approved_by', 'approved_at'])

        tenant = payment.tenant
        if tenant.annual_rent and tenant.annual_rent > 0:
            def add_months(d, n):
                total = d.year * 12 + d.month - 1 + n
                y = total // 12
                m = total % 12 + 1
                try:
                    return d.replace(year=y, month=m)
                except ValueError:
                    last_day = calendar.monthrange(y, m)[1]
                    return d.replace(year=y, month=m, day=last_day)

            if not payment.period_end:
                cycle = tenant.rent_cycle or 'yearly'
                annual = float(tenant.annual_rent)

                if cycle == 'yearly':
                    months_per_unit = 12
                    cost_per_unit = annual
                elif cycle == 'monthly':
                    months_per_unit = 1
                    cost_per_unit = annual / 12
                else:  # daily
                    months_per_unit = 1
                    cost_per_unit = annual / 365

                units_paid = float(payment.amount) / cost_per_unit
                total_months = max(int(units_paid * months_per_unit), 1)
                payment.years_covered = max(total_months // 12, 1)

                if not payment.period_start:
                    payment.period_start = datetime.now().date()

                if tenant.lease_start_date and tenant.lease_expiry_date:
                    coverage_start = tenant.lease_expiry_date
                else:
                    coverage_start = payment.period_start

                payment.period_end = add_months(coverage_start, total_months)
                payment.save(update_fields=['years_covered', 'period_end', 'period_start'])

                if tenant.lease_start_date and tenant.lease_expiry_date:
                    tenant.lease_expiry_date = add_months(tenant.lease_expiry_date, total_months)
                    tenant.lease_renewal_date = tenant.lease_expiry_date
                else:
                    tenant.lease_start_date = payment.period_start
                    tenant.lease_expiry_date = payment.period_end
                    tenant.lease_renewal_date = payment.period_end

                if tenant.tenancy_status in ('document_signed', 'document_sent'):
                    tenant.tenancy_status = 'active'
                tenant.save(update_fields=['lease_start_date', 'lease_expiry_date', 'lease_renewal_date', 'tenancy_status'])

        notify(
            recipient=tenant.user,
            type='payment_approved',
            title='Payment Approved',
            message=f'Your payment of ₦{float(payment.amount):,.0f} for {tenant.unit.property.name} has been approved.',
            link='/dashboard',
            send_email_flag=True,
        )

        serializer = self.get_serializer(payment)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        payment = self.get_object()
        if payment.status != 'pending':
            return Response({'error': f'Payment is already {payment.status}'}, status=400)
        reason = request.data.get('reason', '')
        payment.status = 'rejected'
        payment.rejection_reason = reason
        payment.approved_by = request.user
        payment.approved_at = datetime.now()
        payment.save(update_fields=['status', 'rejection_reason', 'approved_by', 'approved_at'])

        notify(
            recipient=payment.tenant.user,
            type='payment_rejected',
            title='Payment Rejected',
            message=f'Your payment of ₦{float(payment.amount):,.0f} for {payment.tenant.unit.property.name} has been rejected. Reason: {reason}',
            link='/dashboard',
            send_email_flag=True,
        )

        serializer = self.get_serializer(payment)
        return Response(serializer.data)


class AgreementTemplateViewSet(viewsets.ModelViewSet):
    serializer_class = TenancyAgreementTemplateSerializer

    def get_queryset(self):
        return TenancyAgreementTemplate.objects.filter(property__owner=self.request.user)

    def perform_create(self, serializer):
        property_id = serializer.validated_data.get('property_id')
        try:
            prop = Property.objects.get(id=property_id, owner=self.request.user)
        except Property.DoesNotExist:
            raise serializers.ValidationError({'property_id': 'Property not found or not owned by you.'})
        template_data = serializer.validated_data.get('template_data', {})
        merged = deep_merge(DEFAULT_TEMPLATE_DATA, template_data)
        serializer.save(property=prop, template_data=merged)

    @action(detail=True, methods=['post'])
    def upload_pdf(self, request, pk=None):
        template = self.get_object()
        pdf_file = request.FILES.get('file')
        if not pdf_file:
            return Response({'error': 'file is required'}, status=status.HTTP_400_BAD_REQUEST)
        file_bytes = pdf_file.read()
        url = upload_file_bytes(file_bytes, pdf_file.name, pdf_file.content_type, folder='agreement_pdfs')
        template.uploaded_pdf_url = url
        template.save(update_fields=['uploaded_pdf_url'])
        return Response({'uploaded_pdf_url': url})


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    pagination_class = None
    lookup_value_regex = '[0-9]+'

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user)

    def get_serializer_class(self):
        if self.action == 'list':
            return NotificationListSerializer
        return NotificationDetailSerializer

    @action(detail=False, methods=['get'], url_path='unread-count')
    def unread_count(self, request):
        count = self.get_queryset().filter(is_read=False).count()
        return Response({'count': count})

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.save(update_fields=['is_read'])
        return Response({'status': 'ok'})

    @action(detail=False, methods=['post'], url_path='mark-all-read')
    def mark_all_read(self, request):
        self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({'status': 'ok'})


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
        req = serializer.save(reported_by=reported_by)
        try:
            tenant = req.unit.tenant
            if tenant and tenant.is_active:
                notify(
                    recipient=tenant.user,
                    type='maintenance_request',
                    title=f'Maintenance Request — {req.unit.unit_number}',
                    message=f'A maintenance request has been logged: {req.title} — {req.description}. Status: {req.status}.',
                    link='/dashboard',
                    send_email_flag=True,
                    email_body=(
                        f'<p>A maintenance request has been logged for <strong>{req.unit.unit_number}</strong>.</p>'
                        f'<p><strong>Title:</strong> {req.title}<br>'
                        f'<strong>Priority:</strong> {req.priority}<br>'
                        f'<strong>Status:</strong> {req.status}<br>'
                        f'<strong>Description:</strong><br>{req.description}</p>'
                    ),
                )
        except Tenant.DoesNotExist:
            pass


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


@api_view(['GET'])
@permission_classes([AllowAny])
def public_document_download_unsigned(request, token):
    document = get_object_or_404(TenancyDocument, access_token=token)
    url = document.file_url or (document.document_data or {}).get('uploaded_pdf_url', '')
    if not url:
        return Response({'error': 'No file available'}, status=404)
    signed_url, _ = cloudinary_url(url, sign_url=True)
    response = HttpResponseRedirect(signed_url)
    response['Content-Disposition'] = f'attachment; filename="agreement_{document.id}.pdf"'
    return response


@api_view(['GET'])
@permission_classes([AllowAny])
def public_document_download_signed(request, token):
    document = get_object_or_404(TenancyDocument, access_token=token)
    if not document.signed_file_url:
        return Response({'error': 'No signed file available'}, status=404)
    signed_url, _ = cloudinary_url(document.signed_file_url, sign_url=True)
    response = HttpResponseRedirect(signed_url)
    response['Content-Disposition'] = f'attachment; filename="signed_agreement_{document.id}.pdf"'
    return response


# ── Tenant Self-Service Endpoints ──────────────────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])
def tenant_login(request):
    email = request.data.get('email')
    password = request.data.get('password')
    if not email or not password:
        return Response({'error': 'Email and password are required'}, status=400)

    users = User.objects.filter(email=email)
    if not users.exists():
        return Response({'error': 'Invalid credentials'}, status=401)
    user = users.filter(tenant_profile__isnull=False).first() or users.first()

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
def tenant_upload_signed(request, doc_id):
    if not hasattr(request.user, 'tenant_profile') or not request.user.tenant_profile:
        return Response({'error': 'Not a tenant user'}, status=403)
    tenant = request.user.tenant_profile
    document = get_object_or_404(TenancyDocument, id=doc_id, tenant=tenant)
    if document.status == 'signed':
        return Response({'error': 'Document already signed'}, status=400)
    if document.status == 'pending_verification':
        return Response({'error': 'Document is already pending verification'}, status=400)
    if document.mode != 'uploaded_pdf':
        return Response({'error': 'This agreement uses template mode. Please use the electronic sign option.'}, status=400)

    signed_file = request.FILES.get('signed_file')
    if not signed_file:
        return Response({'error': 'signed_file is required'}, status=status.HTTP_400_BAD_REQUEST)

    file_bytes = signed_file.read()
    url = upload_file_bytes(file_bytes, signed_file.name, signed_file.content_type, folder='signed_documents')

    document.signed_file_url = url
    document.status = 'pending_verification'
    document.save(update_fields=['signed_file_url', 'status'])

    agent = document.tenant.unit.property.owner
    notify(
        recipient=agent,
        type='document_uploaded',
        title=f'Signed Agreement Submitted — {tenant.name}',
        message=f'{tenant.name} has uploaded a signed copy of the tenancy agreement for {document.tenant.unit.property.name} - {document.tenant.unit.unit_number}. Please verify it.',
        link='/tenants',
        send_email_flag=True,
        email_subject=f'Signed Agreement Submitted - {tenant.name}',
        email_body=(
            f'<p>Dear {agent.get_full_name() or agent.username},</p>'
            f'<p>{tenant.name} has uploaded a signed copy of the tenancy agreement for '
            f'{document.tenant.unit.property.name} - {document.tenant.unit.unit_number}.</p>'
            f'<p>Please verify the document in your dashboard.</p>'
        ),
    )

    return Response({
        'status': 'pending_verification',
        'signed_file_url': url,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def tenant_sign_document(request, doc_id):
    if not hasattr(request.user, 'tenant_profile') or not request.user.tenant_profile:
        return Response({'error': 'Not a tenant user'}, status=403)
    tenant = request.user.tenant_profile
    document = get_object_or_404(TenancyDocument, id=doc_id, tenant=tenant)
    if document.status == 'signed':
        return Response({'error': 'Document already signed'}, status=400)

    if document.mode == 'uploaded_pdf':
        return Response({'error': 'This agreement uses uploaded PDF mode. Please upload your signed copy instead.'}, status=400)

    if not Payment.objects.filter(tenant=tenant, status='approved').exists():
        return Response({'error': 'You must complete rent payment and have it approved before signing the agreement.'}, status=400)

    signature_name = request.data.get('signature_name', tenant.name)
    signed_date = date.today()
    witness_data = {
        'witness_name': request.data.get('witness_name', ''),
        'witness_address': request.data.get('witness_address', ''),
        'witness_occupation': request.data.get('witness_occupation', ''),
    }
    logo_url = ''
    try:
        template = TenancyAgreementTemplate.objects.get(property=document.tenant.unit.property)
        logo_url = template.logo_url
    except TenancyAgreementTemplate.DoesNotExist:
        pass

    doc_data = dict(document.document_data)
    doc_data['witness_tenant'] = witness_data

    pdf_bytes = generate_tenancy_agreement(
        doc_data,
        signature_name=signature_name,
        signed_date=signed_date,
        logo_url=logo_url,
    )

    filename = f"tenancy_agreement_{tenant.id}_{signed_date.isoformat()}.pdf"
    url = upload_file_bytes(pdf_bytes, filename, 'application/pdf', folder='signed_documents')

    document.status = 'signed'
    document.signed_file_url = url
    document.signed_at = datetime.now()
    document.save(update_fields=['status', 'signed_file_url', 'signed_at'])

    tenant.tenancy_status = 'document_signed'
    tenant.save(update_fields=['tenancy_status'])

    agent = document.tenant.unit.property.owner
    notify(
        recipient=agent,
        type='document_signed',
        title=f'Agreement Signed — {tenant.name}',
        message=f'{tenant.name} has signed the tenancy agreement for {document.tenant.unit.property.name} - {document.tenant.unit.unit_number}.',
        link='/tenants',
        send_email_flag=False,
    )

    if agent.email:
        from .services.email_service import send_email
        send_email(
            to=agent.email,
            subject=f'Tenancy Agreement Signed - {tenant.name}',
            html_body=(
                f'<p>Dear {agent.get_full_name() or agent.username},</p>'
                f'<p>{tenant.name} has signed the tenancy agreement for '
                f'{document.tenant.unit.property.name} - {document.tenant.unit.unit_number}.</p>'
                f'<p>Signed on: {signed_date.strftime("%B %d, %Y")}</p>'
                f'<p>The signed document is attached to this email.</p>'
            ),
            attachment_bytes=pdf_bytes,
            attachment_filename=filename,
        )

    return Response({'status': 'signed', 'signed_file_url': url, 'signed_at': document.signed_at})


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
def tenant_document_detail(request, doc_id):
    if not hasattr(request.user, 'tenant_profile') or not request.user.tenant_profile:
        return Response({'error': 'Not a tenant user'}, status=403)
    tenant = request.user.tenant_profile
    document = get_object_or_404(TenancyDocument, id=doc_id, tenant=tenant)
    serializer = TenancyDocumentDetailSerializer(document)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def tenant_download_signed(request, doc_id):
    if not hasattr(request.user, 'tenant_profile') or not request.user.tenant_profile:
        return Response({'error': 'Not a tenant user'}, status=403)
    tenant = request.user.tenant_profile
    document = get_object_or_404(TenancyDocument, id=doc_id, tenant=tenant)
    if not document.signed_file_url:
        return Response({'error': 'No signed file available'}, status=404)
    signed_url, _ = cloudinary_url(document.signed_file_url, sign_url=True)
    response = HttpResponseRedirect(signed_url)
    response['Content-Disposition'] = f'attachment; filename="signed_agreement_{doc_id}.pdf"'
    return response


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def tenant_download_unsigned(request, doc_id):
    if not hasattr(request.user, 'tenant_profile') or not request.user.tenant_profile:
        return Response({'error': 'Not a tenant user'}, status=403)
    tenant = request.user.tenant_profile
    document = get_object_or_404(TenancyDocument, id=doc_id, tenant=tenant)
    url = document.file_url or (document.document_data or {}).get('uploaded_pdf_url', '')
    if not url:
        return Response({'error': 'No file available'}, status=404)
    signed_url, _ = cloudinary_url(url, sign_url=True)
    response = HttpResponseRedirect(signed_url)
    response['Content-Disposition'] = f'attachment; filename="agreement_{doc_id}.pdf"'
    return response


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def tenant_agreement(request):
    if not hasattr(request.user, 'tenant_profile') or not request.user.tenant_profile:
        return Response({'error': 'Not a tenant user'}, status=403)
    tenant = request.user.tenant_profile
    prop = tenant.unit.property

    existing = TenancyDocument.objects.filter(tenant=tenant, document_type='tenancy_agreement').exclude(status='draft').first()
    if existing:
        # Check if verification_note should be cleared (re-upload after rejection)
        if existing.status == 'sent' and existing.verification_note and request.GET.get('cleared'):
            existing.verification_note = ''
            existing.save(update_fields=['verification_note'])
        serializer = TenancyDocumentDetailSerializer(existing)
        return Response(serializer.data)

    try:
        template = TenancyAgreementTemplate.objects.get(property=prop)
    except TenancyAgreementTemplate.DoesNotExist:
        return Response({'error': 'No agreement template set up for your property.'}, status=404)

    if template.mode == 'uploaded_pdf':
        document = TenancyDocument.objects.create(
            tenant=tenant,
            document_type='tenancy_agreement',
            status='sent',
            mode='uploaded_pdf',
            file_url=template.uploaded_pdf_url,
            sent_at=datetime.now(),
        )
        serializer = TenancyDocumentDetailSerializer(document)
        return Response(serializer.data)

    def _fmt_date(d):
        if not d:
            return ''
        day = d.day
        suffix = 'th' if 11 <= day <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
        return f"{day}{suffix} {d.strftime('%B, %Y')}"

    data = dict(template.template_data)

    if 'landlord' not in data or not isinstance(data.get('landlord'), dict):
        data['landlord'] = {}
    if not data['landlord'].get('name'):
        data['landlord']['name'] = prop.owner.get_full_name() or prop.owner.username

    template_property = template.template_data.get('property', {}) or {}
    data['property'] = {
        'name': prop.name,
        'description': prop.description,
        'address': prop.address,
        'property_type': prop.get_property_type_display(),
        'unit_number': tenant.unit.unit_number,
        'referred_to_as': template_property.get('referred_to_as', 'The Demised Premises'),
        'ownership_note': template_property.get('ownership_note', 'Bona fide property of the landlord'),
    }

    if 'tenancy_terms' not in data or not isinstance(data.get('tenancy_terms'), dict):
        data['tenancy_terms'] = {}
    if tenant.annual_rent:
        data['tenancy_terms']['annual_rent_amount'] = float(tenant.annual_rent)
    data['tenancy_terms']['commencement_date'] = _fmt_date(tenant.lease_start_date)
    data['tenancy_terms']['expiry_date'] = _fmt_date(tenant.lease_expiry_date)

    data['tenant_name'] = tenant.name

    document = TenancyDocument.objects.create(
        tenant=tenant,
        document_type='tenancy_agreement',
        status='sent',
        document_data=data,
        sent_at=datetime.now(),
    )

    serializer = TenancyDocumentDetailSerializer(document)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def pending_verifications(request):
    docs = TenancyDocument.objects.filter(
        status='pending_verification',
        tenant__unit__property__owner=request.user,
    ).select_related('tenant', 'tenant__unit', 'tenant__unit__property')
    return Response([{
        'tenant_id': d.tenant_id,
        'tenant_name': d.tenant.name,
        'document_id': d.id,
        'property_id': d.tenant.unit.property_id,
        'signed_file_url': d.signed_file_url,
    } for d in docs])


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def tenant_express_interest(request):
    if not hasattr(request.user, 'tenant_profile') or not request.user.tenant_profile:
        return Response({'error': 'Not a tenant user'}, status=403)
    tenant = request.user.tenant_profile
    property_id = request.data.get('property_id')
    if not property_id:
        return Response({'error': 'property_id is required'}, status=400)
    try:
        prop = Property.objects.get(id=property_id, is_published=True)
    except Property.DoesNotExist:
        return Response({'error': 'Property not found'}, status=404)

    agent = prop.owner
    message = request.data.get('message', f'{tenant.name} is interested in buying/renting {prop.name}.')

    notify(
        recipient=agent,
        type='purchase_interest',
        title=f'Interest in {prop.name}',
        message=message,
        link='/properties',
        send_email_flag=True,
        email_subject=f'Purchase Interest — {prop.name}',
        email_body=(
            f'<p>Dear {agent.get_full_name() or agent.username},</p>'
            f'<p>{tenant.name} has expressed interest in <b>{prop.name}</b>.</p>'
            f'<p><b>Message:</b> {message}</p>'
            f'<p>Contact: {tenant.email} | {tenant.phone}</p>'
        ),
    )

    return Response({'status': 'interest expressed'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def tenant_change_password(request):
    if not hasattr(request.user, 'tenant_profile') or not request.user.tenant_profile:
        return Response({'error': 'Not a tenant user'}, status=403)

    current_password = request.data.get('current_password')
    new_password = request.data.get('new_password')
    if not current_password or not new_password:
        return Response({'error': 'current_password and new_password are required'}, status=400)
    if len(new_password) < 8:
        return Response({'error': 'Password must be at least 8 characters'}, status=400)

    if not request.user.check_password(current_password):
        return Response({'error': 'Current password is incorrect'}, status=400)

    request.user.set_password(new_password)
    request.user.save()
    return Response({'status': 'password updated'})


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def tenant_maintenance(request):
    if not hasattr(request.user, 'tenant_profile') or not request.user.tenant_profile:
        return Response({'error': 'Not a tenant user'}, status=403)

    tenant = request.user.tenant_profile

    if request.method == 'GET':
        requests = MaintenanceRequest.objects.filter(unit=tenant.unit).order_by('-created_at')
        serializer = MaintenanceRequestListSerializer(requests, many=True)
        return Response(serializer.data)

    title = request.data.get('title')
    description = request.data.get('description')
    priority = request.data.get('priority', 'Medium')

    if not title or not description:
        return Response({'error': 'title and description are required'}, status=400)

    req = MaintenanceRequest.objects.create(
        unit=tenant.unit,
        title=title,
        description=description,
        priority=priority,
        reported_by=tenant.name,
    )

    agent = tenant.unit.property.owner
    notify(
        recipient=agent,
        type='maintenance_request',
        title=f'Maintenance Request — {tenant.unit.unit_number}',
        message=f'{tenant.name} reported: {title} — {description}',
        link='/maintenance',
        send_email_flag=True,
        email_body=(
            f'<p><strong>{tenant.name}</strong> reported a maintenance issue.</p>'
            f'<p><strong>Unit:</strong> {tenant.unit.unit_number}<br>'
            f'<strong>Title:</strong> {title}<br>'
            f'<strong>Priority:</strong> {priority}<br>'
            f'<strong>Description:</strong><br>{description}</p>'
        ),
    )

    serializer = MaintenanceRequestListSerializer(req)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def tenant_payments(request):
    if not hasattr(request.user, 'tenant_profile') or not request.user.tenant_profile:
        return Response({'error': 'Not a tenant user'}, status=403)
    tenant = request.user.tenant_profile

    if request.method == 'GET':
        payments = tenant.payments.all().order_by('-payment_date')
        serializer = TenantPaymentSerializer(payments, many=True)
        return Response(serializer.data)

    proof_url = ''
    proof_file = request.FILES.get('proof')
    if proof_file:
        proof_url = upload_file_bytes(proof_file.read(), proof_file.name, proof_file.content_type, folder='payment_proofs')

    data = request.data.copy()
    if isinstance(data, dict):
        data['proof_url'] = proof_url

    serializer = TenantPaymentSerializer(data=data)
    if serializer.is_valid():
        payment = serializer.save(tenant=tenant, proof_url=proof_url)
        agent = tenant.unit.property.owner
        notify(
            recipient=agent,
            type='payment_received',
            title=f'Payment Received — {tenant.name}',
            message=f'{tenant.name} has submitted a payment of ₦{float(payment.amount):,.0f} for {tenant.unit.property.name} - {tenant.unit.unit_number}.',
            link='/payments',
            send_email_flag=True,
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
