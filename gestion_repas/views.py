from datetime import date

from django.contrib import messages
from django.db.models import F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from account import crud
from account.decorators import role_required
from account.models import ROLE_CHEF, ROLE_CLIENT

from .forms import MenuForm, StockForm
from .models import Menu, StockProduct


def _chef_form(request, *, form_class, title, success_url, instance=None, form_kwargs=None, subtitle=''):
    """Formulaire chef avec prise en charge de l'import local d'image (multipart)."""
    form = form_class(request.POST or None, request.FILES or None, instance=instance, **(form_kwargs or {}))
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Enregistré avec succès.')
        return redirect(success_url)
    return render(request, 'repas/chef_form.html', {
        'form': crud.bootstrapify(form),
        'title': title,
        'subtitle': subtitle,
        'back_url': reverse(success_url),
        'instance': instance,
    })


def _render_menu_list(request, *, queryset, title, subtitle, is_today, add_url_name, edit_url_name, delete_url_name):
    cat = request.GET.get('category', '')
    q = (request.GET.get('q') or '').strip()
    date_filter = request.GET.get('date', '') if not is_today else ''
    try:                                   # date invalide dans l'URL : filtre ignoré (pas d'erreur 500)
        date.fromisoformat(date_filter) if date_filter else None
    except ValueError:
        date_filter = ''
    qs = queryset
    if cat:
        qs = qs.filter(category=cat)
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
    if date_filter:
        qs = qs.filter(date=date_filter)
    rows = [{
        'obj': item,
        'edit_url': reverse(edit_url_name, args=[item.pk]),
        'delete_url': reverse(delete_url_name, args=[item.pk]),
    } for item in qs]
    return render(request, 'repas/menu_list.html', {
        'title': title,
        'subtitle': subtitle,
        'is_today': is_today,
        'rows': rows,
        'add_url': reverse(add_url_name),
        'categories': Menu.CATEGORY_CHOICES,
        'selected_category': cat,
        'selected_date': date_filter,
        'search': q,
    })


# ------------------------------------------------------------------ Menu d'aujourd'hui (CRUD)
@role_required(ROLE_CHEF)
def menu_today(request):
    today = timezone.localdate()
    return _render_menu_list(
        request,
        queryset=Menu.objects.filter(date=today),
        title="Menu d'aujourd'hui",
        subtitle=today.strftime('%d/%m/%Y'),
        is_today=True,
        add_url_name='menu_today_add',
        edit_url_name='menu_today_edit',
        delete_url_name='menu_today_delete',
    )


@role_required(ROLE_CHEF)
def menu_today_add(request):
    return _chef_form(
        request,
        form_class=MenuForm,
        form_kwargs={'today_only': True},
        title="Ajouter un plat au menu d'aujourd'hui",
        subtitle=timezone.localdate().strftime('%d/%m/%Y'),
        success_url='menu_today',
    )


@role_required(ROLE_CHEF)
def menu_today_edit(request, pk):
    obj = get_object_or_404(Menu, pk=pk, date=timezone.localdate())
    return _chef_form(
        request,
        form_class=MenuForm,
        form_kwargs={'today_only': True},
        instance=obj,
        title="Modifier le plat d'aujourd'hui",
        subtitle=obj.date.strftime('%d/%m/%Y'),
        success_url='menu_today',
    )


@role_required(ROLE_CHEF)
def menu_today_delete(request, pk):
    return crud.delete_page(
        request,
        model=Menu,
        pk=pk,
        success_url='menu_today',
        label=lambda m: m.name,
        queryset=Menu.objects.filter(date=timezone.localdate()),
    )


# ------------------------------------------------------------------ Tous les menus (CRUD)
@role_required(ROLE_CHEF)
def menu_list(request):
    return _render_menu_list(
        request,
        queryset=Menu.objects.all(),
        title='Tous les menus',
        subtitle='Historique et planification des plats',
        is_today=False,
        add_url_name='menu_add',
        edit_url_name='menu_edit',
        delete_url_name='menu_delete',
    )


@role_required(ROLE_CHEF)
def menu_add(request):
    return _chef_form(
        request,
        form_class=MenuForm,
        title='Ajouter un plat au menu',
        success_url='menu_list',
    )


@role_required(ROLE_CHEF)
def menu_edit(request, pk):
    obj = get_object_or_404(Menu, pk=pk)
    return _chef_form(
        request,
        form_class=MenuForm,
        instance=obj,
        title='Modifier le plat',
        success_url='menu_list',
    )


@role_required(ROLE_CHEF)
def menu_delete(request, pk):
    return crud.delete_page(
        request,
        model=Menu,
        pk=pk,
        success_url='menu_list',
        label=lambda m: m.name,
    )


# ------------------------------------------------------------------ Stock des produits (CRUD)
@role_required(ROLE_CHEF)
def stock_list(request):
    qs = StockProduct.objects.all()
    cat = request.GET.get('category', '')
    q = (request.GET.get('q') or '').strip()
    low = request.GET.get('low', '')
    if cat:
        qs = qs.filter(category=cat)
    if q:
        qs = qs.filter(name__icontains=q)
    if low == '1':
        qs = qs.filter(quantity__lte=F('threshold'))
    low_count = StockProduct.objects.filter(quantity__lte=F('threshold')).count()
    return render(request, 'repas/stock_list.html', {
        'title': 'Stock des produits',
        'items': qs,
        'categories': StockProduct.CATEGORY_CHOICES,
        'selected_category': cat,
        'search': q,
        'low_only': low == '1',
        'low_count': low_count,
    })


@role_required(ROLE_CHEF)
def stock_add(request):
    return _chef_form(
        request,
        form_class=StockForm,
        title='Nouveau produit en stock',
        success_url='stock_list',
    )


@role_required(ROLE_CHEF)
def stock_edit(request, pk):
    obj = get_object_or_404(StockProduct, pk=pk)
    return _chef_form(
        request,
        form_class=StockForm,
        instance=obj,
        title='Modifier le produit',
        success_url='stock_list',
    )


@role_required(ROLE_CHEF)
def stock_delete(request, pk):
    return crud.delete_page(
        request,
        model=StockProduct,
        pk=pk,
        success_url='stock_list',
        label=lambda p: p.name,
    )


# ------------------------------------------------------------------ Client : consultation menu du jour
@role_required(ROLE_CLIENT)
def client_menu(request):
    return crud.list_page(
        request,
        title='Menu du jour',
        subtitle=timezone.localdate().strftime('%d/%m/%Y'),
        queryset=Menu.objects.filter(date=timezone.localdate()),
        add=False,
        edit=False,
        delete=False,
        columns=[
            ('Plat', lambda m: m.name),
            ('Type', lambda m: m.get_category_display()),
            ('Description', lambda m: m.description or '—'),
        ],
    )
