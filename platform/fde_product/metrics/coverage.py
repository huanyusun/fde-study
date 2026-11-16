"""Optional coverage provenance. Validate shape, never reinterpret client claims."""
from copy import deepcopy
from datetime import date
import re


def validate_coverage_notes(manifest):
    if 'coverage_notes' not in manifest:
        return
    notes = manifest['coverage_notes']
    if not isinstance(notes, dict):
        raise ValueError('COVERAGE_NOTES_INVALID:object')
    if not isinstance(notes.get('source'), str) or not notes['source'].strip():
        raise ValueError('COVERAGE_NOTES_INVALID:source')
    period = notes.get('time_range')
    if not isinstance(period, dict) or not {'start', 'end_exclusive'} <= set(period):
        raise ValueError('COVERAGE_NOTES_INVALID:time_range')
    for key in ['start', 'end_exclusive']:
        value = period[key]
        try:
            if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                raise ValueError()
            date.fromisoformat(value)
        except (TypeError, ValueError):
            raise ValueError('COVERAGE_NOTES_INVALID:time_range.' + key) from None
    counts = notes.get('quarantined')
    if not isinstance(counts, dict) or not {'member','order','card','shop'} <= set(counts):
        raise ValueError('COVERAGE_NOTES_INVALID:quarantined')
    if any(type(value) is not int or value < 0 for value in counts.values()):
        raise ValueError('COVERAGE_NOTES_INVALID:quarantined.count')


def with_coverage_notes(result, dataset):
    if 'coverage_notes' in dataset:
        result = {**result, 'coverage_notes': deepcopy(dataset['coverage_notes'])}
    return result
