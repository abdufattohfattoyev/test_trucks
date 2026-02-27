from django.db import models
from django.contrib.auth.models import User
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

def qarz_document_upload_path(instance, filename):
    """Generate path to save file with original name."""
    truck_id = instance.truck.id if instance.truck else 'no_truck'
    return f'qarz_documents/{truck_id}/{filename}'

class Qarz(models.Model):
    lender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='given_loans',
        verbose_name="Lender"
    )
    borrower_name = models.CharField(
        max_length=100,
        verbose_name="Borrower Name"
    )
    truck = models.ForeignKey(
        Truck,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='loans',
        verbose_name="Truck"
    )
    amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name="Loan Amount",
        validators=[MinValueValidator(0.01)]
    )
    remaining_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name="Remaining Amount"
    )
    given_date = models.DateField(
        verbose_name="Loan Given Date",
        auto_now_add=True
    )
    payment_due_date = models.DateField(
        verbose_name="Payment Due Date",
        null=True,
        blank=True
    )
    description = models.TextField(
        verbose_name="Description",
        blank=True,
        null=True
    )
    document = models.FileField(
        upload_to=qarz_document_upload_path,
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
    is_paid = models.BooleanField(
        default=False,
        verbose_name="Is Paid?"
    )
    created_date = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Created Date"
    )
    updated_date = models.DateTimeField(
        auto_now=True,
        verbose_name="Updated Date"
    )

    def get_user_full_name(self) -> str:
        """Return the full name of the user."""
        full_name = f"{self.lender.first_name} {self.lender.last_name}".strip()
        return full_name or self.lender.username

    def save(self, *args, send_telegram=True, **kwargs):
        is_new = not self.pk
        if is_new:
            self.remaining_amount = self.amount
        if self.document and not self.original_file_name:
            self.original_file_name = os.path.basename(self.document.name)
        if self.is_paid:
            self.remaining_amount = 0

        description = self.description[:500] + '...' if self.description and len(
            self.description) > 500 else self.description or 'None'
        super().save(*args, **kwargs)

        if not send_telegram:
            return

        # Prepare Telegram message
        action = "Created" if is_new else "Updated"
        action_emoji = "💸" if is_new else "🔄"
        truck_info = (
            f"  • PO-ID: <code>{self.truck.po_id}</code>\n"
            f"  • Make/Model: {self.truck.make} {self.truck.model}\n"
            f"  • Year: {self.truck.year}\n"
            f"  • Price: ${self.truck.price:,.2f}"
        ) if self.truck else "None"
        message = (
            f"<b>{action_emoji} Loan {action}</b>\n"
            f"📋 <u>Loan Details:</u>\n"
            f"  • Borrower: {self.borrower_name}\n"
            f"  • Amount: ${self.amount:,.2f}\n"
            f"  • Remaining: ${self.remaining_amount:,.2f}\n"
            f"  • Percentage Paid: {self.percentage_paid:.2f}%\n"
            f"  • Given Date: {self.given_date}\n"
            f"  • Due Date: {self.payment_due_date or 'Not specified'}\n"
            f"  • Description: {description}\n"
            f"  • Document: <code>{self.original_file_name or 'None'}</code>\n"
            f"  • Status: {'Paid' if self.is_paid else 'Unpaid'}\n"
            f"\n🚛 <u>Truck:</u>\n{truck_info}\n"
            f"\n👤 <u>Admin:</u>\n"
            f"  • Username: <code>{self.lender.username}</code>\n"
            f"  • Name: {self.get_user_full_name()}"
        )
        send_to_telegram(message)

        # Send document file
        if self.document:
            file_path = self.document.path
            original_filename = self.original_file_name or os.path.basename(self.document.name)
            caption = (
                f"<b>📎 Loan Document</b>\n"
                f"Borrower: {self.borrower_name}\n"
                f"Amount: ${self.amount:,.2f}\n"
                f"Truck: <code>{self.truck.po_id}</code> ({self.truck.make} {self.truck.model})" if self.truck else "None"
                f"\nFile: <code>{original_filename}</code>"
            )
            send_file_to_telegram(file_path, original_filename, caption)

    def delete(self, *args, **kwargs):
        # Prepare Telegram message
        truck_info = (
            f"  • PO-ID: <code>{self.truck.po_id}</code>\n"
            f"  • Make/Model: {self.truck.make} {self.truck.model}"
        ) if self.truck else "None"
        message = (
            f"<b>🗑️ Loan Deleted</b>\n"
            f"📋 <u>Loan Details:</u>\n"
            f"  • Borrower: {self.borrower_name}\n"
            f"  • Amount: ${self.amount:,.2f}\n"
            f"  • Remaining: ${self.remaining_amount:,.2f}\n"
            f"  • Document: <code>{self.original_file_name or 'None'}</code>\n"
            f"\n🚛 <u>Truck:</u>\n{truck_info}\n"
            f"\n👤 <u>Admin:</u>\n"
            f"  • Username: <code>{self.lender.username}</code>\n"
            f"  • Name: {self.get_user_full_name()}"
        )
        super().delete(*args, **kwargs)
        send_to_telegram(message)

    def __str__(self):
        return f"{self.lender.username} -> {self.borrower_name}: ${self.amount} (Remaining: ${self.remaining_amount})"

    @property
    def percentage_paid(self):
        if self.amount > 0:
            return (1 - self.remaining_amount / self.amount) * 100
        return 0

    def get_paid_amount(self):
        return self.amount - self.remaining_amount

    class Meta:
        verbose_name = "Loan"
        verbose_name_plural = "Loans"
        ordering = ['-given_date']
        indexes = [
            models.Index(fields=['lender', 'is_paid']),
            models.Index(fields=['given_date']),
        ]

