# -*- coding: utf-8 -*-

"""
Tests for the COPY command support.
"""

from datetime import datetime
import unittest
import csv
from StringIO import StringIO
from mock import patch
from djangopg.copy import _convert_to_csv_form, copy_insert
from tests.data import Article, Choice, Poll


class DataConversionTestCase(unittest.TestCase):
    """Tests for converting pieces of data to a suitable form."""

    def test_none_is_converted_to_empty_string(self):
        data = None
        res = _convert_to_csv_form(data)
        expected = ''
        self.assertEqual(res, expected)

    def test_empty_string_is_double_quotes(self):
        data = ''
        res = _convert_to_csv_form(data)
        expected = '""'
        self.assertEqual(res, expected)

    def test_integer_remains_integer(self):
        data = 5
        res = _convert_to_csv_form(data)
        expected = data
        self.assertEqual(res, expected)

    def test_unicode_is_encoded(self):
        data = u'Δοκιμή'
        res = _convert_to_csv_form(data)
        self.assertIsInstance(res, str)

    def test_encoding_for_unicode_is_utf8_(self):
        data = u'Δοκιμή'
        res = _convert_to_csv_form(data)
        expected = data.encode('UTF-8')
        self.assertEqual(res, expected)

    def test_str_is_returned_attached(self):
        data = u'Δοκιμή'
        s = data.encode('UTF-8')
        res = _convert_to_csv_form(s)
        expected = s
        self.assertEqual(res, expected)


@patch('djangopg.copy._send_csv_to_postgres')
class ColumnsTestCase(unittest.TestCase):
    """Tests for the columns used in copy."""

    def setUp(self):
        self.entries = [
            Poll(question="Question1", pub_date=datetime.now()),
            Poll(question="Question2", pub_date=datetime.now()),
        ]

    def test_all_non_pk_columns_are_used_if_none_specified(self, pmock):
        copy_insert(Poll, self.entries)
        columns = pmock.call_args[0][3]
        self.assertEqual(len(columns), 2)

    def test_specified_columns_only_are_used(self, pmock):
        copy_insert(Poll, self.entries, columns=['question'])
        columns = pmock.call_args[0][3]
        self.assertEqual(len(columns), 1)
        self.assertEqual(columns[0], 'question')

        copy_insert(Poll, self.entries, columns=['pub_date'])
        columns = pmock.call_args[0][3]
        self.assertEqual(len(columns), 1)
        self.assertEqual(columns[0], 'pub_date')

        copy_insert(Poll, self.entries, columns=['question', 'pub_date'])
        columns = pmock.call_args[0][3]
        self.assertEqual(len(columns), 2)
        self.assertEqual(columns[0], 'question')
        self.assertEqual(columns[1], 'pub_date')


@patch('djangopg.copy._convert_to_csv_form')
@patch('djangopg.copy._send_csv_to_postgres')
class PreSaveTestCase(unittest.TestCase):
    """Tests the pre-save option of copy_insert().

    If `pre_save=True`, we expect the `pre_save()` method of each field
    to be executed before invoking COPY. If the field has special pre-save
    handling, like `auto_now` for DateTime fields, the value that gets sent
    to the database will be modified first.

    If `pre_save=False`, we expect the value will stay as is.
    """

    def setUp(self):
        # Define a custom value for the `created` field
        # This field has `auto_now_add=True`, so if `pre_save()` is called
        # on it, the value sent to the database will automatically be
        # updated to the current now().
        self.datetime = datetime(year=2018, month=06, day=19)
        self.entries = [
            Article(title="My best article", created=self.datetime),
            Article(title="My second best article", created=self.datetime),
        ]

    def test_pre_save_not_called(self, mock_send_csv, mock_convert):
        """Make sure that pre_save() is not called if the option is false."""
        copy_insert(Article, self.entries, pre_save=False)
        self.assertEqual(mock_convert.call_args[0][0], self._datestr)

    def test_pre_save_called(self, mock_send_csv, mock_convert):
        """Make sure that pre_save() is called if the option is true
        or not specified.
        """
        copy_insert(Article, self.entries, pre_save=True)
        self.assertNotEqual(mock_convert.call_args[0][0], self._datestr)

        copy_insert(Article, self.entries)
        self.assertNotEqual(mock_convert.call_args[0][0], self._datestr)

    @property
    def _datestr(self):
        # Should return "2018-06-19 00:00:00"
        return self.datetime.strftime("%Y-%m-%d %H:%M:%S")

@patch('djangopg.copy._send_csv_to_postgres')
class CsvTestCase(unittest.TestCase):
    """Tests for the CSV formatting."""

    def test_csv_generated_number_of_lines(self, pmock):
        p = Poll(question='Q')
        copy_insert(Poll, [p])
        fd = StringIO(pmock.call_args[0][0])
        lines = fd.readlines()
        self.assertEqual(len(lines), 1)

    def test_csv_generated_is_valid(self, pmock):
        p = Poll(question='Q')
        copy_insert(Poll, [p])
        fd = StringIO(pmock.call_args[0][0])
        csvf = csv.reader(fd)
        rows = [row for row in csvf]
        self.assertEqual(rows[0][0], 'Q')
        self.assertEqual(rows[0][1], '')


@patch('djangopg.copy._send_csv_to_postgres')
class ForeingKeyFieldTestCase(unittest.TestCase):
    """Tests for handling of foreign key fields."""

    def test_actual_foreign_key_value_is_extracted_correctly(self, pmock):
        p = Poll(pk=1)
        c = Choice(poll=p, choice_text='Text', votes=0)
        copy_insert(Choice, [c])
        fd = pmock.call_args[0][0]
        csvf = csv.reader(fd)
        rows = [row for row in csvf]
        data = rows[0]
        self.assertEqual(int(data[0]), 1)


@patch('djangopg.copy._send_csv_to_postgres')
class EmptyStringTestCase(unittest.TestCase):
    """Test handling of empty strings."""

    def setUp(self):
        p = Poll(pk=1)
        self.c = Choice(poll=p)

    def test_empty_string_start(self, pmock):
        copy_insert(Choice, [self.c], columns=['choice_text', 'poll', 'votes'])
        csv_file = pmock.call_args[0][0]
        self.assertEqual('"",1,\n', csv_file)

    def test_empty_string_end(self, pmock):
        copy_insert(Choice, [self.c], columns=['poll', 'votes', 'choice_text'])
        csv_file = pmock.call_args[0][0]
        self.assertEqual('1,,""\n', csv_file)

    def test_empty_string_middle(self, pmock):
        copy_insert(Choice, [self.c], columns=['poll', 'choice_text', 'votes'])
        csv_file = pmock.call_args[0][0]
        self.assertEqual('1,"",\n', csv_file)

    def test_empty_string_start_newline(self, pmock):
        copy_insert(
            Choice, [self.c, self.c], columns=['choice_text', 'poll', 'votes']
        )
        csv_file = pmock.call_args[0][0]
        self.assertEqual('"",1,\n"",1,\n', csv_file)

    def test_empty_string_end_newline(self, pmock):
        copy_insert(
            Choice, [self.c, self.c], columns=['poll', 'votes', 'choice_text']
        )
        csv_file = pmock.call_args[0][0]
        self.assertEqual('1,,""\n1,,""\n', csv_file)

    def test_no_empty_string(self, pmock):
        copy_insert(
            Choice, [self.c, self.c], columns=['poll', 'choice_text', 'votes']
        )
        csv_file = pmock.call_args[0][0]
        self.assertEqual('1,"",\n1,"",\n', csv_file)
