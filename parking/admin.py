from django.contrib import admin

from .models import (
    AuditEvent,
    ClassSchedule,
    OfflineMovement,
    ParkingLot,
    ParkingPolicy,
    Reservation,
    SecurityAssignment,
    Subject,
    UserProfile,
    Vehicle,
)

admin.site.site_header = "Administración de parqueos"
admin.site.register(ClassSchedule)
admin.site.register(SecurityAssignment)
admin.site.register(UserProfile)


class ReadOnlyAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ParkingLot)
class ParkingLotAdmin(ReadOnlyAdmin):
    list_display = ("name", "capacity", "active")


@admin.register(Subject)
class SubjectAdmin(ReadOnlyAdmin):
    list_display = ("name", "user", "weekday", "start_time", "end_time", "active")


@admin.register(Reservation)
class ReservationAdmin(ReadOnlyAdmin):
    list_display = ("plate", "user", "parking_lot", "starts_at", "status")
    list_filter = ("status", "parking_lot", "kind")
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


@admin.register(OfflineMovement)
class OfflineMovementAdmin(ReadOnlyAdmin):
    list_display = (
        "id",
        "officer",
        "reservation",
        "action",
        "occurred_at",
        "received_at",
        "accepted",
        "error",
    )
    list_filter = ("accepted", "action")


@admin.register(ParkingPolicy)
class PolicyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not ParkingPolicy.objects.exists() and super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False
