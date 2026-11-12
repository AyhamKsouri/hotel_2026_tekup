from django.urls import path

from . import views as v

urlpatterns = [
    path('today/', v.menu_today, name='menu_today'),
    path('menus/', v.menu_list, name='menu_list'),
    path('menus/add/', v.menu_add, name='menu_add'),
    path('menus/<int:pk>/edit/', v.menu_edit, name='menu_edit'),
    path('menus/<int:pk>/delete/', v.menu_delete, name='menu_delete'),
    path('stock/', v.stock_list, name='stock_list'),
    path('stock/add/', v.stock_add, name='stock_add'),
    path('stock/<int:pk>/edit/', v.stock_edit, name='stock_edit'),
    path('stock/<int:pk>/delete/', v.stock_delete, name='stock_delete'),
    path('client/', v.client_menu, name='client_menu'),
]
