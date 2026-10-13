with expected as (
    select account_id, observed_lifecycle_status
    from {{ ref('canonical_account_source_history') }}
    where is_latest_source_version
      and event_type = 'upsert'
      and not is_deleted
      and source_system = 'salesforce'
      and observed_lifecycle_status is not null
    qualify row_number() over (
        partition by account_id
        order by source_updated_at desc, observed_at desc, event_id desc
    ) = 1
)
select account.account_id
from {{ ref('canonical_accounts') }} account
inner join expected using (account_id)
where account.lifecycle_status <> expected.observed_lifecycle_status
