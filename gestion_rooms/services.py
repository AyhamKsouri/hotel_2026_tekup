"""Logique métier : cycle de vie d'une réservation et rappels de nettoyage."""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from account.models import ROLE_CLEANER, ROLE_RECEPTIONIST, Notification, User

from .models import CleaningTask, Invoice, Reservation, Room


def notify(users, message):
    Notification.objects.bulk_create([Notification(user=u, message=message) for u in users])


@transaction.atomic
def confirm_reservation(res):
    res.status = Reservation.CONFIRMED
    res.save(update_fields=['status'])
    Invoice.objects.get_or_create(reservation=res, defaults={'amount': res.total})
    notify([res.client], f'Votre réservation #{res.pk} (chambre {res.room.number}) est confirmée.')


@transaction.atomic
def check_in(res):
    res.status = Reservation.CHECKED_IN
    res.save(update_fields=['status'])
    Invoice.objects.get_or_create(reservation=res, defaults={'amount': res.total})
    Room.objects.filter(pk=res.room_id).update(status=Room.OCCUPIED)


_check_in = check_in


@transaction.atomic
def check_out(res):
    """Départ : la chambre passe « à nettoyer » et une tâche de nettoyage est créée."""
    res.status = Reservation.CHECKED_OUT
    res.save(update_fields=['status'])
    Room.objects.filter(pk=res.room_id).update(status=Room.TO_CLEAN)
    task = CleaningTask.objects.create(room=res.room, scheduled_for=timezone.now())
    notify(User.objects.filter(role=ROLE_CLEANER, is_active=True),
           f'Chambre {res.room.number} à nettoyer.')
    return task


@transaction.atomic
def cancel_reservation(res):
    was_in = res.status == Reservation.CHECKED_IN
    res.status = Reservation.CANCELLED
    res.save(update_fields=['status'])
    # une facture non payée n'a plus d'objet ; une facture payée est conservée (remboursement hors système)
    Invoice.objects.filter(reservation=res, status=Invoice.UNPAID).delete()
    if was_in:
        Room.objects.filter(pk=res.room_id).update(status=Room.AVAILABLE)
    notify([res.client], f'Votre réservation #{res.pk} a été annulée.')


@transaction.atomic
def mark_cleaned(task):
    task.status = CleaningTask.DONE
    task.done_at = timezone.now()
    task.save(update_fields=['status', 'done_at'])
    Room.objects.filter(pk=task.room_id, status=Room.TO_CLEAN).update(status=Room.AVAILABLE)
    # seuls les réceptionnistes de l'hôtel de cette chambre sont concernés
    notify(User.objects.filter(role=ROLE_RECEPTIONIST, is_active=True, hotel_id=task.room.hotel_id),
           f'Chambre {task.room.number} nettoyée : elle est de nouveau disponible.')


def schedule_cleaning(task):
    """À appeler après création d'une tâche planifiée : prévient l'agent (ou tous)."""
    targets = [task.assigned_to] if task.assigned_to_id else list(
        User.objects.filter(role=ROLE_CLEANER, is_active=True))
    notify(targets, f'Nettoyage prévu pour la chambre {task.room.number} '
                    f'à {timezone.localtime(task.scheduled_for):%d/%m %H:%M}.')


def notify_due_cleaning():
    """Crée la notification « il est l'heure de nettoyer » pour chaque tâche arrivée à échéance.
    Appelée par la commande `send_cleaning_reminders` et à chaque visite/poll d'un agent."""
    due = CleaningTask.objects.filter(
        status=CleaningTask.PENDING, reminded=False, scheduled_for__lte=timezone.now()
    ).select_related('room', 'assigned_to')
    count = 0
    for task in due:
        targets = [task.assigned_to] if task.assigned_to_id else list(
            User.objects.filter(role=ROLE_CLEANER, is_active=True))
        notify(targets, f'⏰ C\'est l\'heure de nettoyer la chambre {task.room.number} !')
        task.reminded = True
        task.save(update_fields=['reminded'])
        count += 1
    return count


