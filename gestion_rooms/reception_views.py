"""Espace réceptionniste : journée, calendrier, réservation au comptoir, modification,
fiches clients et facture imprimable. Un réceptionniste ne voit QUE son hôtel."""
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Max, Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from account import crud
from account.models import ROLE_ADMIN, ROLE_CLIENT, ROLE_RECEPTIONIST

from . import services
from .models import Invoice, Reservation, Room
from .reception_forms import ClientProfileForm, ReservationEditForm, WalkInForm
from .views import _invoices, _reservations, _rooms, front_desk, safe_next

User = get_user_model()
EDITABLE = (Reservation.PENDING, Reservation.CONFIRMED, Reservation.CHECKED_IN)
CALENDAR_DAYS = 14

# Pages réservées au réceptionniste (elles reposent sur SON hôtel)
reception_only = front_desk(roles=(ROLE_RECEPTIONIST,))


# ================================================================ journée
@reception_only
def reception_today(request):
    """Arrivées attendues, départs prévus et clients présents, avec check-in / check-out en un clic."""
    today = timezone.localdate()
    qs = _reservations(request.user).select_related('client', 'room', 'invoice').order_by('room__number')
    return render(request, 'reception/today.html', {
        'today': today,
        'arrivals': qs.filter(status=Reservation.CONFIRMED, check_in__lte=today),
        'departures': qs.filter(status=Reservation.CHECKED_IN, check_out__lte=today),
        'in_house': qs.filter(status=Reservation.CHECKED_IN, check_out__gt=today),
        'pending': qs.filter(status=Reservation.PENDING).count(),
    })


# ================================================================ calendrier de disponibilité
def _parse_start(raw, today):
    try:
        return date.fromisoformat(raw) if raw else today
    except ValueError:
        return today


@reception_only
def reception_calendar(request):
    """Grille chambre × jour sur 14 jours : libre, réclamée, confirmée, séjour en cours."""
    today = timezone.localdate()
    start = _parse_start(request.GET.get('start'), today)
    days = [start + timedelta(days=i) for i in range(CALENDAR_DAYS)]
    end = days[-1] + timedelta(days=1)
    cat = request.GET.get('category') or ''

    rooms = _rooms(request.user).order_by('number')
    if cat:
        rooms = rooms.filter(category=cat)
    rooms = list(rooms)
    stays = (_reservations(request.user).active()
             .filter(room__in=rooms, check_in__lt=end, check_out__gt=start).select_related('client'))
    by_room = {}
    for r in stays:
        by_room.setdefault(r.room_id, []).append(r)

    grid, free_per_day = [], [0] * len(days)
    for room in rooms:
        cells = []
        for i, d in enumerate(days):
            res = next((r for r in by_room.get(room.pk, []) if r.check_in <= d < r.check_out), None)
            cells.append({'day': d, 'res': res, 'start': bool(res and (res.check_in == d or d == start))})
            if res is None and room.status != Room.MAINTENANCE:
                free_per_day[i] += 1
        grid.append({'room': room, 'cells': cells})

    return render(request, 'reception/calendar.html', {
        'days': days, 'grid': grid, 'free_per_day': free_per_day, 'today': today, 'start': start,
        'prev': start - timedelta(days=7), 'next': start + timedelta(days=7),
        'category': cat, 'categories': Room.CATEGORY_CHOICES,
    })


# ================================================================ réservation au comptoir / modification
@front_desk
def reservation_add(request):
    form = WalkInForm(request.POST or None, user=request.user,
                      initial={'check_in': request.GET.get('check_in') or timezone.localdate(),
                               'room': request.GET.get('room')})
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        try:
            with transaction.atomic():      # nouveau client + réservation : tout ou rien
                res = services.create_walk_in(
                    client=form.get_client(), room=d['room'], check_in=d['check_in'], check_out=d['check_out'],
                    amount=d.get('amount'), check_in_now=d.get('check_in_now'))
        except ValidationError as e:
            form.add_error(None, e.messages[0])
        else:
            extra = ' Check-in effectué.' if d.get('check_in_now') else ''
            messages.success(request, f'Réservation #{res.pk} confirmée pour {res.client.full_name} '
                                      f'(chambre {res.room.number}, {res.total} TND). Facture émise.{extra}')
            return redirect('reservation_list')
    return render(request, 'reception/walkin.html', {
        'form': crud.bootstrapify(form), 'title': 'Réservation au comptoir',
        'back_url': reverse('reservation_list')})


@front_desk
def reservation_edit(request, pk):
    res = get_object_or_404(_reservations(request.user), pk=pk)
    if res.status not in EDITABLE:
        messages.error(request, f'Une réservation « {res.get_status_display()} » ne peut plus être modifiée.')
        return redirect('reservation_list')
    form = ReservationEditForm(request.POST or None, instance=res, user=request.user)
    if request.method == 'POST' and form.is_valid():
        amount = res.total if form.paid else form.cleaned_data['amount']
        services.update_reservation(form.save(commit=False), amount)
        messages.success(request, f'Réservation #{res.pk} modifiée.')
        return redirect(safe_next(request, reverse('reservation_list')))
    return render(request, 'reception/reservation_edit.html', {
        'form': crud.bootstrapify(form), 'res': res, 'title': 'Modifier la réservation',
        'back_url': reverse('reservation_list')})


