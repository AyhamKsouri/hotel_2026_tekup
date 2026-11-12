"""Espace client : parcourir les hôtels créés par les admins, voir le détail, réserver."""
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from account.decorators import role_required
from account.models import ROLE_CLIENT
from gestion_rooms.models import Booking

from .booking import BookingForm, create_booking
from .models import Hotel

FREE_UNDER_AGE = 11


def _published():
    return Hotel.objects.filter(completed_step__gte=3).prefetch_related('gallery', 'services', 'plans')


@role_required(ROLE_CLIENT)
def client_hotels(request):
    mode = 'list' if request.GET.get('view') == 'list' else 'cards'
    hotels = list(_published())
    for h in hotels:
        h.slide_list = h.slides()
        h.cid = f'hc{h.pk}'
        h.min_price = min((t[3] for t in h.room_types()), default=None)
    return render(request, 'hotels/client_list.html', {'hotels': hotels, 'mode': mode})


@role_required(ROLE_CLIENT)
def client_hotel_detail(request, pk):
    hotel = get_object_or_404(_published(), pk=pk)
    return render(request, 'hotels/client_detail.html', {
        'hotel': hotel, 'slides': hotel.slides(), 'types': hotel.room_types(),
        'type_images': hotel.type_images()})


@role_required(ROLE_CLIENT)
def client_hotel_book(request, pk):
    hotel = get_object_or_404(_published(), pk=pk)
    posting = request.method == 'POST'
    form = BookingForm(request.POST if posting else None, hotel=hotel,
                       initial={'full_name': request.user.full_name, 'persons': 2, 'rooms_count': 1,
                                'booking_type': Booking.COUPLE})
    if posting and form.is_valid():
        try:
            booking = create_booking(hotel, request.user, form)
        except ValidationError as e:
            form.add_error(None, e.messages[0])
        else:
            messages.success(request, f'Réservation envoyée à {hotel.name} — total {booking.total} TND. '
                                      f'La réception va la confirmer.')
            return redirect('client_reservations')

    types = []
    for key, label, count, price, cap in hotel.room_types():
        img = hotel.type_images()[key]
        types.append({'key': key, 'label': label, 'count': count, 'price': float(price),
                      'image': img.url if img else ''})
    data = {
        'types': types, 'freeAge': FREE_UNDER_AGE,
        'services': [{'id': s.pk, 'name': s.name, 'price': float(s.price), 'billing': s.billing}
                     for s in form.hotel_services],
        'initial': {'rooms': request.POST.getlist('room_type') if posting else [],
                    'ages': request.POST.getlist('child_age') if posting else [],
                    'services': request.POST.getlist('services') if posting else []},
    }
    return render(request, 'hotels/client_book.html', {
        'hotel': hotel, 'form': form, 'data': data, 'services': form.hotel_services,
        'checked': set(request.POST.getlist('services')) if posting else set(), 'types': types})
