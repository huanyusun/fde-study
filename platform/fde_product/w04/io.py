"""Strict CSV IO preserves strings and CSV record positions (not physical lines)."""
import csv
import hashlib
import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker
import yaml

ROOT = Path(__file__).resolve().parents[3]
RECORD_TABLES = {'member': 'members', 'order': 'orders', 'card': 'cards', 'shop': 'stores'}


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_csv(path, *, encoding='utf-8-sig', delimiter=',', expected_fields=None):
    path = Path(path)
    with path.open(encoding=encoding, newline='') as handle:
        reader = csv.reader(handle, delimiter=delimiter, strict=True)
        header = next(reader, None)
        if not header or any(not x.strip() for x in header) or len(set(header)) != len(header):
            raise ValueError('CSV_HEADER_INVALID:' + path.name)
        if expected_fields is not None and header != list(expected_fields):
            raise ValueError('CSV_HEADER_MISMATCH:' + path.name)
        rows = []
        for index, values in enumerate(reader, 1):
            if len(values) != len(header):
                raise ValueError(f'CSV_WIDTH_MISMATCH:{path.name}:record={index}:expected={len(header)}:actual={len(values)}')
            rows.append({'source_file': path.name, 'source_row': index, 'raw': dict(zip(header, values))})
    return {'fields': header, 'rows': rows}


def read_inputs(folder, *, encoding='utf-8-sig'):
    paths = sorted(Path(folder).glob('*.csv'))
    if not paths:
        raise ValueError('NO_SOURCE_CSV')
    return {path.name: read_csv(path, encoding=encoding) for path in paths}


def write_csv(path, fields, records):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator='\n', extrasaction='raise')
        writer.writeheader()
        writer.writerows(records)


def validate(name, value):
    schema = read_json(ROOT / 'contracts/w04' / (name + '.schema.json'))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)
    return value


def load_rules(path):
    return validate('cleaning_rules', yaml.safe_load(Path(path).read_text(encoding='utf-8-sig')))


def report(path, name, value):
    validate(name, value)
    dump(path, value)
    return value
