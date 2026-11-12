import secrets
import time

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import send_mail
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import crud
from .decorators import role_required
from .forms import (LoginForm, ResetStep1Form, ResetStep2Form, ResetStep3Form,
                    SignupForm, UserAdminForm)
from .spaces import SPACES
from .models import (ROLE_ADMIN, ROLE_CHEF, ROLE_CLEANER, ROLE_CLIENT,
                     ROLE_RECEPTIONIST, Notification)

User = get_user_model()
RESET_KEY = 'pwd_reset'


# ---------------------------------------------------------------- page d'accueil + espaces
def _bootstrapify(form):
    """Ajoute les classes Bootstrap (et is-invalid sur les champs en erreur)."""
    for name, f in form.fields.items():
        w = f.widget
        base = 'form-select' if isinstance(w, forms.Select) else 'form-control'
        cls = w.attrs.get('class', '').replace(' is-invalid', '')
        if form.is_bound and name in form.errors:
            base += ' is-invalid'
        w.attrs['class'] = f'{cls} {base}'.strip()
        w.attrs.setdefault('placeholder', f.label or name)
    return form


def home(request):
    from django.db.models import Count, Min
    from gestion_hotel.models import Event
    from gestion_repas.models import Menu
    from gestion_rooms.models import Room
    from django.utils import timezone

    kinds = {(r['category'], r['capacity']): r for r in
             Room.objects.values('category', 'capacity').annotate(n=Count('id'), price=Min('price_per_night'))}
    room_types = []
    labels = dict(Room.CATEGORY_CHOICES)
    shown = {(Room.NORMAL, 2), (Room.NORMAL, 3), (Room.VIP, 2), (Room.VIP, 3)} | set(kinds)
    for cat, _ in Room.CATEGORY_CHOICES:
        for cap, _ in Room.CAPACITY_CHOICES:
            if (cat, cap) not in shown:
                continue
            k = kinds.get((cat, cap))
            room_types.append({'category': cat, 'label': labels[cat], 'capacity': cap,
                               'price': k['price'] if k else None, 'count': k['n'] if k else 0})
    return render(request, 'home.html', {
        'room_types': room_types,
        'events': Event.objects.filter(start__gte=timezone.now())[:3],
        'menu': Menu.objects.filter(date=timezone.localdate())[:6],
        'n_rooms': Room.objects.count(),
        'n_available': Room.objects.filter(status=Room.AVAILABLE).count(),
        'n_vip': Room.objects.filter(category=Room.VIP).count(),
        'n_staff': User.objects.exclude(role__in=[ROLE_CLIENT]).count(),
        'n_clients': User.objects.filter(role=ROLE_CLIENT).count(),
    })


def espace(request, slug):
    """Carte de connexion d'un espace, avec bascule vers l'inscription."""
    space = SPACES.get(slug)
    if space is None:
        raise Http404
    if request.user.is_authenticated:
        return redirect('dashboard')
    can_signup = space['role'] == ROLE_CLIENT or settings.ALLOW_STAFF_SIGNUP
    pane = 'login'
    login_form = _bootstrapify(LoginForm())
    signup_form = _bootstrapify(SignupForm())

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'signup' and can_signup:
            pane = 'signup'
            data = request.POST.copy()
            data['role'] = space['role']          # le rôle est imposé par l'espace
            signup_form = SignupForm(data)
            if signup_form.is_valid():
                signup_form.save()
                messages.success(request, 'Compte créé. Connectez-vous.')
                return redirect(f"{reverse('espace', args=[slug])}#login")
            _bootstrapify(signup_form)
        else:
            login_form = LoginForm(request.POST)
            if login_form.is_valid():
                user = authenticate(request, username=login_form.cleaned_data['identifier'],
                                    password=login_form.cleaned_data['password'])
                if user is None:
                    login_form.add_error(None, 'E-mail / CIN ou mot de passe incorrect.')
                elif user.role != space['role']:
                    login_form.add_error(None, f"Ce compte n'appartient pas à l'{space['title']}.")
                else:
                    login(request, user)
                    return redirect('dashboard')
            _bootstrapify(login_form)

    signup_fields = [f for f in signup_form if f.name != 'role']
    return render(request, 'account/espace.html', {
        'space': space, 'login_form': login_form, 'signup_form': signup_form,
        'signup_fields': signup_fields, 'can_signup': can_signup, 'pane': pane})


def login_view(request):
    """Ancienne URL de connexion : renvoie vers l'accueil."""
    return redirect('home')


@require_POST
def logout_view(request):
    logout(request)
    return redirect('home')


# ---------------------------------------------------------------- mot de passe oublié (3 étapes)
def _mask_email(email):
    name, _, domain = email.partition('@')
    return f"{name[:2]}{'*' * max(len(name) - 2, 1)}@{domain}"


def _reset_state(request):
    return request.session.get(RESET_KEY)


