from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Notification, User


@admin.register(User)
class HotelUserAdmin(UserAdmin):
    ordering = ('email',)
    list_display = ('email', 'cin', 'nom', 'prenom', 'role', 'hotel', 'is_active')
    list_filter = ('role', 'is_active')
    search_fields = ('email', 'cin', 'nom', 'prenom')
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Identité', {'fields': ('cin', 'nom', 'prenom', 'telephone', 'role', 'hotel')}),
        ('Droits', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
    )
    add_fieldsets = (
        (None, {'classes': ('wide',), 'fields': (
            'email', 'cin', 'nom', 'prenom', 'telephone', 'role', 'hotel', 'password1', 'password2')}),
    )


admin.site.register(Notification)
