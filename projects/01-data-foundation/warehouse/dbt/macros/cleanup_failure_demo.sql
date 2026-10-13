{% macro cleanup_failure_demo() %}
    {% set failure_table = target.database ~ '.' ~ target.schema ~ '.P17_INVALID_GLOBEX' %}
    {% do run_query('drop table if exists ' ~ failure_table) %}
    {{ log('Removed isolated failure-demo table ' ~ failure_table, info=True) }}
{% endmacro %}
