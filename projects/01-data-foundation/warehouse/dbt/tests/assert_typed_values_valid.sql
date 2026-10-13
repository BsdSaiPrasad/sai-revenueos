select event_id, 'salesforce_opportunity_amount_or_date' as invalid_field
from {{ ref('stg_salesforce_opportunities') }}
where not is_amount_valid or not is_close_date_valid
union all
select event_id, 'hubspot_deal_amount_or_date' as invalid_field
from {{ ref('stg_hubspot_deals') }}
where not is_amount_valid or not is_close_date_valid
