with account_ids as (
    select
        canonical_entity_id as account_id,
        min(valid_from) as created_at,
        max(reviewed_at) as identity_reviewed_at
    from {{ ref('int_active_identity_mappings') }}
    where canonical_entity_type = 'Account'
    group by canonical_entity_id
),
current_sources as (
    select *
    from {{ ref('canonical_account_source_history') }}
    where is_latest_source_version and event_type = 'upsert' and not is_deleted
),
authoritative_lifecycle as (
    select account_id, observed_lifecycle_status as lifecycle_status
    from current_sources
    where source_system = 'salesforce' and observed_lifecycle_status is not null
    qualify row_number() over (
        partition by account_id
        order by source_updated_at desc, observed_at desc, event_id desc
    ) = 1
),
source_summary as (
    select
        account_id,
        count(distinct source_record_id) as resolved_source_count,
        max(source_updated_at) as latest_source_updated_at
    from current_sources
    group by account_id
),
conflict_summary as (
    select
        source_current.account_id,
        count_if(
            source_current.source_system <> 'salesforce'
            and source_current.observed_lifecycle_status is not null
            and authoritative.lifecycle_status is not null
            and source_current.observed_lifecycle_status <> authoritative.lifecycle_status
        ) > 0 as has_lifecycle_conflict
    from current_sources source_current
    left join authoritative_lifecycle authoritative using (account_id)
    group by source_current.account_id
)
select
    account.account_id,
    'organization' as account_type,
    authoritative.lifecycle_status,
    cast(null as timestamp_tz) as customer_since_at,
    cast(null as timestamp_tz) as ended_customer_at,
    account.created_at,
    greatest_ignore_nulls(summary.latest_source_updated_at, account.identity_reviewed_at) as updated_at,
    coalesce(summary.resolved_source_count, 0) as resolved_source_count,
    coalesce(conflict.has_lifecycle_conflict, false) as has_lifecycle_conflict,
    cast(null as varchar) as governed_account_name,
    cast(null as varchar) as governed_primary_domain
from account_ids account
left join authoritative_lifecycle authoritative using (account_id)
left join source_summary summary using (account_id)
left join conflict_summary conflict using (account_id)
