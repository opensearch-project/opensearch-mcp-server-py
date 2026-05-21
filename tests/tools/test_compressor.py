# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import json
import pytest
from pathlib import Path
from tools.compressor import (
    CompressionResult,
    _apply_replacements,
    _contains_meta_token,
    _meta_sort_key,
    compress_docs,
    compress_tsv_docs,
)


FIXTURES_DIR = Path(__file__).parent / 'fixtures'


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ecommerce_docs():
    """Simulated ecommerce docs with repeated keyword values."""
    return [
        {
            'category': "Women's Clothing",
            'currency': 'EUR',
            'customer_gender': 'FEMALE',
            'day_of_week': 'Monday',
            'city': 'New York',
            'total': 42.0,
        },
        {
            'category': "Women's Clothing",
            'currency': 'EUR',
            'customer_gender': 'FEMALE',
            'day_of_week': 'Tuesday',
            'city': 'Los Angeles',
            'total': 35.5,
        },
        {
            'category': "Men's Clothing",
            'currency': 'EUR',
            'customer_gender': 'MALE',
            'day_of_week': 'Monday',
            'city': 'New York',
            'total': 78.0,
        },
        {
            'category': "Women's Clothing",
            'currency': 'EUR',
            'customer_gender': 'FEMALE',
            'day_of_week': 'Wednesday',
            'city': 'Chicago',
            'total': 56.0,
        },
        {
            'category': "Men's Clothing",
            'currency': 'EUR',
            'customer_gender': 'MALE',
            'day_of_week': 'Monday',
            'city': 'New York',
            'total': 91.0,
        },
        {
            'category': "Women's Clothing",
            'currency': 'EUR',
            'customer_gender': 'FEMALE',
            'day_of_week': 'Thursday',
            'city': 'Los Angeles',
            'total': 23.0,
        },
        {
            'category': "Men's Clothing",
            'currency': 'EUR',
            'customer_gender': 'MALE',
            'day_of_week': 'Friday',
            'city': 'Chicago',
            'total': 67.0,
        },
        {
            'category': "Women's Clothing",
            'currency': 'EUR',
            'customer_gender': 'FEMALE',
            'day_of_week': 'Monday',
            'city': 'New York',
            'total': 44.0,
        },
    ]


@pytest.fixture
def log_docs():
    """Simulated log docs with repeated text patterns."""
    return [
        {
            'level': 'ERROR',
            'service': 'order-service',
            'message': 'Connection refused to database host db-primary.internal port 5432',
        },
        {
            'level': 'ERROR',
            'service': 'order-service',
            'message': 'Connection refused to database host db-primary.internal port 5432',
        },
        {
            'level': 'WARN',
            'service': 'order-service',
            'message': 'Connection refused to database host db-replica.internal port 5432',
        },
        {
            'level': 'ERROR',
            'service': 'payment-service',
            'message': 'Connection refused to database host db-primary.internal port 5432',
        },
        {
            'level': 'ERROR',
            'service': 'order-service',
            'message': 'Connection refused to database host db-primary.internal port 5432',
        },
        {
            'level': 'WARN',
            'service': 'payment-service',
            'message': 'Connection refused to database host db-replica.internal port 5432',
        },
    ]


# ---------------------------------------------------------------------------
# CompressionResult
# ---------------------------------------------------------------------------


class TestCompressionResult:
    def test_compression_ratio(self):
        cr = CompressionResult('text', {}, original_token_count=100, compressed_token_count=60)
        assert cr.compression_ratio == pytest.approx(0.4)

    def test_compression_ratio_zero_original(self):
        cr = CompressionResult('', {}, original_token_count=0, compressed_token_count=0)
        assert cr.compression_ratio == 0.0

    def test_format_dictionary_sorted(self):
        cr = CompressionResult('', {'<M3>': 'c', '<M1>': 'a', '<M10>': 'j', '<M2>': 'b'}, 0, 0)
        assert cr.format_dictionary() == '<M1> = a\n<M2> = b\n<M3> = c\n<M10> = j'

    def test_decompress_restores_values(self):
        cr = CompressionResult(
            compressed_text='{"status":"<M1>","code":"<M2>"}',
            dictionary={'<M1>': 'active', '<M2>': '200'},
            original_token_count=100,
            compressed_token_count=60,
        )
        assert '"active"' in cr.decompress()
        assert '"200"' in cr.decompress()
        assert '<M' not in cr.decompress()

    def test_repr(self):
        cr = CompressionResult('x', {'<M1>': 'val'}, 100, 60)
        r = repr(cr)
        assert '40.0%' in r
        assert 'dictionary_size=1' in r


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_meta_sort_key(self):
        assert _meta_sort_key('<M1>') == 1
        assert _meta_sort_key('<M10>') == 10
        assert _meta_sort_key('<M99>') == 99

    def test_contains_meta_token_true(self):
        assert _contains_meta_token(['hello', '<M1>', 'world']) is True

    def test_contains_meta_token_false(self):
        assert _contains_meta_token(['hello', 'world']) is False
        assert _contains_meta_token(['<M1>partial']) is False

    def test_apply_replacements(self):
        tokens = ['a', 'b', 'c', 'a', 'b', 'c']
        selected = [(('a', 'b', 'c'), [0, 3], '<M1>')]
        result = _apply_replacements(tokens, selected)
        assert result == ['<M1>', '<M1>']

    def test_apply_replacements_partial(self):
        tokens = ['a', 'b', 'c', 'd', 'a', 'b']
        selected = [(('a', 'b'), [0, 4], '<M1>')]
        result = _apply_replacements(tokens, selected)
        assert result == ['<M1>', 'c', 'd', '<M1>']


