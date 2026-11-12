from django.urls import path

from . import client_views as c
from . import hotel_views as v

urlpatterns = [
    # espace client
    path('browse/', c.client_hotels, name='client_hotels'),
    path('browse/<int:pk>/', c.client_hotel_detail, name='client_hotel_detail'),
    path('browse/<int:pk>/book/', c.client_hotel_book, name='client_hotel_book'),
    # espace admin
    path('', v.hotel_list, name='hotel_list'),
    path('new/', v.hotel_new, name='hotel_new'),
    path('<int:pk>/', v.hotel_detail, name='hotel_detail'),
    path('<int:pk>/step/<int:step>/', v.hotel_step, name='hotel_step'),
    path('<int:pk>/images/add/', v.hotel_image_add, name='hotel_image_add'),
    path('<int:pk>/images/<int:image_pk>/delete/', v.hotel_image_delete, name='hotel_image_delete'),
    path('<int:pk>/delete/', v.hotel_delete, name='hotel_delete'),
]
