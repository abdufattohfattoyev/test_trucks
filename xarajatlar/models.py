from django.db import models
from trucks.models import Truck
from django.utils import timezone
import os
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.core.exceptions import ValidationError
from .utils import send_to_telegram, send_file_to_telegram
from typing import Optional


def validate_file_size(value):
    """Limit file size to 50 MB."""
    limit = 50 * 1024 * 1024  # 50 MB
    if value.size > limit:
        raise ValidationError("File size must not exceed 50 MB.")


def xarajat_document_upload_path(instance, filename):
    """Generate path to save file with original name."""
    return f'xarajat_documents/{instance.truck.id}/{filename}'


class Xarajat(models.Model):
    EXPENSE_TYPES = (
        ('repair', 'Repair'),
        ('fuel', 'Fuel'),
        ('insurance', 'Insurance'),
        ('parts', 'Spare Parts'),
        ('other', 'Other'),
    )

    truck = models.ForeignKey(
        Truck,
        on_delete=models.CASCADE,
        related_name='expenses',
        verbose_name="Truck"
    )
    expense_type = models.CharField(
        max_length=50,
        choices=EXPENSE_TYPES,
        verbose_name="Expense Type"
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Amount",
        validators=[MinValueValidator(0.01)]
    )
    description = models.TextField(
        blank=True,
        verbose_name="Description"
    )
    date = models.DateField(
        verbose_name="Date",
        default=timezone.now
    )
    document = models.FileField(
        upload_to=xarajat_document_upload_path,
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'pdf', 'doc', 'docx']),
            validate_file_size
        ],
        verbose_name="Document"
    )
    original_file_name = models.CharField(
        max_length=255,
        verbose_name="Original File Name",
        blank=True,
        null=True
    )

    def get_user_full_name(self) -> str:
        """Return the full name of the user."""
        full_name = f"{self.truck.user.first_name} {self.truck.user.last_name}".strip()
        return full_name or self.truck.user.username

    def save(self, *args, **kwargs):
        is_new = not self.pk
        if self.document and not self.original_file_name:
            self.original_file_name = os.path.basename(self.document.name)

        # Limit description to 500 characters (for Telegram limit)
        description = self.description[:500] + '...' if len(self.description) > 500 else self.description or 'None'

        super().save(*args, **kwargs)

        # Prepare Telegram message
        action = "Created" if is_new else "Updated"
        action_emoji = "💰" if is_new else "🔄"
        message = (
            f"<b>{action_emoji} Expense {action}</b>\n"
            f"📅 <u>Expense Details:</u>\n"
            f"  • Type: {self.get_expense_type_display()}\n"
            f"  • Amount: ${self.amount:,.2f}\n"
            f"  • Date: {self.date}\n"
            f"  • Description: {description}\n"
            f"  • Document: <code>{self.original_file_name or 'None'}</code>\n"
            f"\n🚛 <u>Truck:</u>\n"
            f"  • PO-ID: <code>{self.truck.po_id}</code>\n"
            f"  • Make/Model: {self.truck.make} {self.truck.model}\n"
            f"  • Year: {self.truck.year}\n"
            f"  • Price: ${self.truck.price:,.2f}\n"
            f"  • Serial: {self.truck.seriya or 'None'}\n"
            f"\n👤 <u>User:</u>\n"
            f"  • Username: <code>{self.truck.user.username}</code>\n"
            f"  • Name: {self.get_user_full_name()}"
        )
        send_to_telegram(message)

        # Send document file
        if self.document:
            file_path = self.document.path
            original_filename = self.original_file_name or os.path.basename(self.document.name)
            caption = (
                f"<b>📎 Expense Document</b>\n"
                f"Truck: <code>{self.truck.po_id}</code> ({self.truck.make} {self.truck.model})\n"
                f"Expense Type: {self.get_expense_type_display()}\n"
                f"Amount: ${self.amount:,.2f}\n"
                f"File: <code>{original_filename}</code>"
            )
            send_file_to_telegram(file_path, original_filename, caption)

    def delete(self, *args, **kwargs):
        # Prepare Telegram message
        message = (
            f"<b>🗑️ Expense Deleted</b>\n"
            f"📅 <u>Expense Details:</u>\n"
            f"  • Type: {self.get_expense_type_display()}\n"
            f"  • Amount: ${self.amount:,.2f}\n"
            f"  • Date: {self.date}\n"
            f"  • Document: <code>{self.original_file_name or 'None'}</code>\n"
            f"\n🚛 <u>Truck:</u>\n"
            f"  • PO-ID: <code>{self.truck.po_id}</code>\n"
            f"  • Make/Model: {self.truck.make} {self.truck.model}\n"
            f"\n👤 <u>User:</u>\n"
            f"  • Username: <code>{self.truck.user.username}</code>\n"
            f"  • Name: {self.get_user_full_name()}"
        )
        super().delete(*args, **kwargs)
        send_to_telegram(message)

    def __str__(self):
        return f"{self.truck.make} - {self.get_expense_type_display()} - ${self.amount} ({self.date})"

    def get_document_name(self) -> Optional[str]:
        """Return the original document name."""
        if self.document:
            return self.original_file_name or os.path.basename(self.document.name)
        return None

    class Meta:
        verbose_name = "Expense"
        verbose_name_plural = "Expenses"
        ordering = ['-date']
        indexes = [
            models.Index(fields=['truck', 'expense_type']),
            models.Index(fields=['date']),
        ]