from django.contrib import admin

from .models import CleaningTask, Invoice, Reservation, Room

admin.site.register([Room, Reservation, Invoice, CleaningTask])
