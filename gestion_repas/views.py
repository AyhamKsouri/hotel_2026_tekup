from django.shortcuts import get_object_or_404
from django.utils import timezone

from account import crud
from account.decorators import role_required
from account.models import ROLE_ADMIN, ROLE_CHEF, ROLE_CLIENT

from .forms import MenuForm, StockForm
from .models import Menu, StockProduct


def _menu_cols():
    return [('Date', lambda m: m.date.strftime('%d/%m/%Y')), ('Plat', lambda m: m.name),
            ('Type', lambda m: m.get_category_display()),
            ('Description', lambda m: m.description or '—'), ('Prix', lambda m: f'{m.price:.2f} TND')]


@role_required(ROLE_CHEF)
def menu_today(request):
    return crud.list_page(request, title='Menu d\'aujourd\'hui', queryset=Menu.objects.filter(
        date=timezone.localdate()), base_name='menu', columns=_menu_cols())


@role_required(ROLE_CHEF)
def menu_list(request):
    return crud.list_page(request, title='Tous les menus', queryset=Menu.objects.all(),
                          base_name='menu', columns=_menu_cols())


@role_required(ROLE_CHEF)
def menu_add(request):
    return crud.form_page(request, form_class=MenuForm, title='Ajouter un plat au menu',
                          success_url='menu_today')


@role_required(ROLE_CHEF)
def menu_edit(request, pk):
    return crud.form_page(request, form_class=MenuForm, title='Modifier le plat',
                          instance=get_object_or_404(Menu, pk=pk), success_url='menu_list')


@role_required(ROLE_CHEF)
def menu_delete(request, pk):
    return crud.delete_page(request, model=Menu, pk=pk, success_url='menu_list',
                            label=lambda m: m.name)


@role_required(ROLE_CHEF)
def stock_list(request):
    qs = StockProduct.objects.all()
    cat = request.GET.get('category')
    if cat:
        qs = qs.filter(category=cat)
    return crud.list_page(
        request, title='Stock des produits', queryset=qs, base_name='stock',
        columns=[('Produit', lambda p: p.name), ('Catégorie', lambda p: p.get_category_display()),
                 ('Quantité', lambda p: f'{p.quantity:g} {p.unit}'),
                 ('Seuil', lambda p: f'{p.threshold:g} {p.unit}'),
                 ('État', lambda p: '⚠ Stock bas' if p.is_low else 'OK')],
        filters={'name': 'category', 'value': cat, 'choices': StockProduct.CATEGORY_CHOICES})


@role_required(ROLE_CHEF)
def stock_add(request):
    return crud.form_page(request, form_class=StockForm, title='Nouveau produit', success_url='stock_list')


@role_required(ROLE_CHEF)
def stock_edit(request, pk):
    return crud.form_page(request, form_class=StockForm, title='Modifier le produit',
                          instance=get_object_or_404(StockProduct, pk=pk), success_url='stock_list')


@role_required(ROLE_CHEF)
def stock_delete(request, pk):
    return crud.delete_page(request, model=StockProduct, pk=pk, success_url='stock_list',
                            label=lambda p: p.name)


@role_required(ROLE_CLIENT)
def client_menu(request):
    return crud.list_page(
        request, title='Menu du jour', subtitle=timezone.localdate().strftime('%d/%m/%Y'),
        queryset=Menu.objects.filter(date=timezone.localdate()), add=False, edit=False, delete=False,
        columns=_menu_cols()[1:])
