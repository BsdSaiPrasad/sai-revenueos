with source_opportunities as (
    select
        event_id,
        source_record_id,
        source_system,
        source_tenant,
        source_object_type,
        source_object_id,
        name,
        account_source_object_id,
        stage,
        amount,
        currency_code,
        close_date as expected_close_date,
        source_updated_at,
        observed_at,
        trace_id,
        payload_sha256
    from {{ ref('stg_salesforce_opportunities') }}
    where is_latest_source_version and event_type = 'upsert' and not is_deleted

    union all

    select
        event_id,
        source_record_id,
        source_system,
        source_tenant,
        source_object_type,
        source_object_id,
        name,
        cast(null as varchar) as account_source_object_id,
        stage,
        amount,
        cast(null as varchar) as currency_code,
        close_date as expected_close_date,
        source_updated_at,
        observed_at,
        trace_id,
        payload_sha256
    from {{ ref('stg_hubspot_deals') }}
    where is_latest_source_version and event_type = 'upsert' and not is_deleted
),
current_companies as (
    select *
    from {{ ref('stg_crm_companies') }}
    where is_latest_source_version and event_type = 'upsert' and not is_deleted
)
select
    cast(null as varchar) as opportunity_id,
    opportunity.source_record_id as opportunity_source_record_id,
    opportunity.source_system,
    opportunity.source_tenant,
    opportunity.source_object_type,
    opportunity.source_object_id,
    account_mapping.canonical_entity_id as primary_account_id,
    opportunity.name,
    opportunity.stage,
    opportunity.amount,
    opportunity.currency_code,
    opportunity.expected_close_date,
    opportunity.source_updated_at,
    opportunity.observed_at,
    opportunity.trace_id,
    opportunity.payload_sha256,
    'unresolved_opportunity' as opportunity_resolution_status,
    case
        when account_mapping.canonical_entity_id is not null then 'resolved'
        else 'unresolved'
    end as primary_account_resolution_status
from source_opportunities opportunity
left join current_companies company
    on company.source_system = opportunity.source_system
   and company.source_tenant = opportunity.source_tenant
   and company.source_object_id = opportunity.account_source_object_id
left join {{ ref('int_active_identity_mappings') }} account_mapping
    on account_mapping.source_record_id = company.source_record_id
   and account_mapping.canonical_entity_type = 'Account'
