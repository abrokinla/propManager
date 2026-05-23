from django.contrib import admin
from .models import UserProfile, Property, Unit, Tenant, Payment, MaintenanceRequest, TenancyDocument, Reminder, QuitNotice

admin.site.register(UserProfile)
admin.site.register(Property)
admin.site.register(Unit)
admin.site.register(Tenant)
admin.site.register(Payment)
admin.site.register(MaintenanceRequest)
admin.site.register(TenancyDocument)
admin.site.register(Reminder)
admin.site.register(QuitNotice)
