with current_people as (
    select *
    from {{ ref('stg_crm_people') }}
    where is_latest_source_version and event_type = 'upsert' and not is_deleted
      and employer_source_object_id is not null
),
current_companies as (
    select *
    from {{ ref('stg_crm_companies') }}
    where is_latest_source_version and event_type = 'upsert' and not is_deleted
)
select
    person_mapping.canonical_entity_id as person_id,
    account_mapping.canonical_entity_id as account_id,
    'employment' as relationship_type,
    person.job_title,
    person.source_record_id as person_source_record_id,
    company.source_record_id as account_source_record_id,
    person.source_updated_at as evidence_updated_at,
    person.event_id as evidence_event_id,
    'resolved_input' as relationship_status
from current_people person
inner join {{ ref('int_active_identity_mappings') }} person_mapping
    on person_mapping.source_record_id = person.source_record_id
   and person_mapping.canonical_entity_type = 'Person'
inner join current_companies company
    on company.source_system = person.source_system
   and company.source_tenant = person.source_tenant
   and company.source_object_id = person.employer_source_object_id
inner join {{ ref('int_active_identity_mappings') }} account_mapping
    on account_mapping.source_record_id = company.source_record_id
   and account_mapping.canonical_entity_type = 'Account'