# ---------------------------------------------------------------- réservations « réclamées » (réception)
def pending_claims(hotel_id):
    """Demandes de réservation en attente d'un hôtel, regroupées par demande client.

    Une demande (`Booking`) peut couvrir plusieurs chambres : la réception la traite d'un seul clic.
    Retourne une liste de dicts triée de la plus ancienne à la plus récente."""
    qs = (Reservation.objects.filter(status=Reservation.PENDING, room__hotel_id=hotel_id)
          .select_related('client', 'room', 'booking').order_by('created_at', 'pk'))
    groups = {}
    for res in qs:
        key = ('b', res.booking_id) if res.booking_id else ('r', res.pk)
        g = groups.setdefault(key, {'first': res, 'booking': res.booking, 'reservations': [],
                                    'total': Decimal(0)})
        g['reservations'].append(res)
        g['total'] += res.total
    return list(groups.values())


def _claim_group(res):
    """Toutes les réservations encore en attente de la même demande que `res`."""
    if res.booking_id:
        return list(Reservation.objects.select_for_update(of=('self',)).filter(
            booking_id=res.booking_id, status=Reservation.PENDING).select_related('room', 'room__hotel'))
    return [res] if res.status == Reservation.PENDING else []


def _claim_label(group):
    first = group[0]
    ref = f'#{first.booking_id}' if first.booking_id else f'#{first.pk}'
    hotel = f' à {first.room.hotel.name}' if first.room.hotel_id else ''
    rooms = ', '.join(r.room.number for r in group)
    return (f'Votre réservation {ref}{hotel} (chambre{"s" if len(group) > 1 else ""} {rooms}, '
            f'{first.check_in:%d/%m/%Y} → {first.check_out:%d/%m/%Y})')


@transaction.atomic
def confirm_claim(res):
    """Le réceptionniste confirme la demande : réservations confirmées + facture par chambre."""
    group = _claim_group(res)
    for r in group:
        r.status = Reservation.CONFIRMED
        r.save(update_fields=['status'])
        Invoice.objects.get_or_create(reservation=r, defaults={'amount': r.total})
    if group:
        notify([group[0].client], f'{_claim_label(group)} est confirmée.')
    return group


@transaction.atomic
def refuse_claim(res):
    """Le réceptionniste refuse la demande : les chambres redeviennent réservables."""
    group = _claim_group(res)
    for r in group:
        r.status = Reservation.REFUSED
        r.save(update_fields=['status'])
    if group:
        notify([group[0].client], f'{_claim_label(group)} a été refusée par la réception.')
    return group


# ---------------------------------------------------------------- réception : comptoir et modifications
@transaction.atomic
def create_walk_in(*, client, room, check_in, check_out, amount=None, check_in_now=False):
    """Réservation saisie au comptoir : confirmée tout de suite, facture émise, check-in optionnel.
    Lève ValidationError si la chambre est déjà prise sur ces dates."""
    Room.objects.select_for_update().filter(pk=room.pk).first()     # sérialise les réservations de la chambre
    res = Reservation(client=client, room=room, check_in=check_in, check_out=check_out,
                      status=Reservation.CONFIRMED, price_override=amount)
    res.full_clean()
    res.save()
    Invoice.objects.create(reservation=res, amount=res.total)
    if check_in_now:
        _check_in(res)        # alias : le paramètre « check_in » (une date) masque la fonction
    notify([client], f'Votre réservation #{res.pk} (chambre {room.number}, '
                     f'{check_in:%d/%m/%Y} → {check_out:%d/%m/%Y}) a été enregistrée par la réception.')
    return res


@transaction.atomic
def update_reservation(res, amount):
    """Enregistre une réservation modifiée par la réception et met la facture impayée au nouveau montant."""
    res.price_override = amount
    res.save()
    Invoice.objects.filter(reservation=res, status=Invoice.UNPAID).update(amount=res.total)
    if res.status == Reservation.CHECKED_IN:
        Room.objects.filter(pk=res.room_id).update(status=Room.OCCUPIED)
    notify([res.client], f'Votre réservation #{res.pk} a été modifiée par la réception : chambre {res.room.number}, '
                         f'{res.check_in:%d/%m/%Y} → {res.check_out:%d/%m/%Y}, {res.total} TND.')
    return res


@transaction.atomic
def pay_invoice(invoice, method):
    invoice.status, invoice.method = Invoice.PAID, method
    invoice.save()
    notify([invoice.reservation.client], f'Paiement reçu pour la facture #{invoice.pk} ({invoice.amount} TND).')
    return invoice
