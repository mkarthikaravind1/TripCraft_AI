from django.db import migrations


def seed(apps, schema_editor):
    from support.services.errors import DEFAULTS, REQUIRED_CODES

    ErrorCode = apps.get_model("support", "ErrorCode")
    for order, code in enumerate(REQUIRED_CODES, start=1):
        entry = DEFAULTS[code]
        ErrorCode.objects.update_or_create(
            code=entry.code,
            defaults={
                "http_status": entry.http_status,
                "title": entry.title,
                "meaning": entry.meaning,
                "causes": list(entry.causes),
                "user_action": entry.user_action,
                "troubleshooting": list(entry.troubleshooting),
                "where_seen": entry.where_seen,
                "keywords": list(entry.keywords),
                "order": order,
                "is_active": True,
            },
        )


def unseed(apps, schema_editor):
    from support.services.errors import REQUIRED_CODES

    apps.get_model("support", "ErrorCode").objects.filter(code__in=REQUIRED_CODES).delete()


class Migration(migrations.Migration):
    dependencies = [("support", "0003_errorcode")]
    operations = [migrations.RunPython(seed, unseed)]
