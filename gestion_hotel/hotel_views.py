"""Assistant de création d'hôtel en 3 étapes (réservé aux administrateurs).

Étape 1 : informations générales  -> crée l'hôtel en brouillon
Étape 2 : chambres (images, nombres, total auto)
Étape 3 : tarifs, services, formules -> génère les chambres et termine l'hôtel
"""
from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from account.crud import bootstrapify
from account.decorators import role_required
from account.models import ROLE_ADMIN
from gestion_rooms.models import Room

from .hotel_forms import (validate_image_size, PLAN_PRESETS, SERVICE_PRESETS, COUNTRIES, HotelInfoForm, HotelPricingForm,
                          HotelRoomsForm, PlanFormSet, ServiceFormSet)
from .models import MAX_GALLERY_IMAGES, Hotel, HotelImage

ROOM_PREFIX = {Room.NORMAL: 'N', Room.VIP: 'V', Room.COUPLE: 'C', Room.FAMILY: 'F'}
STEP_TITLES = {1: 'Informations', 2: 'Chambres', 3: 'Services et tarification'}


def _my_hotel(request, pk):
    return get_object_or_404(Hotel, pk=pk, owner=request.user)


def _guard(request, hotel, step):
    """Renvoie une redirection si l'étape demandée n'est pas accessible, sinon None."""
    if hotel.is_complete:
        messages.info(request, 'Cet hôtel est déjà créé.')
        return redirect('hotel_detail', pk=hotel.pk)
    if step > hotel.completed_step + 1:
        messages.warning(request, f'Terminez d\'abord l\'étape {hotel.completed_step + 1}.')
        return redirect('hotel_step', pk=hotel.pk, step=hotel.next_step)
    return None


def _wizard_ctx(hotel, step, **extra):
    return {'hotel': hotel, 'step': step, 'step_title': STEP_TITLES[step],
            'steps': [(n, t) for n, t in STEP_TITLES.items()],
            'completed': hotel.completed_step if hotel else 0, **extra}


# ------------------------------------------------------------------ liste / détail / suppression
@role_required(ROLE_ADMIN)
def hotel_list(request):
    hotels = Hotel.objects.filter(owner=request.user)
    return render(request, 'hotels/list.html', {'hotels': hotels})


@role_required(ROLE_ADMIN)
def hotel_detail(request, pk):
    hotel = _my_hotel(request, pk)
    if not hotel.is_complete:
        return redirect('hotel_step', pk=hotel.pk, step=hotel.next_step)
    return render(request, 'hotels/detail.html', {
        'hotel': hotel, 'services': hotel.services.all(), 'plans': hotel.plans.all(),
        'types': hotel.room_types(), 'gallery': hotel.gallery.all(), 'max_images': MAX_GALLERY_IMAGES})


@role_required(ROLE_ADMIN)
def hotel_delete(request, pk):
    hotel = _my_hotel(request, pk)
    if request.method == 'POST':
        try:
            hotel.delete()
        except ProtectedError:
            messages.error(request, 'Impossible : des chambres de cet hôtel ont des réservations.')
            return redirect('hotel_list')
        messages.success(request, 'Hôtel supprimé.')
        return redirect('hotel_list')
    return render(request, 'crud/confirm_delete.html',
                  {'object_label': f'l\'hôtel « {hotel.name} » et ses chambres', 'back_url': reverse('hotel_list')})


# ------------------------------------------------------------------ étape 1
@role_required(ROLE_ADMIN)
def hotel_new(request):
    """Étape 1, hôtel pas encore créé."""
    return _step1(request, None)


@role_required(ROLE_ADMIN)
def hotel_step(request, pk, step):
    hotel = _my_hotel(request, pk)
    if step == 1:
        return _step1(request, hotel)
    if step not in (2, 3):
        return redirect('hotel_step', pk=hotel.pk, step=hotel.next_step)
    blocked = _guard(request, hotel, step)
    if blocked:
        return blocked
    return _step2(request, hotel) if step == 2 else _step3(request, hotel)


