import datetime
import tablib

from django.utils.encoding import smart_unicode
from django.utils.translation import ugettext_lazy as _

mimetype_map = {
    'xls': 'application/vnd.ms-excel',
    'csv': 'text/csv',
    'html': 'text/html',
    'yaml': 'text/yaml',
    'json': 'application/json',
}


class BaseDataset(tablib.Dataset):

    encoding = 'utf-8'

    def __init__(self):
        data = map(self._getattrs, self.queryset)
        super(BaseDataset, self).__init__(headers=self.header_list, *data)

    def _cleanval(self, value, attr):
        if callable(value):
            value = value()
        elif value is None or unicode(value) == u"None":
            value = ""

        t = type(value)
        if t is str:
            return value
        elif t in [datetime.date, datetime.datetime]:
            return value.strftime('%Y-%m-%dT%H:%M:%SZ').encode("utf-8")
        elif t is bool:
            value = _("Y") if value else _("N")
            return smart_unicode(value).encode(self.encoding)
        # XXX: This code should not logically ever be hit, given the first
        # elif, but it is present. Evaluate it please.
        # elif t in [datetime.date, datetime.datetime]:
        #     return date(value, 'SHORT_DATE_FORMAT').encode(self.encoding)

        return smart_unicode(value).encode(self.encoding)

    def _getattrs(self, obj):
        attrs = []
        for attr in self.attr_list:
            if callable(attr):
                attr = self._cleanval(attr(obj), attr)
            else:
                # XXX: This was the jazkarta version of this logical branch. It
                # is unclear if the problems it solved are covered by the
                # mainline changes below. Retain this as reference in case of
                # bugs
                # if '.' in attr:
                #     (fk_obj, fk_attr) = attr.split('.')
                #     fk_obj = getattr(obj, fk_obj)
                #     attr = self._cleanval(getattr(fk_obj, fk_attr, ''), fk_attr)
                # else:
                #     attr = self._cleanval(getattr(obj, attr, ''), attr)
                if hasattr(obj, 'get_%s_display' % attr):
                    value = getattr(obj, 'get_%s_display' % attr)()
                else:
                    value = getattr(obj, attr)
                attr = self._cleanval(value, attr)
            attrs.append(attr)
        return attrs

    def append(self, *args, **kwargs):
        # Thanks to my previous decision to simply not support columns, this
        # dumb conditional is necessary to preserve backwards compatibility.
        if len(args) == 1:
            # if using old syntax, just set django_object to args[0] and
            # col to None
            django_object = args[0]
            col = None
        else:
            # otherwise assume both row and col may have been passed and
            # handle appropriately
            django_object = kwargs.get('row', None)
            col = kwargs.get('col', None)

        # make sure that both row and col are in a format that can be passed
        # straight to tablib
        if django_object is not None:
            row = self._getattrs(django_object)
        else:
            row = django_object

        super(BaseDataset, self).append(row=row, col=col)
