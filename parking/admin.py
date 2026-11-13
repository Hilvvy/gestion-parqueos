from django.contrib import admin

from .models import (
    AuditEvent,
    ClassSchedule,
    ParkingLot,
    ParkingPolicy,
    Reservation,
    SecurityAssignment,
    Vehicle,
)

admin.site.site_header = "Administración de parqueos"
admin.site.register(ParkingLot)
admin.site.register(ClassSchedule)
admin.site.register(SecurityAssignment)


class ReadOnlyAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Reservation)
class ReservationAdmin(ReadOnlyAdmin):
    list_display = ("plate", "user", "parking_lot", "starts_at", "status")
    list_filter = ("status", "parking_lot")
    search_fields = ("plate", "user__username")


@admin.register(Vehicle)
class VehicleAdmin(ReadOnlyAdmin):
    list_display = ("plate", "owner", "kind", "active")
    list_filter = ("active", "kind")
    search_fields = ("plate", "owner__username")


@admin.register(AuditEvent)
class AuditEventAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "action", "actor", "reservation", "vehicle")
    list_filter = ("action",)


@admin.register(ParkingPolicy)
class PolicyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not ParkingPolicy.objects.exists() and super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False
