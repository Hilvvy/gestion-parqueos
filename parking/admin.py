from django.contrib import admin

from .models import ClassSchedule, ParkingLot, Reservation

admin.site.register(ParkingLot)
admin.site.register(ClassSchedule)


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ("plate", "user", "parking_lot", "starts_at", "status")
    list_filter = ("status", "parking_lot")
    search_fields = ("plate", "user__username")
    readonly_fields = tuple(field.name for field in Reservation._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