# ---------------------------------------------------------------------------
# compress_docs
# ---------------------------------------------------------------------------


class TestCompressDocs:
    def test_empty_docs(self):
        cr = compress_docs([])
        assert cr.compressed_text == ''
        assert cr.dictionary == {}

    def test_single_doc_no_compression(self):
        cr = compress_docs([{'a': 'unique_value'}])
        assert cr.dictionary == {}
        parsed = json.loads(cr.compressed_text)
        assert parsed['a'] == 'unique_value'

    def test_repeated_values_compressed(self, ecommerce_docs):
        cr = compress_docs(ecommerce_docs)
        assert len(cr.dictionary) > 0
        assert cr.compression_ratio > 0
        for meta in cr.dictionary:
            assert meta in cr.compressed_text

    def test_lossless_json(self, ecommerce_docs):
        cr = compress_docs(ecommerce_docs)
        compressed_lines = cr.compressed_text.strip().split('\n')
        assert len(compressed_lines) == len(ecommerce_docs)
        for line in compressed_lines:
            restored = line
            for meta, val in cr.dictionary.items():
                restored = restored.replace(meta, val)
            parsed = json.loads(restored)
            assert isinstance(parsed, dict)

    def test_skip_fields_bypasses_numeric(self, ecommerce_docs):
        cr_skip = compress_docs(ecommerce_docs, skip_fields={'total'})
        skip_metas = set(cr_skip.dictionary.values())
        for doc in ecommerce_docs:
            assert str(doc['total']) not in skip_metas

    def test_skip_fields_preserves_raw_values(self, ecommerce_docs):
        cr = compress_docs(ecommerce_docs, skip_fields={'total', 'currency'})
        for line in cr.compressed_text.strip().split('\n'):
            obj = json.loads(line)
            assert isinstance(obj.get('total', 0), (int, float))

    def test_text_fields_substring_compression(self, log_docs):
        cr = compress_docs(log_docs, text_fields={'message'})
        assert cr.compression_ratio > 0

    def test_l_max_parameter(self, log_docs):
        cr_default = compress_docs(log_docs, text_fields={'message'})
        cr_short = compress_docs(log_docs, text_fields={'message'}, l_max=2)
        assert cr_default.compressed_token_count <= cr_default.original_token_count
        assert cr_short.compressed_token_count <= cr_short.original_token_count

    def test_field_order_preserved(self):
        docs = [
            {'z_field': 'a', 'a_field': 'b', 'm_field': 'c'},
            {'z_field': 'a', 'a_field': 'b', 'm_field': 'c'},
        ]
        cr = compress_docs(docs)
        first_line = json.loads(cr.compressed_text.split('\n')[0])
        assert list(first_line.keys()) == ['z_field', 'a_field', 'm_field']

    def test_missing_fields_handled(self):
        docs = [
            {'a': 'val1', 'b': 'val2'},
            {'a': 'val1'},
            {'a': 'val1', 'b': 'val2', 'c': 'val3'},
        ]
        cr = compress_docs(docs)
        lines = cr.compressed_text.strip().split('\n')
        assert len(lines) == 3


# ---------------------------------------------------------------------------
# compress_tsv_docs
# ---------------------------------------------------------------------------


