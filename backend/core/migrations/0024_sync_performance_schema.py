# Generated manually to sync DB schema with core models

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0023_webvitalsresult_qualitymetricssnapshot_and_more'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            ALTER TABLE core_qualitymetricssnapshot ADD COLUMN IF NOT EXISTS performance_score double precision DEFAULT 0 NULL;
            ALTER TABLE core_performancethreshold ADD COLUMN IF NOT EXISTS updated_at timestamp with time zone DEFAULT NOW();
            ALTER TABLE core_loadtestresult ADD COLUMN IF NOT EXISTS method varchar(10) DEFAULT 'GET';
            ALTER TABLE core_loadtestresult ADD COLUMN IF NOT EXISTS url_pattern varchar(1000) DEFAULT '';
            ALTER TABLE core_loadtestresult ADD COLUMN IF NOT EXISTS duration_seconds integer DEFAULT 30;
            ALTER TABLE core_loadtestresult ADD COLUMN IF NOT EXISTS successful_requests integer DEFAULT 0;
            ALTER TABLE core_loadtestresult ADD COLUMN IF NOT EXISTS max_ms double precision DEFAULT 0;
            ALTER TABLE core_webvitalsresult ADD COLUMN IF NOT EXISTS cls_score double precision NULL;
            ALTER TABLE core_webvitalsresult ADD COLUMN IF NOT EXISTS transfer_size_kb double precision NULL;
            ALTER TABLE core_webvitalsresult DROP COLUMN IF EXISTS cls;
            ALTER TABLE core_webvitalsresult ALTER COLUMN lcp_ms DROP NOT NULL;
            ALTER TABLE core_webvitalsresult ALTER COLUMN ttfb_ms DROP NOT NULL;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
