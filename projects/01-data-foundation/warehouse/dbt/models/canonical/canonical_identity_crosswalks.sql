select
    external_identity_crosswalk_id,
    source_record_id,
    canonical_entity_type,
    canonical_entity_id,
    mapping_status,
    mapping_method,
    confidence,
    valid_from,
    valid_to,
    reviewed_by,
    reviewed_at,
    publication_id
from {{ ref('int_active_identity_mappings') }}
