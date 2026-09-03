"""
URL configuration for propmanager project.
"""
from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from properties.views import (
    PropertyViewSet, UnitViewSet, TenantViewSet,
    PaymentViewSet, MaintenanceRequestViewSet,
    AgreementTemplateViewSet, NotificationViewSet,
    PropertyAvailabilityViewSet, VisitBookingViewSet,
    register_view, login_view, dashboard_stats, profile_view,
    health_check, public_document_detail, public_document_sign,
    public_document_download_signed, public_document_download_unsigned,
    upload_image,
    public_properties_list, public_property_detail, public_property_detail_by_slug, public_agent_properties,
    public_property_available_slots, public_book_visit, track_property_view,
    property_analytics_summary, property_analytics_detail,
    tenant_me, tenant_complete_profile, tenant_sign_document,
    tenant_upload_signed, tenant_documents, tenant_document_detail,
    tenant_download_signed, tenant_download_unsigned,
    tenant_email_signed, tenant_email_unsigned,
    tenant_agreement, tenant_payments, tenant_login,
    tenant_express_interest, tenant_change_password, tenant_maintenance,
    pending_verifications,
)

router = DefaultRouter()
router.register(r'properties', PropertyViewSet, basename='property')
router.register(r'units', UnitViewSet, basename='unit')
router.register(r'tenants', TenantViewSet, basename='tenant')
router.register(r'payments', PaymentViewSet, basename='payment')
router.register(r'agreement-templates', AgreementTemplateViewSet, basename='agreement-template')
router.register(r'maintenance', MaintenanceRequestViewSet, basename='maintenance')
router.register(r'notifications', NotificationViewSet, basename='notification')
router.register(r'availability', PropertyAvailabilityViewSet, basename='availability')
router.register(r'bookings', VisitBookingViewSet, basename='booking')

resend_invite_view = TenantViewSet.as_view({'post': 'resend_invite'})

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),
    path('api/tenants/<int:pk>/resend-invite/', resend_invite_view, name='tenant-resend-invite'),
    path('api/register/', register_view, name='register'),
    path('api/login/', login_view, name='login'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('api/health/', health_check, name='health-check'),
    path('api/dashboard/stats/', dashboard_stats, name='dashboard-stats'),
    path('api/profile/', profile_view, name='profile'),
    path('api/upload-image/', upload_image, name='upload-image'),
    path('api/public/document/<uuid:token>/', public_document_detail, name='public-document-detail'),
    path('api/public/document/<uuid:token>/sign/', public_document_sign, name='public-document-sign'),
    path('api/public/document/<uuid:token>/download-signed/', public_document_download_signed, name='public-document-download-signed'),
    path('api/public/document/<uuid:token>/download-unsigned/', public_document_download_unsigned, name='public-document-download-unsigned'),
    path('api/public/properties/', public_properties_list, name='public-properties-list'),
    path('api/public/properties/<int:pk>/', public_property_detail, name='public-property-detail'),
    path('api/public/properties/slug/<slug:slug>/', public_property_detail_by_slug, name='public-property-detail-by-slug'),
    path('api/public/properties/agent/<slug:slug>/', public_agent_properties, name='public-agent-properties'),
    path('api/public/properties/slug/<slug:slug>/slots/', public_property_available_slots, name='public-available-slots'),
    path('api/public/properties/slug/<slug:slug>/book/', public_book_visit, name='public-book-visit'),
    path('api/public/properties/slug/<slug:slug>/view/', track_property_view, name='track-property-view'),
    path('api/analytics/summary/', property_analytics_summary, name='analytics-summary'),
    path('api/analytics/property/<int:pk>/', property_analytics_detail, name='analytics-detail'),
    path('api/tenant/login/', tenant_login, name='tenant-login'),
    path('api/tenant/me/', tenant_me, name='tenant-me'),
    path('api/tenant/me/complete-profile/', tenant_complete_profile, name='tenant-complete-profile'),
    path('api/tenant/me/agreement/', tenant_agreement, name='tenant-agreement'),
    path('api/tenant/me/documents/', tenant_documents, name='tenant-documents'),
    path('api/tenant/me/documents/<int:doc_id>/', tenant_document_detail, name='tenant-document-detail'),
    path('api/tenant/me/documents/<int:doc_id>/sign/', tenant_sign_document, name='tenant-sign-document'),
    path('api/tenant/me/documents/<int:doc_id>/upload-signed/', tenant_upload_signed, name='tenant-upload-signed'),
    path('api/tenant/me/documents/<int:doc_id>/download-signed/', tenant_download_signed, name='tenant-download-signed'),
    path('api/tenant/me/documents/<int:doc_id>/download-unsigned/', tenant_download_unsigned, name='tenant-download-unsigned'),
    path('api/tenant/me/documents/<int:doc_id>/email-unsigned/', tenant_email_unsigned, name='tenant-email-unsigned'),
    path('api/tenant/me/documents/<int:doc_id>/email-signed/', tenant_email_signed, name='tenant-email-signed'),
    path('api/tenant/me/payments/', tenant_payments, name='tenant-payments'),
    path('api/tenant/me/express-interest/', tenant_express_interest, name='tenant-express-interest'),
    path('api/tenant/me/change-password/', tenant_change_password, name='tenant-change-password'),
    path('api/tenant/me/maintenance/', tenant_maintenance, name='tenant-maintenance'),
    path('api/pending-verifications/', pending_verifications, name='pending-verifications'),
]
