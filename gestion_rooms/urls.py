from django.urls import path

from . import views as v

urlpatterns = [
    # admin
    path('admin/', v.room_list, name='room_list'),
    path('admin/add/', v.room_add, name='room_add'),
    path('admin/<int:pk>/edit/', v.room_edit, name='room_edit'),
    path('admin/<int:pk>/delete/', v.room_delete, name='room_delete'),
    # réceptionniste
    path('availability/', v.room_availability, name='room_availability'),
    path('<int:pk>/mark-available/', v.room_mark, {'status': 'available'}, name='room_mark_available'),
    path('<int:pk>/mark-occupied/', v.room_mark, {'status': 'occupied'}, name='room_mark_occupied'),
    path('<int:pk>/mark-maintenance/', v.room_mark, {'status': 'maintenance'}, name='room_mark_maintenance'),
    path('reservations/claimed/', v.claimed_list, name='claimed_list'),
    path('reservations/claimed/<int:pk>/confirm/', v.claimed_confirm, name='claimed_confirm'),
    path('reservations/claimed/<int:pk>/refuse/', v.claimed_refuse, name='claimed_refuse'),
    path('reservations/', v.reservation_list, name='reservation_list'),
    path('reservations/add/', v.reservation_add, name='reservation_add'),
    path('reservations/<int:pk>/edit/', v.reservation_edit, name='reservation_edit'),
    path('reservations/<int:pk>/delete/', v.reservation_delete, name='reservation_delete'),
    path('reservations/<int:pk>/confirm/', v.reservation_confirm, name='reservation_confirm'),
    path('reservations/<int:pk>/checkin/', v.reservation_checkin, name='reservation_checkin'),
    path('reservations/<int:pk>/checkout/', v.reservation_checkout, name='reservation_checkout'),
    path('reservations/<int:pk>/cancel/', v.reservation_cancel, name='reservation_cancel'),
    path('invoices/', v.invoice_list, name='invoice_list'),
    path('invoices/add/', v.invoice_add, name='invoice_add'),
    path('invoices/<int:pk>/edit/', v.invoice_edit, name='invoice_edit'),
    path('invoices/<int:pk>/delete/', v.invoice_delete, name='invoice_delete'),
    path('invoices/<int:pk>/pay/', v.invoice_pay, name='invoice_pay'),
    path('cleaning/', v.cleaning_list, name='cleaning_list'),
    path('cleaning/add/', v.cleaning_add, name='cleaning_add'),
    path('cleaning/<int:pk>/edit/', v.cleaning_edit, name='cleaning_edit'),
    path('cleaning/<int:pk>/delete/', v.cleaning_delete, name='cleaning_delete'),
    # agent de nettoyage
    path('cleaner/todo/', v.cleaner_todo, name='cleaner_todo'),
    path('cleaner/done/', v.cleaner_done, name='cleaner_done'),
    path('cleaner/<int:pk>/done/', v.cleaner_mark_done, name='cleaner_mark_done'),
    # client
    path('book/', v.client_book, name='client_book'),
    path('my-reservations/', v.client_reservations, name='client_reservations'),
    path('my-reservations/<int:pk>/cancel/', v.client_cancel, name='client_cancel'),
    path('my-invoices/', v.client_invoices, name='client_invoices'),
]
