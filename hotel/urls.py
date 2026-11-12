from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('', include('account.urls')),
    path('rooms/', include('gestion_rooms.urls')),
    path('events/', include('gestion_hotel.urls')),
    path('hotels/', include('gestion_hotel.hotel_urls')),
    path('repas/', include('gestion_repas.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
