with raw_count as (
    select count(*) as row_count
    from {{ source('revenueos_raw', 'source_event') }}
),
staging_count as (
    select count(*) as row_count
    from {{ ref('stg_source_events') }}
)
select raw_count.row_count as raw_rows, staging_count.row_count as staging_rows
from raw_count cross join staging_count
where raw_count.row_count <> staging_count.row_count
