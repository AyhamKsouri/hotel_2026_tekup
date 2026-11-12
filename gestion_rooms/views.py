from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from account import crud
from account.decorators import role_required
from account.models import ROLE_ADMIN, ROLE_CLEANER, ROLE_CLIENT, ROLE_RECEPTIONIST

from . import services
from .forms import CleaningTaskForm, InvoiceForm, ReservationForm, RoomForm
from .models import CleaningTask, Invoice, Reservation, Room

STAFF_FRONT = (ROLE_RECEPTIONIST, ROLE_ADMIN)


def _money(v):
    return f'{v:.2f} TND'


def _own_hotel(qs, user, field):
    """Un réceptionniste ne voit que les données de SON hôtel (`field` = chemin vers l'hôtel).
    Sans hôtel assigné il ne voit que les données historiques (sans hôtel). L'admin voit tout."""
    if user.role == ROLE_RECEPTIONIST:
        return qs.filter(**{f'{field}_id': user.hotel_id})
    return qs


def _reservations(user):
    return _own_hotel(Reservation.objects.select_related('client', 'room'), user, 'room__hotel')


def _invoices(user):
    return _own_hotel(Invoice.objects.select_related('reservation__client', 'reservation__room'),
                      user, 'reservation__room__hotel')


def _rooms(user):
    return _own_hotel(Room.objects.all(), user, 'hotel')


# ================================================================ ADMIN : chambres
def _admin_rooms(user):
    """Chambres des hôtels de cet admin + chambres historiques (sans hôtel)."""
    return Room.objects.filter(Q(hotel__owner=user) | Q(hotel__isnull=True)).select_related('hotel')


@role_required(ROLE_ADMIN)
def room_list(request):
    qs = _admin_rooms(request.user)
    cat = request.GET.get('category')
    if cat:
        qs = qs.filter(category=cat)
    return crud.list_page(
        request, title='Gestion des chambres', queryset=qs, base_name='room',
        columns=[('Hôtel', lambda r: r.hotel.name if r.hotel_id else '—'),
                 ('N°', lambda r: r.number), ('Catégorie', lambda r: r.get_category_display()),
                 ('Capacité', lambda r: r.get_capacity_display()),
                 ('Prix / nuit', lambda r: _money(r.price_per_night)),
                 ('Statut', lambda r: r.get_status_display())],
        filters={'name': 'category', 'value': cat, 'choices': Room.CATEGORY_CHOICES})


@role_required(ROLE_ADMIN)
def room_add(request):
    return crud.form_page(request, form_class=RoomForm, title='Nouvelle chambre', success_url='room_list',
                          form_kwargs={'user': request.user})


@role_required(ROLE_ADMIN)
def room_edit(request, pk):
    return crud.form_page(request, form_class=RoomForm, title='Modifier la chambre',
                          instance=get_object_or_404(_admin_rooms(request.user), pk=pk),
                          form_kwargs={'user': request.user}, success_url='room_list')


@role_required(ROLE_ADMIN)
def room_delete(request, pk):
    from django.db.models import ProtectedError
    try:
        return crud.delete_page(request, model=Room, pk=pk, success_url='room_list', label=str,
                                queryset=_admin_rooms(request.user))
    except ProtectedError:
        messages.error(request, 'Impossible : cette chambre a des réservations.')
        return redirect('room_list')


# ================================================================ RÉCEPTIONNISTE : chambres disponibles
@role_required(*STAFF_FRONT)
def room_availability(request):
    qs = _rooms(request.user)
    st = request.GET.get('status', Room.AVAILABLE if 'status' not in request.GET else '')
    if st:
        qs = qs.filter(status=st)
    return crud.list_page(
        request, title='Chambres disponibles', queryset=qs, base_name='room',
        add=False, edit=False, delete=False,
        columns=[('N°', lambda r: r.number), ('Catégorie', lambda r: r.get_category_display()),
                 ('Capacité', lambda r: r.get_capacity_display()),
                 ('Prix / nuit', lambda r: _money(r.price_per_night)),
                 ('Statut', lambda r: r.get_status_display())],
        extra_actions=[
            ('Disponible', 'room_mark_available', lambda r: r.status != Room.AVAILABLE),
            ('Occupée', 'room_mark_occupied', lambda r: r.status != Room.OCCUPIED),
            ('Maintenance', 'room_mark_maintenance', lambda r: r.status != Room.MAINTENANCE),
        ],
        filters={'name': 'status', 'value': st, 'choices': Room.STATUS_CHOICES})


