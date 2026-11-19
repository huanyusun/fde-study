"""Implement customer statistics and decisions here. The harness only handles IO."""


def profile(tables, dictionary, context):
    """Return profile_report: field statistics, anomalies and dictionary comparison."""
    raise NotImplementedError('W04_PROFILE_UNIMPLEMENTED')


def adapt(tables, rules, context):
    """Execute YAML rules, map fields, record all dispositions, and write coverage.

    Return tables, record_counts, field_mapping, samples, coverage_notes.
    See examples/w04/wutong/customer/w04/solution.py for the same interface.
    """
    raise NotImplementedError('W04_ADAPTER_UNIMPLEMENTED')


def reconcile(payload):
    """Compute adapter_test_report from raw, cleaned and both imported databases."""
    raise NotImplementedError('W04_RECONCILIATION_UNIMPLEMENTED')