def _step1(request, hotel):
    form = HotelInfoForm(request.POST or None, instance=hotel)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.owner = request.user
        obj.completed_step = max(obj.completed_step or 0, 1)
        obj.save()
        if obj.is_complete:
            messages.success(request, 'Informations mises à jour.')
            return redirect('hotel_detail', pk=obj.pk)
        return redirect('hotel_step', pk=obj.pk, step=obj.next_step)
    return render(request, 'hotels/step1.html', _wizard_ctx(
        hotel, 1, form=bootstrapify(form), countries=COUNTRIES))


# ------------------------------------------------------------------ étape 2
def _step2(request, hotel):
    form = HotelRoomsForm(request.POST or None, request.FILES or None, instance=hotel)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.completed_step = max(obj.completed_step, 2)
        obj.save()
        return redirect('hotel_step', pk=obj.pk, step=3)
    return render(request, 'hotels/step2.html', _wizard_ctx(
        hotel, 2, form=bootstrapify(form), gallery=hotel.gallery.all(), max_images=MAX_GALLERY_IMAGES))


# ------------------------------------------------------------------ étape 3
def _generate_rooms(hotel):
    rooms = []
    for key, _label, count, price, capacity in hotel.room_types():
        prefix = ROOM_PREFIX[key]
        rooms += [Room(hotel=hotel, number=f'{prefix}{i:03d}', category=key, capacity=capacity,
                       price_per_night=price) for i in range(1, count + 1)]
    Room.objects.bulk_create(rooms)
    return len(rooms)


def _step3(request, hotel):
    posting = request.method == 'POST'
    form = HotelPricingForm(request.POST if posting else None, instance=hotel)
    services = ServiceFormSet(request.POST if posting else None, instance=hotel, prefix='services')
    plans = PlanFormSet(request.POST if posting else None, instance=hotel, prefix='plans')

    if posting and form.is_valid() and services.is_valid() and plans.is_valid():
        with transaction.atomic():
            locked = Hotel.objects.select_for_update().get(pk=hotel.pk)
            if locked.is_complete:               # double envoi : rien à refaire
                return redirect('hotel_detail', pk=hotel.pk)
            hotel = form.save(commit=False)      # prix saisis, déjà posés sur l'instance
            n_rooms = _generate_rooms(hotel)
            hotel.completed_step = 3
            hotel.save()
            services.save()
            plans.save()
        s = 's' if n_rooms > 1 else ''
        messages.success(request, f'Hôtel « {hotel.name} » créé : {n_rooms} chambre{s} générée{s}.')
        return redirect('hotel_detail', pk=hotel.pk)

    for f in [form, *services.forms, *plans.forms, services.empty_form, plans.empty_form]:
        bootstrapify(f)
    return render(request, 'hotels/step3.html', _wizard_ctx(
        hotel, 3, form=form, services=services, plans=plans,
        service_presets=SERVICE_PRESETS, plan_presets=PLAN_PRESETS, types=hotel.room_types()))


# ------------------------------------------------------------------ galerie (bouton « + »)
def _back(hotel):
    return redirect('hotel_detail', pk=hotel.pk) if hotel.is_complete else redirect('hotel_step', pk=hotel.pk, step=2)


@role_required(ROLE_ADMIN)
@require_POST
def hotel_image_add(request, pk):
    hotel = _my_hotel(request, pk)
    files = request.FILES.getlist('images')
    room_left = MAX_GALLERY_IMAGES - hotel.gallery.count()
    if not files:
        messages.error(request, 'Aucune image sélectionnée.')
        return _back(hotel)
    added = 0
    for f in files:
        if added >= room_left:
            messages.warning(request, f'Maximum {MAX_GALLERY_IMAGES} images par hôtel.')
            break
        try:
            forms.ImageField().clean(f)       # vérifie que c'est bien une image
            validate_image_size(f)
        except ValidationError as e:
            messages.error(request, f'« {f.name} » refusée : {e.messages[0]}')
            continue
        HotelImage.objects.create(hotel=hotel, image=f)
        added += 1
    if added:
        messages.success(request, f'{added} image{"s" if added > 1 else ""} ajoutée{"s" if added > 1 else ""}.')
    return _back(hotel)


@role_required(ROLE_ADMIN)
@require_POST
def hotel_image_delete(request, pk, image_pk):
    hotel = _my_hotel(request, pk)
    img = get_object_or_404(HotelImage, pk=image_pk, hotel=hotel)
    img.image.delete(save=False)
    img.delete()
    messages.success(request, 'Image supprimée.')
    return _back(hotel)
