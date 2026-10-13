select account.account_id
from {{ ref('canonical_accounts') }} account
left join {{ ref('canonical_identity_crosswalks') }} mapping
    on mapping.canonical_entity_type = 'Account'
   and mapping.canonical_entity_id = account.account_id
where mapping.canonical_entity_id is null
