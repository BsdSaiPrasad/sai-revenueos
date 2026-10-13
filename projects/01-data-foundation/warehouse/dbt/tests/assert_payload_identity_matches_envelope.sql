select event_id, source_system, source_object_type, source_object_id, payload_source_object_id
from {{ ref('stg_salesforce_accounts') }}
where payload_source_object_id is null or payload_source_object_id <> source_object_id
union all
select event_id, source_system, source_object_type, source_object_id, payload_source_object_id
from {{ ref('stg_salesforce_leads') }}
where payload_source_object_id is null or payload_source_object_id <> source_object_id
union all
select event_id, source_system, source_object_type, source_object_id, payload_source_object_id
from {{ ref('stg_salesforce_contacts') }}
where payload_source_object_id is null or payload_source_object_id <> source_object_id
union all
select event_id, source_system, source_object_type, source_object_id, payload_source_object_id
from {{ ref('stg_salesforce_opportunities') }}
where payload_source_object_id is null or payload_source_object_id <> source_object_id
union all
select event_id, source_system, source_object_type, source_object_id, payload_source_object_id
from {{ ref('stg_hubspot_companies') }}
where payload_source_object_id is null or payload_source_object_id <> source_object_id
union all
select event_id, source_system, source_object_type, source_object_id, payload_source_object_id
from {{ ref('stg_hubspot_contacts') }}
where payload_source_object_id is null or payload_source_object_id <> source_object_id
union all
select event_id, source_system, source_object_type, source_object_id, payload_source_object_id
from {{ ref('stg_hubspot_deals') }}
where payload_source_object_id is null or payload_source_object_id <> source_object_id