class TestCompressTsvDocs:
    def test_empty_docs(self):
        cr = compress_tsv_docs([])
        assert cr.compressed_text == ''
        assert cr.dictionary == {}

    def test_header_row_present(self, ecommerce_docs):
        cr = compress_tsv_docs(ecommerce_docs)
        header = cr.compressed_text.split('\n')[0]
        for field in ecommerce_docs[0]:
            assert field in header

    def test_tab_separated(self, ecommerce_docs):
        cr = compress_tsv_docs(ecommerce_docs)
        lines = cr.compressed_text.strip().split('\n')
        header_cols = lines[0].split('\t')
        for line in lines[1:]:
            assert len(line.split('\t')) == len(header_cols)

    def test_repeated_values_compressed(self, ecommerce_docs):
        cr = compress_tsv_docs(ecommerce_docs)
        assert len(cr.dictionary) > 0
        assert cr.compression_ratio > 0

    def test_lossless_tsv(self, ecommerce_docs):
        cr = compress_tsv_docs(ecommerce_docs)
        lines = cr.compressed_text.strip().split('\n')
        header = lines[0].split('\t')
        for row in lines[1:]:
            cells = row.split('\t')
            restored = []
            for cell in cells:
                for meta, val in cr.dictionary.items():
                    cell = cell.replace(meta, val)
                restored.append(cell)
            assert len(restored) == len(header)

    def test_skip_fields_bypasses_numeric(self, ecommerce_docs):
        cr = compress_tsv_docs(ecommerce_docs, skip_fields={'total'})
        lines = cr.compressed_text.strip().split('\n')
        header = lines[0].split('\t')
        total_idx = header.index('total')
        for row in lines[1:]:
            cell = row.split('\t')[total_idx]
            assert '<M' not in cell

    def test_tsv_more_compact_than_json(self, ecommerce_docs):
        cr_json = compress_docs(ecommerce_docs)
        cr_tsv = compress_tsv_docs(ecommerce_docs)
        assert cr_tsv.compressed_token_count <= cr_json.compressed_token_count

    def test_text_fields_substring_compression(self, log_docs):
        cr = compress_tsv_docs(log_docs, text_fields={'message'})
        assert cr.compression_ratio > 0

    def test_l_max_parameter(self, log_docs):
        cr = compress_tsv_docs(log_docs, text_fields={'message'}, l_max=3)
        assert cr.compressed_token_count <= cr.original_token_count


# ---------------------------------------------------------------------------
# Expected output matching
# ---------------------------------------------------------------------------


class TestCompressDocsExpectedOutput:
    def test_ecommerce_expected(self, ecommerce_docs):
        cr = compress_docs(ecommerce_docs, skip_fields={'total'})
        assert cr.dictionary == {'<M1>': "Women's Clothing"}
        assert cr.compressed_text == (
            '{"category":"<M1>","currency":"EUR","customer_gender":"FEMALE","day_of_week":"Monday","city":"New York","total":42.0}\n'
            '{"category":"<M1>","currency":"EUR","customer_gender":"FEMALE","day_of_week":"Tuesday","city":"Los Angeles","total":35.5}\n'
            '{"category":"Men\'s Clothing","currency":"EUR","customer_gender":"MALE","day_of_week":"Monday","city":"New York","total":78.0}\n'
            '{"category":"<M1>","currency":"EUR","customer_gender":"FEMALE","day_of_week":"Wednesday","city":"Chicago","total":56.0}\n'
            '{"category":"Men\'s Clothing","currency":"EUR","customer_gender":"MALE","day_of_week":"Monday","city":"New York","total":91.0}\n'
            '{"category":"<M1>","currency":"EUR","customer_gender":"FEMALE","day_of_week":"Thursday","city":"Los Angeles","total":23.0}\n'
            '{"category":"Men\'s Clothing","currency":"EUR","customer_gender":"MALE","day_of_week":"Friday","city":"Chicago","total":67.0}\n'
            '{"category":"<M1>","currency":"EUR","customer_gender":"FEMALE","day_of_week":"Monday","city":"New York","total":44.0}'
        )

    def test_log_docs_expected(self, log_docs):
        cr = compress_docs(log_docs, text_fields={'message'})
        assert cr.dictionary == {
            '<M1>': 'Connection refused to database host db-primary.internal port 5432',
            '<M2>': 'Connection refused to database host db-replica.internal port 5432',
        }
        assert cr.compressed_text == (
            '{"level":"ERROR","service":"order-service","message":"<M1>"}\n'
            '{"level":"ERROR","service":"order-service","message":"<M1>"}\n'
            '{"level":"WARN","service":"order-service","message":"<M2>"}\n'
            '{"level":"ERROR","service":"payment-service","message":"<M1>"}\n'
            '{"level":"ERROR","service":"order-service","message":"<M1>"}\n'
            '{"level":"WARN","service":"payment-service","message":"<M2>"}'
        )
        assert cr.compression_ratio > 0.25


