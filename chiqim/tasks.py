from celery import shared_task
import logging
from django.utils import timezone
from django.core.mail import send_mail
from .models import Bildirishnoma, EmailHistory
from django.conf import settings
import smtplib

logger = logging.getLogger(__name__)

@shared_task
def check_payment_reminders():
    logger.info("Starting check_payment_reminders task")
    current_date = timezone.now().date()
    notifications = Bildirishnoma.objects.filter(
        status__in=['pending', 'warning', 'urgent', 'overdue'],
        email_sent=False
    )
    logger.info(f"Found {len(notifications)} notifications to process")

    for notification in notifications:
        days_left = (notification.tolov_sana - current_date).days
        email = notification.chiqim.xaridor.user.email
        logger.info(f"Processing notification ID {notification.id}, days_left: {days_left}, email: {email}")

        if not email:
            logger.warning(f"No email address for Notification ID {notification.id}, skipping email")
            continue

        if days_left <= notification.eslatish_kunlari and not notification.email_sent:
            subject = f"Payment Reminder for {notification.chiqim.truck.make} {notification.chiqim.truck.model}"
            message = (
                f"Assalomu alaykum, {notification.chiqim.xaridor.ism_familiya},\n\n"
                f"Sizning {notification.chiqim.truck.make} {notification.chiqim.truck.model} uchun to'lov muddati yaqinlashmoqda.\n"
                f"To'lov summasi: ${notification.chiqim.oyiga_tolov:,.2f}\n"
                f"To'lov sanasi: {notification.tolov_sana}\n"
                f"Qoldiq summa: ${notification.chiqim.qoldiq_summa:,.2f}\n\n"
                f"Iltimos, to'lovni o'z vaqtida amalga oshiring.\n"
                f"Rahmat!"
            )
            recipient_list = [email]

            try:
                result = send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=recipient_list,
                    fail_silently=False,
                )
                logger.info(f"Email sent for Notification ID {notification.id}, result: {result}")
                if result == 0:
                    logger.warning(f"No email sent for Notification ID {notification.id}, check SMTP settings")
                    EmailHistory.objects.create(
                        bildirishnoma=notification,
                        subject=subject,
                        message=message,
                        recipient=email,
                        status='failed',
                        error_message="No email sent, possibly invalid recipient or SMTP issue"
                    )
                else:
                    EmailHistory.objects.create(
                        bildirishnoma=notification,
                        subject=subject,
                        message=message,
                        recipient=email,
                        status='success'
                    )
                    notification.email_sent = True
                    notification.save()
            except smtplib.SMTPException as e:
                logger.error(f"SMTP error for Notification ID {notification.id}: {str(e)}")
                EmailHistory.objects.create(
                    bildirishnoma=notification,
                    subject=subject,
                    message=message,
                    recipient=email,
                    status='failed',
                    error_message=str(e)
                )
            except Exception as e:
                logger.error(f"Unexpected error for Notification ID {notification.id}: {str(e)}")
    return None