class Payment(models.Model):
    qarz = models.ForeignKey(
        Qarz,
        on_delete=models.CASCADE,
        related_name='payments',
        verbose_name="Loan"
    )
    amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name="Payment Amount",
        validators=[MinValueValidator(0.01)]
    )
    payment_date = models.DateField(
        verbose_name="Payment Date"
    )
    description = models.TextField(
        verbose_name="Description",
        blank=True,
        null=True
    )

    def save(self, *args, **kwargs):
        is_new = not self.pk
        super().save(*args, **kwargs)

        # Update loan remaining amount
        total_payments = self.qarz.payments.aggregate(total=models.Sum('amount'))['total'] or 0
        remaining = self.qarz.amount - total_payments
        self.qarz.remaining_amount = max(0, remaining)
        self.qarz.is_paid = self.qarz.remaining_amount == 0
        self.qarz.save()

        # Prepare Telegram message
        action = "Created" if is_new else "Updated"
        action_emoji = "💳" if is_new else "🔄"

        # Truck information
        truck = self.qarz.truck
        truck_info = (
            f"  • PO-ID: <code>{truck.po_id}</code>\n"
            f"  • Make/Model: {truck.make} {truck.model}"
            if truck else "None"
        )

        # Limit description to 500 characters
        description = self.description or 'None'
        if len(description) > 500:
            description = description[:500] + '...'

        # Telegram message
        message = (
            f"<b>{action_emoji} Payment {action}</b>\n"
            f"💸 <u>Payment Details:</u>\n"
            f"  • Amount: ${self.amount:,.2f}\n"
            f"  • Date: {self.payment_date}\n"
            f"  • Description: {description}\n"
            f"\n📋 <u>Loan:</u>\n"
            f"  • Borrower: {self.qarz.borrower_name}\n"
            f"  • Total Amount: ${self.qarz.amount:,.2f}\n"
            f"  • Remaining: ${self.qarz.remaining_amount:,.2f}\n"
            f"  • Status: {'Paid' if self.qarz.is_paid else 'Unpaid'}\n"
            f"\n🚛 <u>Truck:</u>\n{truck_info}\n"
            f"\n👤 <u>Admin:</u>\n"
            f"  • Username: <code>{self.qarz.lender.username}</code>\n"
            f"  • Name: {self.qarz.get_user_full_name()}"
        )

        # Send to Telegram
        send_to_telegram(message)

    def delete(self, *args, **kwargs):
        # Save necessary data before deletion
        qarz = self.qarz
        amount = self.amount
        payment_date = self.payment_date
        description = self.description or 'None'
        truck = qarz.truck

        # Delete
        super().delete(*args, **kwargs)

        # Update loan
        total_payments = qarz.payments.aggregate(total=models.Sum('amount'))['total'] or 0
        qarz.remaining_amount = max(0, qarz.amount - total_payments)
        qarz.is_paid = qarz.remaining_amount == 0
        qarz.save()

        # Limit description to 500 characters
        if len(description) > 500:
            description = description[:500] + '...'

        # Truck information
        truck_info = (
            f"  • PO-ID: <code>{truck.po_id}</code>\n"
            f"  • Make/Model: {truck.make} {truck.model}"
            if truck else "None"
        )

        # Telegram message
        message = (
            f"<b>❌ Payment Deleted</b>\n"
            f"💸 <u>Payment Details:</u>\n"
            f"  • Amount: ${amount:,.2f}\n"
            f"  • Date: {payment_date}\n"
            f"  • Description: {description}\n"
            f"\n📋 <u>Loan:</u>\n"
            f"  • Borrower: {qarz.borrower_name}\n"
            f"  • Total Amount: ${qarz.amount:,.2f}\n"
            f"  • Remaining: ${qarz.remaining_amount:,.2f}\n"
            f"  • Status: {'Paid' if qarz.is_paid else 'Unpaid'}\n"
            f"\n🚛 <u>Truck:</u>\n{truck_info}\n"
            f"\n👤 <u>Admin:</u>\n"
            f"  • Username: <code>{qarz.lender.username}</code>\n"
            f"  • Name: {qarz.get_user_full_name()}"
        )

        send_to_telegram(message)

    def __str__(self):
        return f"Payment ${self.amount} for {self.qarz} ({self.payment_date})"

    class Meta:
        verbose_name = "Payment"
        verbose_name_plural = "Payments"
        ordering = ['-payment_date']
        indexes = [
            models.Index(fields=['qarz']),
            models.Index(fields=['payment_date']),
        ]