# ================================================================ fiches clients
def _hotel_clients(user):
    """Clients ayant au moins une réservation dans l'hôtel du réceptionniste."""
    stays = Q(reservations__room__hotel_id=user.hotel_id)
    return (User.objects.filter(stays, role=ROLE_CLIENT)
            .annotate(n_stays=Count('reservations', filter=stays, distinct=True),
                      last_stay=Max('reservations__check_in', filter=stays))
            .order_by('nom', 'prenom'))


def _hotel_client(user, pk):
    client = _hotel_clients(user).filter(pk=pk).first()
    if client is None:
        raise Http404
    return client


@reception_only
def reception_clients(request):
    q = (request.GET.get('q') or '').strip()
    qs = _hotel_clients(request.user)
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(prenom__icontains=q) | Q(cin__icontains=q)
                       | Q(email__icontains=q) | Q(telephone__icontains=q))
    return crud.list_page(
        request, title='Clients', subtitle=f'Clients ayant séjourné ou réservé à {request.user.hotel.name}',
        queryset=qs, search=q, add=False, edit=False, delete=False,
        columns=[('Nom', lambda u: u.full_name), ('CIN', lambda u: u.cin), ('Téléphone', lambda u: u.telephone),
                 ('E-mail', lambda u: u.email), ('Réservations', lambda u: u.n_stays),
                 ('Dernière arrivée', lambda u: u.last_stay.strftime('%d/%m/%Y') if u.last_stay else '—')],
        links=[('Fiche', 'reception_client_detail', None)])


@reception_only
def reception_client_detail(request, pk):
    client = _hotel_client(request.user, pk)
    stays = (_reservations(request.user).filter(client=client)
             .select_related('room', 'invoice', 'booking').order_by('-check_in'))
    invoices = _invoices(request.user).filter(reservation__client=client)
    totals = invoices.aggregate(paid=Sum('amount', filter=Q(status=Invoice.PAID)),
                                due=Sum('amount', filter=Q(status=Invoice.UNPAID)))
    today = timezone.localdate()
    return render(request, 'reception/client_detail.html', {
        'client': client, 'stays': stays, 'paid': totals['paid'] or 0, 'due': totals['due'] or 0,
        'editable': EDITABLE,
        'upcoming': stays.filter(check_in__gte=today).exclude(
            status__in=[Reservation.CANCELLED, Reservation.REFUSED]).count(),
        'nights': sum(r.nights for r in stays if r.status in (Reservation.CHECKED_IN, Reservation.CHECKED_OUT)),
    })


@reception_only
def reception_client_edit(request, pk):
    client = _hotel_client(request.user, pk)
    form = ClientProfileForm(request.POST or None, instance=client)
    back = reverse('reception_client_detail', args=[pk])
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Profil de {client.full_name} mis à jour.')
        return redirect(back)
    return render(request, 'crud/form.html', {
        'form': crud.bootstrapify(form), 'title': f'Modifier le profil — {client.full_name}', 'back_url': back})


# ================================================================ facture imprimable (regroupée par demande)
@front_desk(roles=(ROLE_RECEPTIONIST, ROLE_ADMIN, ROLE_CLIENT))
def invoice_print(request, pk):
    """Une facture regroupe toutes les chambres d'une même demande de réservation."""
    user = request.user
    if user.role == ROLE_CLIENT:
        scope = Invoice.objects.filter(reservation__client=user)
    else:
        scope = _invoices(user)
    inv = get_object_or_404(scope.select_related('reservation__booking', 'reservation__room__hotel'), pk=pk)
    res = inv.reservation
    if res.booking_id:
        lines = scope.filter(reservation__booking_id=res.booking_id)
    else:
        lines = scope.filter(pk=inv.pk)
    lines = list(lines.select_related('reservation__room').order_by('reservation__room__number'))
    if not lines:
        raise PermissionDenied
    hotel = res.room.hotel
    back = reverse('client_invoices') if user.role == ROLE_CLIENT else reverse('invoice_list')
    return render(request, 'reception/invoice_print.html', {
        'inv': inv, 'res': res, 'booking': res.booking, 'hotel': hotel, 'client': res.client, 'lines': lines,
        'total': sum(i.amount for i in lines),
        'paid': sum(i.amount for i in lines if i.status == Invoice.PAID),
        'due': sum(i.amount for i in lines if i.status == Invoice.UNPAID),
        'all_paid': all(i.status == Invoice.PAID for i in lines),
        'back_url': back, 'now': timezone.now(),
    })
