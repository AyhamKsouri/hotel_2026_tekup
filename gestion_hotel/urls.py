from django.urls import path

from . import views as v

urlpatterns = [
    path('', v.event_list, name='event_list'),
    path('add/', v.event_add, name='event_add'),
    path('<int:pk>/edit/', v.event_edit, name='event_edit'),
    path('<int:pk>/delete/', v.event_delete, name='event_delete'),
    path('upcoming/', v.client_events, name='client_events'),
]
