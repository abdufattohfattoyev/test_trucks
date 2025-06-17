from django.core.management.base import BaseCommand
from django.utils import timezone
from chiqim.models import Bildirishnoma
from django.db import transaction

class Command(BaseCommand):
    help = 'Bildirishnoma statuslarini kunlik yangilash'

    def handle(self, *args, **kwargs):
        with transaction.atomic():
            for bildirishnoma in Bildirishnoma.objects.filter(is_archived=False):
                bildirishnoma.save()
        self.stdout.write(self.style.SUCCESS('Bildirishnoma statuslari yangilandi'))