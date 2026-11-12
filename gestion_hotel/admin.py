from django.contrib import admin

from .models import BookingPlan, Event, Hotel, HotelImage, HotelService

admin.site.register(Event)


class ServiceInline(admin.TabularInline):
    model = HotelService
    extra = 0


class PlanInline(admin.TabularInline):
    model = BookingPlan
    extra = 0


class ImageInline(admin.TabularInline):
    model = HotelImage
    extra = 0


@admin.register(Hotel)
class HotelAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'city', 'stars', 'completed_step')
    inlines = [ServiceInline, PlanInline, ImageInline]