@role_required(*STAFF_FRONT)
@require_POST
def room_mark(request, pk, status):
    room = get_object_or_404(_rooms(request.user), pk=pk)
    room.status = status
    room.save(update_fields=['status'])
    messages.success(request, f'Chambre {room.number} : {room.get_status_display()}.')
    return redirect(request.META.get('HTTP_REFERER') or 'room_availability')


# ================================================================ RÉCEPTIONNISTE : réservations
@role_required(*STAFF_FRONT)
def reservation_list(request):
    qs = _reservations(request.user)
    st = request.GET.get('status')
    if st:
        qs = qs.filter(status=st)
    return crud.list_page(
        request, title='Gestion des réservations', queryset=qs, base_name='reservation',
        columns=[('#', lambda r: r.pk), ('Client', lambda r: r.client.full_name),
                 ('Chambre', lambda r: r.room.number),
                 ('Arrivée', lambda r: r.check_in.strftime('%d/%m/%Y')),
                 ('Départ', lambda r: r.check_out.strftime('%d/%m/%Y')),
                 ('Total', lambda r: _money(r.total)), ('Statut', lambda r: r.get_status_display())],
        extra_actions=[
            ('Confirmer', 'reservation_confirm', lambda r: r.status == Reservation.PENDING),
            ('Check-in', 'reservation_checkin', lambda r: r.status == Reservation.CONFIRMED),
            ('Check-out', 'reservation_checkout', lambda r: r.status == Reservation.CHECKED_IN),
            ('Annuler', 'reservation_cancel',
             lambda r: r.status in (Reservation.PENDING, Reservation.CONFIRMED)),
        ],
        filters={'name': 'status', 'value': st, 'choices': Reservation.STATUS_CHOICES})


@role_required(*STAFF_FRONT)
def reservation_add(request):
    return crud.form_page(request, form_class=ReservationForm, title='Nouvelle réservation',
                          form_kwargs={'user': request.user}, success_url='reservation_list')


@role_required(*STAFF_FRONT)
def reservation_edit(request, pk):
    return crud.form_page(request, form_class=ReservationForm, title='Modifier la réservation',
                          instance=get_object_or_404(_reservations(request.user), pk=pk),
                          form_kwargs={'user': request.user}, success_url='reservation_list')


@role_required(*STAFF_FRONT)
def reservation_delete(request, pk):
    return crud.delete_page(request, model=Reservation, pk=pk, success_url='reservation_list',
                            queryset=_reservations(request.user))


def _transition(request, pk, allowed, action, ok_msg):
    res = get_object_or_404(_reservations(request.user), pk=pk)
    if res.status not in allowed:
        messages.error(request, 'Action impossible dans l\'état actuel de la réservation.')
    else:
        action(res)
        messages.success(request, ok_msg)
    return redirect('reservation_list')


@role_required(*STAFF_FRONT)
@require_POST
def reservation_confirm(request, pk):
    return _transition(request, pk, [Reservation.PENDING], services.confirm_reservation,
                       'Réservation confirmée, facture générée.')


@role_required(*STAFF_FRONT)
@require_POST
def reservation_checkin(request, pk):
    return _transition(request, pk, [Reservation.CONFIRMED], services.check_in, 'Check-in effectué.')


@role_required(*STAFF_FRONT)
@require_POST
def reservation_checkout(request, pk):
    return _transition(request, pk, [Reservation.CHECKED_IN], services.check_out,
                       'Check-out effectué : chambre envoyée au nettoyage.')


@role_required(*STAFF_FRONT)
@require_POST
def reservation_cancel(request, pk):
    return _transition(request, pk, [Reservation.PENDING, Reservation.CONFIRMED],
                       services.cancel_reservation, 'Réservation annulée.')


# ================================================================ RÉCEPTIONNISTE : réservations réclamées
@role_required(ROLE_RECEPTIONIST)
def claimed_list(request):
    """Demandes des clients de MON hôtel, en attente : le réceptionniste confirme ou refuse."""
    hotel = request.user.hotel
    return render(request, 'reception/claimed.html', {
        'hotel': hotel, 'claims': services.pending_claims(hotel.pk) if hotel else []})


