select unresolved.source_record_id
from {{ ref('unresolved_identity_records') }} unresolved
inner join {{ ref('canonical_identity_crosswalks') }} mapping
    on mapping.source_record_id = unresolved.source_record_id
