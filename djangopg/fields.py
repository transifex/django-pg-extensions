# -*- coding: utf-8 -*-

from django.db import models
from django.utils.encoding import smart_unicode


class ArrayContains(models.Lookup):
    lookup_name = 'array_contains'

    def as_sql(self, compiler, connection):
        lhs, lhs_params = self.process_lhs(compiler, connection)
        params = lhs_params
        return '%s @> ARRAY%s' % (
            lhs, [i.encode("utf8") for i in self.rhs]
        ), params


class ArrayField(models.Field):
    """Base class for fields of type array."""

    __metaclass__ = models.SubfieldBase

    _allowed_operators = [
        'exact', 'isnull', 'array_contains',
        'array_contained', 'array_overlaps',
    ]

    def db_type(self, connection):
        return '%s[]' % self._type

    def to_python(self, value):
        # Psycopg2 uses lists for arrays
        if value is None or value == '':
            # The check for empty strings is needed, because to_python
            # is called on empty constructors.
            return None
        if not isinstance(value, list):
            raise TypeError("Expected list, got %s" % type(value))
        return value

    def get_prep_value(self, value):
        return value

    def get_prep_lookup(self, lookup_type, value):
        if lookup_type not in self._allowed_operators:
            raise TypeError('Invalid operator %s' % lookup_type)
        return value

    def get_db_prep_lookup(self, lookup_type, value, connection, prepared=False):
        prep_value = super(ArrayField, self).get_db_prep_lookup(
            lookup_type, value, connection, prepared
        )
        if prep_value is None and lookup_type.startswith('array_'):
            prep_value = self.get_db_prep_value(
                value, connection=connection, prepared=prepared
            )
            return [prep_value]


class TextArrayField(ArrayField):
    """Field for arrays of VARCHAR."""

    description = 'Text array'
    _type = 'text'

    def to_python(self, value):
        value = super(TextArrayField, self).to_python(value)
        if value is None:
            return None
        return map(smart_unicode, value)


class IntArrayField(ArrayField):
    """Field for arrays of INT."""

    description = 'INT array'
    _type = 'int'


class CaseInsensitiveMixin(object):
    """Add a case-insensitive variant of text fields."""

    def db_type(self, connection):
        return 'citext'

    def to_python(self, value):
        if isinstance(value, unicode) or value is None:
            return value
        if isinstance(value, str):
            return value.decode('UTF-8')
        return smart_unicode(value)


class CaseInsensitiveCharField(CaseInsensitiveMixin, models.CharField):
    """Case-insensitive CharField."""

    __metaclass__ = models.SubfieldBase


class CaseInsensitiveSlugField(CaseInsensitiveMixin, models.SlugField):
    """Case-insensitive SlugField."""

    __metaclass__ = models.SubfieldBase