def _decide(request, pk, action, ok_msg):
    if not request.user.hotel_id:
        raise PermissionDenied
    res = get_object_or_404(_reservations(request.user), pk=pk)
    if not action(res):
        messages.error(request, 'Cette réservation a déjà été traitée.')
    else:
        messages.success(request, ok_msg)
    return redirect('claimed_list')


@role_required(ROLE_RECEPTIONIST)
@require_POST
def claimed_confirm(request, pk):
    return _decide(request, pk, services.confirm_claim, 'Réservation confirmée : le client est prévenu '
                                                       'et la facture est générée.')


@role_required(ROLE_RECEPTIONIST)
@require_POST
def claimed_refuse(request, pk):
    return _decide(request, pk, services.refuse_claim, 'Réservation refusée : le client est prévenu '
                                                      'et les chambres sont de nouveau libres.')


# ================================================================ RÉCEPTIONNISTE : factures
@role_required(*STAFF_FRONT)
def invoice_list(request):
    qs = _invoices(request.user)
    st = request.GET.get('status')
    if st:
        qs = qs.filter(status=st)
    return crud.list_page(
        request, title='Factures de paiement', queryset=qs, base_name='invoice',
        columns=[('#', lambda i: i.pk), ('Client', lambda i: i.reservation.client.full_name),
                 ('Réservation', lambda i: f'#{i.reservation_id} – ch. {i.reservation.room.number}'),
                 ('Montant', lambda i: _money(i.amount)), ('Statut', lambda i: i.get_status_display()),
                 ('Paiement', lambda i: i.get_method_display() or '—'),
                 ('Émise le', lambda i: timezone.localtime(i.issued_at).strftime('%d/%m/%Y'))],
        extra_actions=[('Marquer payée (espèces)', 'invoice_pay', lambda i: i.status == Invoice.UNPAID)],
        filters={'name': 'status', 'value': st, 'choices': Invoice.STATUS_CHOICES})


@role_required(*STAFF_FRONT)
def invoice_add(request):
    return crud.form_page(request, form_class=InvoiceForm, title='Nouvelle facture',
                          form_kwargs={'user': request.user}, success_url='invoice_list')


@role_required(*STAFF_FRONT)
def invoice_edit(request, pk):
    return crud.form_page(request, form_class=InvoiceForm, title='Modifier la facture',
                          instance=get_object_or_404(_invoices(request.user), pk=pk),
                          form_kwargs={'user': request.user}, success_url='invoice_list')


@role_required(*STAFF_FRONT)
def invoice_delete(request, pk):
    return crud.delete_page(request, model=Invoice, pk=pk, success_url='invoice_list',
                            queryset=_invoices(request.user))


@role_required(*STAFF_FRONT)
@require_POST
def invoice_pay(request, pk):
    inv = get_object_or_404(_invoices(request.user), pk=pk)
    inv.status, inv.method = Invoice.PAID, inv.method or 'cash'
    inv.save()
    messages.success(request, 'Facture marquée comme payée.')
    return redirect('invoice_list')


# ================================================================ RÉCEPTIONNISTE : planifier un nettoyage
@role_required(*STAFF_FRONT)
def cleaning_list(request):
    return crud.list_page(
        request, title='Planification des nettoyages',
        queryset=CleaningTask.objects.select_related('room', 'assigned_to'), base_name='cleaning',
        columns=[('Chambre', lambda t: t.room.number),
                 ('Agent', lambda t: t.assigned_to.full_name if t.assigned_to else 'Tous'),
                 ('Heure prévue', lambda t: timezone.localtime(t.scheduled_for).strftime('%d/%m %H:%M')),
                 ('Statut', lambda t: t.get_status_display()), ('Note', lambda t: t.note or '—')])


@role_required(*STAFF_FRONT)
def cleaning_add(request):
    def after_save(task):
        services.schedule_cleaning(task)   # prévient l'agent de la planification
        services.notify_due_cleaning()     # et, si l'heure est déjà passée, du rappel immédiat

    return crud.form_page(request, form_class=CleaningTaskForm, title='Planifier un nettoyage',
                          success_url='cleaning_list', after_save=after_save)


