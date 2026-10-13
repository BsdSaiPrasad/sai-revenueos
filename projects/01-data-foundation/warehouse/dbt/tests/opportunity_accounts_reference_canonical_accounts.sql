select opportunity.opportunity_source_record_id
from {{ ref('canonical_opportunity_inputs') }} opportunity
left join {{ ref('canonical_accounts') }} account
    on account.account_id = opportunity.primary_account_id
where opportunity.primary_account_id is not null
  and account.account_id is null