class TestCompressTsvDocsExpectedOutput:
    def test_ecommerce_expected(self, ecommerce_docs):
        cr = compress_tsv_docs(ecommerce_docs, skip_fields={'total'})
        assert cr.dictionary == {'<M1>': "Women's Clothing"}
        assert cr.compressed_text == (
            'category\tcurrency\tcustomer_gender\tday_of_week\tcity\ttotal\n'
            '<M1>\tEUR\tFEMALE\tMonday\tNew York\t42.0\n'
            '<M1>\tEUR\tFEMALE\tTuesday\tLos Angeles\t35.5\n'
            "Men's Clothing\tEUR\tMALE\tMonday\tNew York\t78.0\n"
            '<M1>\tEUR\tFEMALE\tWednesday\tChicago\t56.0\n'
            "Men's Clothing\tEUR\tMALE\tMonday\tNew York\t91.0\n"
            '<M1>\tEUR\tFEMALE\tThursday\tLos Angeles\t23.0\n'
            "Men's Clothing\tEUR\tMALE\tFriday\tChicago\t67.0\n"
            '<M1>\tEUR\tFEMALE\tMonday\tNew York\t44.0'
        )

    def test_log_docs_expected(self, log_docs):
        cr = compress_tsv_docs(log_docs, text_fields={'message'})
        assert cr.dictionary == {
            '<M1>': 'Connection refused to database host db-primary.internal port 5432',
            '<M2>': 'Connection refused to database host db-replica.internal port 5432',
        }
        assert cr.compressed_text == (
            'level\tservice\tmessage\n'
            'ERROR\torder-service\t<M1>\n'
            'ERROR\torder-service\t<M1>\n'
            'WARN\torder-service\t<M2>\n'
            'ERROR\tpayment-service\t<M1>\n'
            'ERROR\torder-service\t<M1>\n'
            'WARN\tpayment-service\t<M2>'
        )
        assert cr.compression_ratio > 0.35

    def test_tsv_better_than_json_for_logs(self, log_docs):
        cr_json = compress_docs(log_docs, text_fields={'message'})
        cr_tsv = compress_tsv_docs(log_docs, text_fields={'message'})
        assert cr_tsv.compression_ratio > cr_json.compression_ratio


# ---------------------------------------------------------------------------
# Decompress round-trip
# ---------------------------------------------------------------------------


class TestDecompressRoundTrip:
    def test_compress_docs_round_trip(self, ecommerce_docs):
        cr = compress_docs(ecommerce_docs)
        decompressed = cr.decompress()
        original_lines = cr.compressed_text
        for meta, val in cr.dictionary.items():
            original_lines = original_lines.replace(meta, val)
        assert decompressed == original_lines

    def test_compress_tsv_round_trip(self, ecommerce_docs):
        cr = compress_tsv_docs(ecommerce_docs)
        decompressed = cr.decompress()
        assert '<M' not in decompressed
        lines = decompressed.strip().split('\n')
        assert len(lines) == len(ecommerce_docs) + 1  # header + data rows


# ---------------------------------------------------------------------------
# Train-ticket logs (realistic 50-doc fixture)
# ---------------------------------------------------------------------------


@pytest.fixture
def train_ticket_docs():
    """50 realistic log documents from a train-ticket microservice system."""
    data = json.loads((FIXTURES_DIR / 'train_ticket_logs.json').read_text())
    return [hit['_source'] for hit in data['hits']['hits']]


class TestTrainTicketLogs:
    def test_compress_tsv_produces_output(self, train_ticket_docs):
        cr = compress_tsv_docs(
            train_ticket_docs, text_fields={'message'}, skip_fields={'timestamp'}
        )
        assert cr.compressed_text != ''
        lines = cr.compressed_text.strip().split('\n')
        assert len(lines) == 51  # header + 50 data rows

    def test_compression_ratio(self, train_ticket_docs):
        cr = compress_tsv_docs(
            train_ticket_docs, text_fields={'message'}, skip_fields={'timestamp'}
        )
        assert cr.compression_ratio > 0

    def test_lossless_round_trip(self, train_ticket_docs):
        cr = compress_tsv_docs(
            train_ticket_docs, text_fields={'message'}, skip_fields={'timestamp'}
        )
        decompressed = cr.decompress()
        assert '<M' not in decompressed
        lines = decompressed.split('\n')
        header = lines[0].split('\t')
        assert 'container_name' in header
        assert 'message' in header
        for row in lines[1:]:
            if not row:
                continue
            assert len(row.split('\t')) == len(header)

    def test_json_compression(self, train_ticket_docs):
        cr = compress_docs(train_ticket_docs, text_fields={'message'}, skip_fields={'timestamp'})
        assert cr.compression_ratio > 0
        lines = cr.compressed_text.strip().split('\n')
        assert len(lines) == 50
