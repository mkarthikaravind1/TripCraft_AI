from django.db import migrations


def seed(apps, schema_editor):
    from support.faq_data import FAQS

    FAQ = apps.get_model("support", "FAQ")
    for order, item in enumerate(FAQS, start=1):
        FAQ.objects.update_or_create(
            question=item["question"],
            defaults={**{k: v for k, v in item.items() if k != "question"}, "order": order, "is_active": True},
        )


def unseed(apps, schema_editor):
    from support.faq_data import FAQS

    apps.get_model("support", "FAQ").objects.filter(question__in=[f["question"] for f in FAQS]).delete()


class Migration(migrations.Migration):
    dependencies = [("support", "0001_initial")]
    operations = [migrations.RunPython(seed, unseed)]
