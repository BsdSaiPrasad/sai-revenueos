select mapping.source_record_id, staged.event_id
from {{ ref('int_active_identity_mappings') }} mapping
inner join {{ ref('stg_crm_companies') }} staged
    on staged.source_record_id = mapping.source_record_id
left join {{ ref('canonical_account_source_history') }} history
    on history.source_record_id = staged.source_record_id
   and history.event_id = staged.event_id
where mapping.canonical_entity_type = 'Account'
  and history.event_id is null
