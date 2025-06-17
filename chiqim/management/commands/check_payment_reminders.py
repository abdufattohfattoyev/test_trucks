from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from chiqim.models import Bildirishnoma, EmailHistory
import logging
import smtplib

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Check payment reminders and send emails'

    def handle(self, *args, **kwargs):
        current_date = timezone.now().date()
        notifications = Bildirishnoma.objects.filter(status__in=['pending', 'warning', 'urgent', 'overdue'])

        for notification in notifications:
            days_left = (notification.tolov_sana - current_date).days
            is_overdue = days_left < 0
            is_near_due = 0 <= days_left <= 5

            if (is_near_due or is_overdue) and notification.status != 'paid':
                subject = f"Payment Reminder - Due on {notification.tolov_sana}"
                message = (
                    f"Dear {notification.chiqim.xaridor.ism_familiya},\n\n"
                    f"This is a reminder for your payment due on {notification.tolov_sana}.\n"
                    f"Vehicle: {notification.chiqim.truck.make} {notification.chiqim.truck.model} (PO ID: {notification.chiqim.truck.po_id})\n"
                    f"Remaining Amount: ${notification.chiqim.qoldiq_summa:,.2f}\n"
                    f"Monthly Payment: ${notification.chiqim.oyiga_tolov:,.2f}\n"
                    f"Days Left: {days_left if days_left >= 0 else 'Overdue by ' + str(abs(days_left)) + ' days'}\n\n"
                    f"Please make the payment as soon as possible to avoid penalties.\n\n"
                    f"Best regards,\nYour Admin Team"
                )
                from_email = settings.DEFAULT_FROM_EMAIL
                recipient_list = [notification.chiqim.xaridor.user.email]

                try:
                    # SMTP ulanishini sinash
                    smtp_server = smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT)
                    smtp_server.starttls()
                    smtp_server.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
                    logger.info(f"SMTP login successful for {settings.EMAIL_HOST_USER}")

                    result = send_mail(
                        subject,
                        message,
                        from_email,
                        recipient_list,
                        fail_silently=False,
                    )
                    smtp_server.quit()

                    email_history = EmailHistory.objects.create(
                        bildirishnoma=notification,
                        subject=subject,
                        message=message,
                        recipient=notification.chiqim.xaridor.user.email,
                        status='success' if result == 1 else 'failed',
                        error_message='No error' if result == 1 else f'Email not sent, result: {result}'
                    )
                    if result == 1:
                        logger.info(f"Email sent successfully for Notification ID {notification.id}, result: {result}")
                    else:
                        logger.error(f"Email failed to send for Notification ID {notification.id}, result: {result}")
                except Exception as e:
                    email_history = EmailHistory.objects.create(
                        bildirishnoma=notification,
                        subject=subject,
                        message=message,
                        recipient=notification.chiqim.xaridor.user.email,
                        status='error',
                        error_message=str(e)
                    )
                    logger.error(f"Error sending email for Notification ID {notification.id}: {str(e)}")

                notification.update_status()

        logger.info(f"Checked {len(notifications)} payment reminders at {timezone.now()}")
        self.stdout.write(self.style.SUCCESS('Payment reminders checked'))