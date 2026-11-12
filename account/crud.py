"""Petites aides communes pour les écrans liste / formulaire / suppression."""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse


def bootstrapify(form):
    from django import forms
    for name, f in form.fields.items():
        w = f.widget
        if getattr(w, 'input_type', '') == 'checkbox':
            continue
        base = 'form-select' if isinstance(w, forms.Select) else 'form-control'
        if form.is_bound and name in form.errors:
            base += ' is-invalid'
        w.attrs['class'] = (w.attrs.get('class', '').replace('form-control', '').replace('form-select', '').replace('is-invalid', '').strip() + ' ' + base).strip()
    return form


def list_page(request, *, title, queryset, columns, base_name=None, add=True,
              extra_actions=(), filters=None, edit=True, delete=True, subtitle=''):
    """columns : [(en-tête, fonction(obj) -> texte)].
    extra_actions : [(libellé, nom_url, condition(obj))] -> boutons POST."""
    rows = []
    for obj in queryset:
        actions = [(label, reverse(url, args=[obj.pk]))
                   for label, url, cond in extra_actions if cond is None or cond(obj)]
        rows.append({
            'cells': [fn(obj) for _, fn in columns],
            'actions': actions,
            'edit_url': reverse(f'{base_name}_edit', args=[obj.pk]) if base_name and edit else None,
            'delete_url': reverse(f'{base_name}_delete', args=[obj.pk]) if base_name and delete else None,
        })
    return render(request, 'crud/list.html', {
        'title': title, 'subtitle': subtitle, 'headers': [h for h, _ in columns], 'rows': rows,
        'add_url': reverse(f'{base_name}_add') if base_name and add else None,
        'filters': filters,
    })


def form_page(request, *, form_class, title, success_url, instance=None,
              form_kwargs=None, on_save=None, after_save=None, success_message='Enregistré avec succès.'):
    kwargs = dict(form_kwargs or {})
    form = form_class(request.POST or None, instance=instance, **kwargs)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        if on_save:
            on_save(obj, form)
        obj.save()
        form.save_m2m()
        if after_save:
            after_save(obj)
        messages.success(request, success_message)
        return redirect(success_url)
    return render(request, 'crud/form.html', {
        'form': bootstrapify(form), 'title': title, 'back_url': reverse(success_url)})


def delete_page(request, *, model, pk, success_url, label=str, queryset=None):
    obj = get_object_or_404(queryset if queryset is not None else model, pk=pk)
    if request.method == 'POST':
        obj.delete()
        messages.success(request, 'Supprimé.')
        return redirect(success_url)
    return render(request, 'crud/confirm_delete.html', {
        'object_label': label(obj), 'back_url': reverse(success_url)})
