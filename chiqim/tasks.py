
from celery import shared_task
import logging
from django.utils import timezone
from django.core.mail import send_mail, get_connection
from .models import Bildirishnoma, EmailHistory
from django.conf import settings
import smtplib
from django.db import transaction
from django.core.mail.backends.smtp import EmailBackend

logger = logging.getLogger(__name__)


@shared_task
def check_payment_reminders():
    logger.info("Starting check_payment_reminders task")
    current_date = timezone.now().date()

    # Email sozlamalarini tekshirish
    logger.info(f"EMAIL_BACKEND: {getattr(settings, 'EMAIL_BACKEND', 'Not set')}")
    logger.info(f"EMAIL_HOST: {getattr(settings, 'EMAIL_HOST', 'Not set')}")
    logger.info(f"EMAIL_PORT: {getattr(settings, 'EMAIL_PORT', 'Not set')}")
    logger.info(f"EMAIL_USE_TLS: {getattr(settings, 'EMAIL_USE_TLS', 'Not set')}")
    logger.info(f"DEFAULT_FROM_EMAIL: {getattr(settings, 'DEFAULT_FROM_EMAIL', 'Not set')}")

    notifications = list(Bildirishnoma.objects.filter(
        status__in=['pending', 'warning', 'urgent', 'overdue'],
        email_sent=False
    ))

    logger.info(f"Found {len(notifications)} notifications to process")

    for notification in notifications:
        try:
            # Null tekshirishlar
            if not notification.tolov_sana:
                logger.warning(f"Notification ID {notification.id} has no tolov_sana, skipping")
                continue

            if not notification.chiqim:
                logger.warning(f"Notification ID {notification.id} has no chiqim, skipping")
                continue

            if not notification.chiqim.xaridor:
                logger.warning(f"Notification ID {notification.id} has no xaridor, skipping")
                continue

            if not notification.chiqim.xaridor.user:
                logger.warning(f"Notification ID {notification.id} has no user, skipping")
                continue

            days_left = (notification.tolov_sana - current_date).days
            email = notification.chiqim.xaridor.user.email

            logger.info(f"Processing notification ID {notification.id}, days_left: {days_left}, email: {email}")

            if not email:
                logger.warning(f"No email address for Notification ID {notification.id}, skipping email")
                continue

            if notification.eslatish_kunlari is None:
                logger.warning(f"Notification ID {notification.id} has no eslatish_kunlari, skipping")
                continue

            if days_left <= notification.eslatish_kunlari and not notification.email_sent:
                # Truck ma'lumotlarini tekshirish
                truck_info = "Unknown Vehicle"
                if notification.chiqim.truck:
                    make = getattr(notification.chiqim.truck, 'make', 'Unknown')
                    model = getattr(notification.chiqim.truck, 'model', 'Unknown')
                    truck_info = f"{make} {model}"

                subject = f"Payment Reminder for {truck_info}"

                oyiga_tolov = getattr(notification.chiqim, 'oyiga_tolov', 0) or 0
                qoldiq_summa = getattr(notification.chiqim, 'qoldiq_summa', 0) or 0
                full_name = getattr(notification.chiqim.xaridor, 'ism_familiya', 'Valued Customer')


                message = (
                    f"Dear {full_name},\n\n"
                    f"This is a reminder from NCL TRUCK SALES INC that your monthly payment for {truck_info} is due on {notification.tolov_sana}.\n\n"
                    f"Please make sure to submit your payment on time to avoid a late fee.\n"
                    f"If you have already made the payment, please disregard this message.\n\n"
                    f"Thank you for your prompt attention.\n\n"
                    f"Sincerely,\n"
                    f"NCL TRUCK SALES INC\n"
                    f"Billing Department"
                )

                recipient_list = [email]

                # EMAIL CONNECTION ni alohida yaratish
                try:
                    # Manual connection yaratish
                    connection = get_connection(
                        backend=settings.EMAIL_BACKEND,
                        host=settings.EMAIL_HOST,
                        port=settings.EMAIL_PORT,
                        username=settings.EMAIL_HOST_USER,
                    password = settings.EMAIL_HOST_PASSWORD,
                    use_tls = settings.EMAIL_USE_TLS,
                    use_ssl = getattr(settings, 'EMAIL_USE_SSL', False),
                    timeout = 30,  # Timeout qo'shish
                    fail_silently = False,
                    )

                    logger.info(f"Attempting to send email to {email} for notification {notification.id}")

                    # Connection ochish va tekshirish
                    connection.open()
                    logger.info("SMTP connection opened successfully")

                    result = send_mail(
                        subject=subject,
                        message=message,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=recipient_list,
                        fail_silently=False,
                        connection=connection,
                    )

                    connection.close()
                    logger.info(f"Email sent successfully for Notification ID {notification.id}, result: {result}")

                    # Transaction ichida yangilash
                    with transaction.atomic():
                        EmailHistory.objects.create(
                            bildirishnoma=notification,
                            subject=subject,
                            message=message,
                            recipient=email,
                            status='success'
                        )
                        notification.email_sent = True
                        notification.save()
                        logger.info(f"Database updated for notification {notification.id}")

                except smtplib.SMTPAuthenticationError as e:
                    logger.error(f"SMTP Authentication error for Notification ID {notification.id}: {str(e)}")
                    EmailHistory.objects.create(
                        bildirishnoma=notification,
                        subject=subject,
                        message=message,
                        recipient=email,
                        status='failed',
                        error_message=f"Authentication Error: {str(e)}"
                    )
                except smtplib.SMTPRecipientsRefused as e:
                    logger.error(f"SMTP Recipients Refused for Notification ID {notification.id}: {str(e)}")
                    EmailHistory.objects.create(
                        bildirishnoma=notification,
                        subject=subject,
                        message=message,
                        recipient=email,
                        status='failed',
                        error_message=f"Recipients Refused: {str(e)}"
                    )
                except smtplib.SMTPException as e:
                    logger.error(f"SMTP error for Notification ID {notification.id}: {str(e)}")
                    EmailHistory.objects.create(
                        bildirishnoma=notification,
                        subject=subject,
                        message=message,
                        recipient=email,
                        status='failed',
                        error_message=f"SMTP Error: {str(e)}"
                    )
                except Exception as e:
                    logger.error(f"Email sending error for Notification ID {notification.id}: {str(e)}")
                    EmailHistory.objects.create(
                        bildirishnoma=notification,
                        subject=subject,
                        message=message,
                        recipient=email,
                        status='failed',
                        error_message=f"General Error: {str(e)}"
                    )

        except Exception as e:
            logger.error(f"Unexpected error processing Notification ID {notification.id}: {str(e)}")
            continue