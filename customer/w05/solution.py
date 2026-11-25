"""Customer TODOs. The platform provides IO, contracts, graph/conflict checks and runtime."""
def identity_evidence(accounts,materials):
    """Return accepted same/different/unresolved edges with source rows and rule version.
    Names, masked phones and devices alone cannot establish verified identity.
    """
    raise NotImplementedError('CUSTOMER_IDENTITY_RULES_REQUIRED')

def member_attributes(member_id,source_records):
    """Return attributes/conflicts with provenance; preserve multi-store relationships."""
    raise NotImplementedError('CUSTOMER_MEMBER_ADAPTER_REQUIRED')

def contact_constraints(member_id,source_records,materials,channel):
    """Apply confirmed customer rules to structured evidence; unknown is not permission."""
    raise NotImplementedError('CUSTOMER_CONTACT_RULES_REQUIRED')
