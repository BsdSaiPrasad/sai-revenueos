select
    source_system,
    source_tenant,
    source_object_type,
    source_object_id,
    count_if(is_latest_source_version) as latest_versions
from {{ ref('stg_source_events') }}
group by 1, 2, 3, 4
having count_if(is_latest_source_version) <> 1
