# -*- coding: utf-8 -*-

import re
import csv
from cStringIO import StringIO
from contextlib import closing
from django.db import connections
from django.db.models import AutoField


def _convert_to_csv_form(data):
    """Convert the data to a form suitable for CSV."""
    # NULL values should be an empty column
    if data is None:
        return ''
    # Empty strings should be different to NULL values
    if data == '':
        return '""'
    # CSV needs to be encoded to UTF8
    if isinstance(data, unicode):
        return data.encode('UTF-8')
    return data


def _fix_empty_string_marks(text):
    """Fix the empty string notation in text to what PostgreSQL expects."""
    # COPY command expects the empty string to be quoted.
    # But csv quotes the double-quotes we put.
    # Replace the quoted values either at the first entry, the last or one in
    # between with "".
    substiture = r'((?<=^)""""""(?=,)|(?<=,)""""""(?=,)|(?<=,)""""""(?=$))'
    replace_with = r'""'
    return re.sub(substiture, replace_with, text, flags=re.M)


def _send_csv_to_postgres(csv_text, conn, table_name, columns):
    """
    Send the CSV file to PostgreSQL for inserting the entries.

    Use the COPY command for faster insertion and less WAL generation.

    :param csv_text: A CSV-formatted string with the data to send.
    :param conn: The connection object.
    """
    fd = StringIO(csv_text)
    # Move the fp to the beginning of the string
    fd.seek(0)
    columns = map(conn.ops.quote_name, columns)
    cursor = conn.cursor()
    sql = "COPY %s(%s) FROM STDIN WITH CSV"
    try:
        cursor.copy_expert(sql % (table_name, ','.join(columns)), fd)
    finally:
        cursor.close()
        fd.close()


def copy_insert(model, entries, columns=None, using='default',
                pre_save=True, **kwargs):
    """
    Add the given entries to the database using the COPY command.

    The caller is required to handle the transaction.

    Supports the option of not calling `pre_save()` on entries
    before performing the COPY operation. This might be useful in
    cases where some fields are automatically updated inside pre_save(),
    e.g. DateTime fields with `auto_now=True`.

    :param model: The model class the entries are for.
    :param entries: An iterable of entries to be inserted.
    :param columns: A list of columns that will have to be populated.
        By default, we use all columns but the primary key.
    :param using: The database connection to use.
    :param bool pre_save: If True, `pre_save()` will be called on each entry
        before executing COPY, otherwise it won't. `get_db_prep_save()`
        will always be called either way
    """
    table_name = kwargs.get('table_name', model._meta.db_table)
    conn = connections[using]

    if columns is None:
        fields = [
            f for f in model._meta.fields if not isinstance(f, AutoField)
        ]
    else:
        fields = [model._meta.get_field_by_name(col)[0] for col in columns]

    # Construct a StringIO from the entries
    with closing(StringIO()) as fd:
        csvf = csv.writer(fd, lineterminator='\n')
        for entry in entries:
            row = []
            for f in fields:
                value = entry

                # We only call pre_save() if we are told to
                if pre_save:
                    value = f.pre_save(entry, True)
                # Otherwise we get the value as is
                else:
                    value = getattr(entry, f.name)

                # We always call get_db_prep_save(), because it
                # updates the value depending on the current backend
                value = f.get_db_prep_save(value, connection=conn)
                row.append(_convert_to_csv_form(value))

            csvf.writerow(row)

        content = _fix_empty_string_marks(fd.getvalue())
    db_columns = [f.column for f in fields]
    _send_csv_to_postgres(content, conn, table_name, db_columns)


def copy_insert_raw(table_name, entries, columns, using='default'):
    conn = connections[using]

    # Construct a StringIO from the entries
    with closing(StringIO()) as fd:
        csvf = csv.writer(fd, lineterminator='\n')
        for e in entries:
            row = [
                _convert_to_csv_form(cell) for cell in e
            ]
            csvf.writerow(row)
        content = _fix_empty_string_marks(fd.getvalue())
    _send_csv_to_postgres(content, conn, table_name, columns)
