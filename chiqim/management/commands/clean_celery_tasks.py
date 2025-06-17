from django.core.management.base import BaseCommand
from django_celery_beat.models import PeriodicTask

class Command(BaseCommand):
    help = 'Remove unwanted Celery periodic tasks'

    def handle(self, *args, **kwargs):
        unwanted_task = 'chiqim.tasks.check_twilio_balance_task'
        tasks = PeriodicTask.objects.filter(task=unwanted_task)
        count = tasks.count()
        if count > 0:
            tasks.delete()
            self.stdout.write(self.style.SUCCESS(f'Successfully deleted {count} instances of {unwanted_task}'))
        else:
            self.stdout.write(self.style.SUCCESS(f'No instances of {unwanted_task} found'))