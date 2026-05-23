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
    register_view, login_view, dashboard_stats, profile_view,
    health_check, public_document_detail, public_document_sign,
    upload_image,
)

router = DefaultRouter()
router.register(r'properties', PropertyViewSet, basename='property')
router.register(r'units', UnitViewSet, basename='unit')
router.register(r'tenants', TenantViewSet, basename='tenant')
router.register(r'payments', PaymentViewSet, basename='payment')
router.register(r'maintenance', MaintenanceRequestViewSet, basename='maintenance')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),
    path('api/register/', register_view, name='register'),
    path('api/login/', login_view, name='login'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('api/health/', health_check, name='health-check'),
    path('api/dashboard/stats/', dashboard_stats, name='dashboard-stats'),
    path('api/profile/', profile_view, name='profile'),
    path('api/public/document/<uuid:token>/', public_document_detail, name='public-document-detail'),
    path('api/public/document/<uuid:token>/sign/', public_document_sign, name='public-document-sign'),
    path('api/upload-image/', upload_image, name='upload-image'),
]