@role_required(*STAFF_FRONT)
def cleaning_edit(request, pk):
    return crud.form_page(request, form_class=CleaningTaskForm, title='Modifier le nettoyage',
                          instance=get_object_or_404(CleaningTask, pk=pk), success_url='cleaning_list')


@role_required(*STAFF_FRONT)
def cleaning_delete(request, pk):
    return crud.delete_page(request, model=CleaningTask, pk=pk, success_url='cleaning_list')


# ================================================================ AGENT DE NETTOYAGE
def _task_columns():
    return [('Chambre', lambda t: t.room.number),
            ('Catégorie', lambda t: t.room.get_category_display()),
            ('Heure prévue', lambda t: timezone.localtime(t.scheduled_for).strftime('%d/%m %H:%M')),
            ('Statut', lambda t: ('⏰ En retard' if t.status == CleaningTask.PENDING
                                  and t.scheduled_for <= timezone.now() else t.get_status_display())),
            ('Note', lambda t: t.note or '—')]


@role_required(ROLE_CLEANER)
def cleaner_todo(request):
    services.notify_due_cleaning()
    qs = CleaningTask.objects.for_cleaner(request.user).filter(
        status=CleaningTask.PENDING).select_related('room')
    return crud.list_page(
        request, title='Chambres à nettoyer', queryset=qs, columns=_task_columns(),
        extra_actions=[('Marquer comme nettoyée', 'cleaner_mark_done', None)])


@role_required(ROLE_CLEANER)
def cleaner_done(request):
    qs = CleaningTask.objects.for_cleaner(request.user).filter(
        status=CleaningTask.DONE).select_related('room').order_by('-done_at')
    cols = _task_columns()[:2] + [
        ('Nettoyée le', lambda t: timezone.localtime(t.done_at).strftime('%d/%m %H:%M'))]
    return crud.list_page(request, title='Chambres déjà nettoyées', queryset=qs, columns=cols)


@role_required(ROLE_CLEANER)
@require_POST
def cleaner_mark_done(request, pk):
    task = get_object_or_404(CleaningTask.objects.for_cleaner(request.user), pk=pk)
    if task.status == CleaningTask.PENDING:
        services.mark_cleaned(task)
        messages.success(request, f'Chambre {task.room.number} marquée comme nettoyée.')
    return redirect('cleaner_todo')


# ================================================================ CLIENT
@role_required(ROLE_CLIENT)
def client_book(request):
    return crud.form_page(
        request, form_class=ReservationForm, title='Réserver une chambre',
        form_kwargs={'user': request.user}, success_url='client_reservations',
        success_message='Réservation envoyée : la réception va la confirmer.')


@role_required(ROLE_CLIENT)
def client_reservations(request):
    qs = Reservation.objects.filter(client=request.user).select_related('room')
    return crud.list_page(
        request, title='Mes réservations', queryset=qs, add=False, edit=False, delete=False,
        columns=[('#', lambda r: r.pk), ('Chambre', lambda r: str(r.room)),
                 ('Arrivée', lambda r: r.check_in.strftime('%d/%m/%Y')),
                 ('Départ', lambda r: r.check_out.strftime('%d/%m/%Y')),
                 ('Total', lambda r: _money(r.total)), ('Statut', lambda r: r.get_status_display())],
        extra_actions=[('Annuler', 'client_cancel',
                        lambda r: r.status in (Reservation.PENDING, Reservation.CONFIRMED))])


@role_required(ROLE_CLIENT)
@require_POST
def client_cancel(request, pk):
    res = get_object_or_404(Reservation, pk=pk, client=request.user)
    if res.status in (Reservation.PENDING, Reservation.CONFIRMED):
        services.cancel_reservation(res)
        messages.success(request, 'Réservation annulée.')
    return redirect('client_reservations')


@role_required(ROLE_CLIENT)
def client_invoices(request):
    qs = Invoice.objects.filter(reservation__client=request.user).select_related('reservation__room')
    return crud.list_page(
        request, title='Mes factures', queryset=qs, add=False, edit=False, delete=False,
        columns=[('#', lambda i: i.pk), ('Réservation', lambda i: f'#{i.reservation_id} – ch. {i.reservation.room.number}'),
                 ('Montant', lambda i: _money(i.amount)), ('Statut', lambda i: i.get_status_display()),
                 ('Paiement', lambda i: i.get_method_display() or '—')])