def reset_step1(request):
    """Étape 1 : CIN + e-mail du même compte -> génération et envoi du code à 6 chiffres."""
    form = ResetStep1Form(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = User.objects.filter(cin=form.cleaned_data['cin'].strip(),
                                   email__iexact=form.cleaned_data['email'].strip(),
                                   is_active=True).first()
        if user is None:
            form.add_error(None, "Aucun compte ne correspond à ce CIN et à cet e-mail.")
        else:
            code = f'{secrets.randbelow(10 ** 6):06d}'
            request.session[RESET_KEY] = {
                'uid': user.pk, 'hash': make_password(code),
                'expires': time.time() + settings.PASSWORD_RESET_CODE_TTL,
                'attempts': 0, 'verified': False,
            }
            send_mail('Code de réinitialisation du mot de passe',
                      f'Votre code de vérification est : {code}\n'
                      f'Il est valable {settings.PASSWORD_RESET_CODE_TTL // 60} minutes.',
                      None, [user.email])
            messages.info(request, 'Un code à 6 chiffres a été envoyé à votre e-mail.')
            if settings.DEBUG and 'console' in settings.EMAIL_BACKEND:
                # Aide au développement uniquement : le code est aussi dans la console du serveur.
                messages.warning(request, f'[Mode développement] Votre code : {code}')
            return redirect('reset_step2')
    return render(request, 'account/reset_step1.html', {'form': _bootstrapify(form)})


def reset_step2(request):
    """Étape 2 : saisie du même code."""
    state = _reset_state(request)
    if not state:
        return redirect('reset_step1')
    form = ResetStep2Form(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        if time.time() > state['expires']:
            request.session.pop(RESET_KEY, None)
            messages.error(request, 'Le code a expiré. Recommencez.')
            return redirect('reset_step1')
        state['attempts'] += 1
        if state['attempts'] > settings.PASSWORD_RESET_MAX_ATTEMPTS:
            request.session.pop(RESET_KEY, None)
            messages.error(request, 'Trop de tentatives. Recommencez.')
            return redirect('reset_step1')
        if check_password(form.cleaned_data['code'], state['hash']):
            state['verified'] = True
            request.session[RESET_KEY] = state
            return redirect('reset_step3')
        request.session[RESET_KEY] = state
        form.add_error('code', 'Code incorrect.')
    user = User.objects.filter(pk=state['uid']).only('email').first()
    return render(request, 'account/reset_step2.html', {
        'form': _bootstrapify(form), 'masked_email': _mask_email(user.email) if user else ''})


def reset_step3(request):
    """Étape 3 : nouveau mot de passe (uniquement si le code a été validé)."""
    state = _reset_state(request)
    if not state:
        return redirect('reset_step1')
    if not state.get('verified'):
        return redirect('reset_step2')
    user = User.objects.filter(pk=state['uid'], is_active=True).first()
    if user is None:
        request.session.pop(RESET_KEY, None)
        return redirect('reset_step1')
    form = ResetStep3Form(request.POST or None)
    form.instance = user
    if request.method == 'POST' and form.is_valid():
        user.set_password(form.cleaned_data['password1'])
        user.save(update_fields=['password'])
        request.session.pop(RESET_KEY, None)
        # Connexion automatique puis redirection vers le tableau de bord du rôle
        # (admin / client / réceptionniste / agent de nettoyage / chef).
        login(request, user, backend='account.backends.EmailOrCinBackend')
        messages.success(request, f'Mot de passe modifié. Bienvenue {user.prenom} !')
        return redirect('dashboard')
    return render(request, 'account/reset_step3.html', {'form': _bootstrapify(form)})


# ---------------------------------------------------------------- tableaux de bord
DASHBOARD_ROLES = {
    ROLE_CLIENT: 'client', ROLE_ADMIN: 'admin', ROLE_RECEPTIONIST: 'receptionist',
    ROLE_CLEANER: 'cleaner', ROLE_CHEF: 'chef',
}


@login_required
def dashboard(request):
    """Un tableau de bord différent pour chaque rôle."""
    from gestion_hotel.models import Event, Hotel
    from gestion_repas.models import Menu, StockProduct
    from gestion_rooms import services
    from gestion_rooms.models import CleaningTask, Invoice, Reservation, Room
    from django.db.models import F
    from django.utils import timezone

    user, today = request.user, timezone.localdate()
    role = user.role
    stats = []
    if role == ROLE_ADMIN:
        stats = [
            ('Mes hôtels', Hotel.objects.filter(owner=user, completed_step__gte=3).count()),
            ('Utilisateurs', User.objects.count()),
            ('Clients', User.objects.filter(role=ROLE_CLIENT).count()),
            ('Employés', User.objects.exclude(role__in=[ROLE_CLIENT, ROLE_ADMIN]).count()),
            ('Chambres', Room.objects.count()),
            ('Chambres VIP', Room.objects.filter(category=Room.VIP).count()),
            ('Événements à venir', Event.objects.filter(start__gte=timezone.now()).count()),
        ]
    elif role == ROLE_RECEPTIONIST:
        mine = Reservation.objects.filter(room__hotel_id=user.hotel_id)
        stats = [
            ('Réservations réclamées', len(services.pending_claims(user.hotel_id)) if user.hotel_id else 0),
            ('Arrivées attendues', mine.filter(status=Reservation.CONFIRMED, check_in__lte=today).count()),
            ('Départs du jour', mine.filter(status=Reservation.CHECKED_IN, check_out__lte=today).count()),
            ('Séjours en cours', mine.filter(status=Reservation.CHECKED_IN).count()),
            ('Factures impayées', Invoice.objects.filter(
                reservation__room__hotel_id=user.hotel_id, status=Invoice.UNPAID).count()),
            ('Chambres disponibles', Room.objects.filter(
                hotel_id=user.hotel_id, status=Room.AVAILABLE).count()),
        ]
    elif role == ROLE_CLEANER:
        services.notify_due_cleaning()
        mine = CleaningTask.objects.for_cleaner(user)
        stats = [
            ('À nettoyer', mine.filter(status=CleaningTask.PENDING).count()),
            ('En retard', mine.filter(status=CleaningTask.PENDING,
                                      scheduled_for__lte=timezone.now()).count()),
            ('Déjà nettoyées', mine.filter(status=CleaningTask.DONE).count()),
        ]
    elif role == ROLE_CHEF:
        stats = [
            ('Plats au menu aujourd\'hui', Menu.objects.filter(date=today).count()),
            ('Produits en stock', StockProduct.objects.count()),
            ('Stock bas', StockProduct.objects.filter(quantity__lte=F('threshold')).count()),
        ]
    else:
        stats = [
            ('Mes réservations', Reservation.objects.filter(client=user).count()),
            ('Séjours à venir', Reservation.objects.filter(
                client=user, check_in__gte=today).exclude(
                    status__in=[Reservation.CANCELLED, Reservation.REFUSED]).count()),
            ('Factures impayées', Invoice.objects.filter(
                reservation__client=user, status=Invoice.UNPAID).count()),
        ]
    notes = list(user.notifications.filter(is_read=False)[:10])
    return render(request, f'dashboards/{DASHBOARD_ROLES.get(role, "client")}.html',
                  {'stats': stats, 'notes': notes})


# ---------------------------------------------------------------- notifications
@login_required
def notifications(request):
    if request.user.role == ROLE_CLEANER:
        from gestion_rooms import services
        services.notify_due_cleaning()
    items = request.user.notifications.all()[:50]
    return render(request, 'account/notifications.html', {'items': items})


@login_required
@require_POST
def notifications_read(request):
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return redirect('notifications')


@login_required
def notifications_poll(request):
    """Appelé périodiquement par le navigateur : déclenche les rappels de nettoyage dus."""
    if request.user.role == ROLE_CLEANER:
        from gestion_rooms import services
        services.notify_due_cleaning()
    unread = request.user.notifications.filter(is_read=False)
    return JsonResponse({'count': unread.count(),
                         'latest': [n.message for n in unread[:3]]})


# ---------------------------------------------------------------- admin : gestion des utilisateurs
@role_required(ROLE_ADMIN)
def user_list(request):
    qs = User.objects.select_related('hotel')
    role = request.GET.get('role')
    if role:
        qs = qs.filter(role=role)
    return crud.list_page(
        request, title='Gestion des utilisateurs', queryset=qs, base_name='user',
        columns=[('CIN', lambda u: u.cin), ('Nom', lambda u: u.full_name),
                 ('E-mail', lambda u: u.email), ('Téléphone', lambda u: u.telephone),
                 ('Rôle', lambda u: u.get_role_display()),
                 ('Hôtel', lambda u: u.hotel.name if u.hotel_id else '—'),
                 ('Actif', lambda u: 'Oui' if u.is_active else 'Non')],
        filters={'name': 'role', 'value': role, 'choices': User._meta.get_field('role').choices})


@role_required(ROLE_ADMIN)
def user_add(request):
    return crud.form_page(request, form_class=UserAdminForm, title='Nouvel utilisateur',
                          form_kwargs={'admin': request.user}, success_url='user_list')


@role_required(ROLE_ADMIN)
def user_edit(request, pk):
    from django.shortcuts import get_object_or_404
    return crud.form_page(request, form_class=UserAdminForm, title='Modifier l\'utilisateur',
                          instance=get_object_or_404(User, pk=pk),
                          form_kwargs={'admin': request.user}, success_url='user_list')


@role_required(ROLE_ADMIN)
def user_delete(request, pk):
    if pk == request.user.pk:
        messages.error(request, 'Vous ne pouvez pas supprimer votre propre compte.')
        return redirect('user_list')
    return crud.delete_page(request, model=User, pk=pk, success_url='user_list',
                            label=lambda u: f'{u.full_name} ({u.email})')
