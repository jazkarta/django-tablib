from __future__ import absolute_import

import csv

from django import get_version
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.urlresolvers import reverse
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.http import HttpResponseRedirect
from django.db.models.loading import get_model
from django.shortcuts import render
from django.contrib import messages

from .base import mimetype_map
from .datasets import SimpleDataset


def export(request, queryset=None, model=None, headers=None, file_type='xls',
           filename='export'):
    if queryset is None:
        queryset = model.objects.all()

    dataset = SimpleDataset(queryset, headers=headers)
    filename = '%s.%s' % (filename, file_type)
    if not hasattr(dataset, file_type):
        raise Http404

    response_kwargs = {}
    key = 'content_type' if get_version().split('.')[1] > 6 else 'mimetype'
    response_kwargs[key] = mimetype_map.get(
        file_type, 'application/octet-stream')

    response = HttpResponse(getattr(dataset, file_type), **response_kwargs)

    response['Content-Disposition'] = 'attachment; filename=%s' % filename
    return response


def generic_export(request, model_name=None):
    """
    Generic view configured through settings.TABLIB_MODELS

    Usage:
        1. Add the view to ``urlpatterns`` in ``urls.py``::
            url(r'export/(?P<model_name>[^/]+)/$', "django_tablib.views.generic_export"),
        2. Create the ``settings.TABLIB_MODELS`` dictionary using model names
           as keys the allowed lookup operators as values, if any::

           TABLIB_MODELS = {
               'myapp.simple': None,
               'myapp.related': {'simple__title': ('exact', 'iexact')},
           }
        3. Open ``/export/myapp.simple`` or
           ``/export/myapp.related/?simple__title__iexact=test``
    """

    if model_name not in settings.TABLIB_MODELS:
        raise Http404()

    model = get_model(*model_name.split(".", 2))
    if not model:
        raise ImproperlyConfigured(
            "Model %s is in settings.TABLIB_MODELS but"
            " could not be loaded" % model_name)

    qs = model._default_manager.all()

    # Filtering may be allowed based on TABLIB_MODELS:
    filter_settings = settings.TABLIB_MODELS[model_name]
    filters = {}

    for k, v in request.GET.items():
        try:
            # Allow joins (they'll be checked below) but chop off the trailing
            # lookup operator:
            rel, lookup_type = k.rsplit("__", 1)
        except ValueError:
            rel = k
            lookup_type = "exact"

        allowed_lookups = filter_settings.get(rel, None)

        if allowed_lookups is None:
            return HttpResponseBadRequest(
                "Filtering on %s is not allowed" % rel
            )
        elif lookup_type not in allowed_lookups:
            return HttpResponseBadRequest(
                "%s may only be filtered using %s"
                % (k, " ".join(allowed_lookups)))
        else:
            filters[str(k)] = v

    if filters:
        qs = qs.filter(**filters)

    return export(request, model=model, queryset=qs)


def import_csv(request, model, keys, rel_app_labels):
    model_name = model.__name__
    if request.method == 'POST':
        csv_file = request.FILES.get('csv_file')
        reader = csv.DictReader(csv_file)
        rows = 0
        for row in reader:
            rows += 1
            key_args = {}
            related = {}
            for key in keys:
                if '.' in key:
                    mod, mod_key = key.split('.')
                    if mod not in related:
                        related[mod] = {}
                    related[mod][mod_key] = row[key]
                    continue
                key_args[key] = row[key]
            for rel_key, rel_fields in related.items():
                app_label, app_model = rel_app_labels[rel_key]
                rel_mod = get_model(app_label, app_model)
                try:
                    rel_obj = rel_mod.objects.get(**rel_fields)
                except rel_mod.DoesNotExist:
                    rel_obj = rel_mod(**rel_fields)
                    rel_obj.save()
                key_args[rel_key] = rel_obj
            try:
                obj = model.objects.get(**key_args)
            except model.DoesNotExist:
                obj = model(**key_args)
            for field, value in row.items():
                setattr(obj, field, value)
            obj.save()
        message = "Imported %d rows" % rows
        messages.add_message(request, messages.INFO, message)
        url = reverse('admin:%s_%s_changelist' % (model._meta.app_label,
            model_name.lower()))
        return HttpResponseRedirect(url)

    return render(request, 'tablib/import_csv.html', {
        'model': model_name
    })
