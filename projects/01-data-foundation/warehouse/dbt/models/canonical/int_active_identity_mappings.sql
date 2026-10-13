with latest_publication as (
    select publication_id
    from {{ source('p18_identity', 'p18_identity_mapping_publication') }}
    qualify row_number() over (
        order by try_to_timestamp_tz(generated_at) desc, loaded_at desc, publication_id desc
    ) = 1
)

select
    mapping.publication_id,
    mapping.external_identity_crosswalk_id,
    mapping.source_record_id,
    mapping.canonical_entity_type,
    mapping.canonical_entity_id,
    mapping.mapping_status,
    mapping.mapping_method,
    mapping.confidence,
    try_to_timestamp_tz(mapping.valid_from) as valid_from,
    try_to_timestamp_tz(mapping.valid_to) as valid_to,
    mapping.reviewed_by,
    try_to_timestamp_tz(mapping.reviewed_at) as reviewed_at
from {{ source('p18_identity', 'p18_approved_identity_mapping') }} mapping
inner join latest_publication using (publication_id)
where mapping.mapping_status = 'active'
