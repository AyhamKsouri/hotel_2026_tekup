from django.shortcuts import get_object_or_404
from django.utils import timezone

from account import crud
from account.decorators import role_required
from account.models import ROLE_ADMIN, ROLE_CLIENT

from .forms import EventForm
from .models import Event


def _cols():
    return [('Titre', lambda e: e.title), ('Lieu', lambda e: e.location),
            ('Début', lambda e: timezone.localtime(e.start).strftime('%d/%m/%Y %H:%M')),
            ('Capacité', lambda e: e.capacity), ('Prix', lambda e: f'{e.price:.2f} TND')]


@role_required(ROLE_ADMIN)
def event_list(request):
    return crud.list_page(request, title='Gestion des événements', queryset=Event.objects.all(),
                          base_name='event', columns=_cols())


@role_required(ROLE_ADMIN)
def event_add(request):
    return crud.form_page(request, form_class=EventForm, title='Nouvel événement', success_url='event_list')


@role_required(ROLE_ADMIN)
def event_edit(request, pk):
    return crud.form_page(request, form_class=EventForm, title='Modifier l\'événement',
                          instance=get_object_or_404(Event, pk=pk), success_url='event_list')


@role_required(ROLE_ADMIN)
def event_delete(request, pk):
    return crud.delete_page(request, model=Event, pk=pk, success_url='event_list',
                            label=lambda e: e.title)


@role_required(ROLE_CLIENT)
def client_events(request):
    return crud.list_page(
        request, title='Événements de l\'hôtel', subtitle='Événements à venir',
        queryset=Event.objects.filter(start__gte=timezone.now()), add=False, edit=False, delete=False,
        columns=_cols() + [('Description', lambda e: e.description or '—')])
