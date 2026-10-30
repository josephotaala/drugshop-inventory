import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


def new_receipt_number():
    return f"INV-{uuid.uuid4().hex[:8].upper()}"


def new_purchase_reference():
    return f"PO-{uuid.uuid4().hex[:8].upper()}"


class Supplier(models.Model):
    name = models.CharField(max_length=160, unique=True)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    balance = models.DecimalField(max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)])

    def __str__(self):
        return self.name


class Customer(models.Model):
    name = models.CharField(max_length=160)
    phone = models.CharField(max_length=40, blank=True)
    balance = models.DecimalField(max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def account_number(self):
        return f"CUS-{self.pk:06d}"


class Product(models.Model):
    name = models.CharField(max_length=180)
    category = models.CharField(max_length=100, default="General")
    barcode = models.CharField(max_length=80, blank=True, unique=True, null=True)
    unit = models.CharField(max_length=40, default="pack")
    stock_quantity = models.PositiveIntegerField(default=0)
    reorder_level = models.PositiveIntegerField(default=10)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    batch_number = models.CharField(max_length=80, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    average_daily_sales = models.PositiveIntegerField(default=0)
    supplier = models.ForeignKey(Supplier, null=True, blank=True, on_delete=models.SET_NULL, related_name="products")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def stock_value(self):
        return self.stock_quantity * self.unit_cost

    @property
    def is_low_stock(self):
        return self.stock_quantity <= self.reorder_level


class Sale(models.Model):
    PAYMENT_METHODS = [
        ("Cash", "Cash"),
        ("Mobile Money", "Mobile Money"),
        ("Card", "Card"),
        ("Credit", "Credit"),
        ("Bank transfer", "Bank transfer"),
    ]
    STATUS_CHOICES = [("Completed", "Completed"), ("Voided", "Voided")]
    receipt_number = models.CharField(max_length=24, unique=True, default=new_receipt_number)
    sold_at = models.DateTimeField(default=timezone.now)
    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.PROTECT, related_name="sales")
    customer_name = models.CharField(max_length=160, default="Walk-in customer")
    payment_method = models.CharField(max_length=30, choices=PAYMENT_METHODS, default="Cash")
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    cost_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="Completed")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-sold_at"]

    def __str__(self):
        return self.receipt_number

    @property
    def gross_profit(self):
        return self.total - self.cost_total


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="sale_items")
    product_name = models.CharField(max_length=180)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)

    @property
    def line_total(self):
        return self.quantity * self.unit_price


class Purchase(models.Model):
    reference = models.CharField(max_length=30, unique=True, default=new_purchase_reference)
    received_at = models.DateField(default=timezone.localdate)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchases")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="purchases")
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    batch_number = models.CharField(max_length=80, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    invoice_reference = models.CharField(max_length=80, blank=True)
    amount_paid = models.DecimalField(max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)])

    class Meta:
        ordering = ["-received_at", "-id"]

    @property
    def total(self):
        return self.quantity * self.unit_cost


class CustomerPayment(models.Model):
    METHODS = [("Cash", "Cash"), ("Mobile Money", "Mobile Money"), ("Bank transfer", "Bank transfer")]
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    method = models.CharField(max_length=30, choices=METHODS)
    reference = models.CharField(max_length=80, blank=True)
    received_at = models.DateTimeField(default=timezone.now)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)


class Expense(models.Model):
    CATEGORIES = [(x, x) for x in ["Rent", "Transport", "Utilities", "Wages", "Packaging", "Bank charges", "Other"]]
    date = models.DateField(default=timezone.localdate)
    category = models.CharField(max_length=40, choices=CATEGORIES)
    description = models.CharField(max_length=240)
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-date", "-id"]


class StockMovement(models.Model):
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="movements")
    quantity_change = models.IntegerField()
    movement_type = models.CharField(max_length=30)
    reason = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-created_at"]


class AuditLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=100)
    details = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class ShopSettings(models.Model):
    shop_name = models.CharField(max_length=160, default="Trusteen Drug Center")
    expiry_alert_days = models.PositiveIntegerField(default=30)
    reorder_coverage_days = models.PositiveIntegerField(default=7)

    def __str__(self):
        return self.shop_name
