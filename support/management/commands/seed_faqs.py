from django.core.management.base import BaseCommand

from support.faq_data import FAQS
from support.models import FAQ


class Command(BaseCommand):
    help = "Create or update the help-centre FAQs (safe to run repeatedly)."

    def handle(self, *args, **options):
        created = 0
        for order, item in enumerate(FAQS, start=1):
            _, was_created = FAQ.objects.update_or_create(
                question=item["question"],
                defaults={**{k: v for k, v in item.items() if k != "question"}, "order": order, "is_active": True},
            )
            created += was_created
        self.stdout.write(self.style.SUCCESS(f"FAQs ready: {len(FAQS)} total, {created} newly created."))
