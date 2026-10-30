from django.contrib import admin

from .models import (
    AuditLog, Customer, CustomerPayment, Expense, Product, Purchase,
    Sale, SaleItem, ShopSettings, StockMovement, Supplier,
)


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0
    readonly_fields = ["product_name", "quantity", "unit_price", "unit_cost"]


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ["receipt_number", "sold_at", "customer_name", "payment_method", "total", "status"]
    list_filter = ["status", "payment_method", "sold_at"]
    search_fields = ["receipt_number", "customer_name"]
    inlines = [SaleItemInline]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "stock_quantity", "reorder_level", "selling_price", "expiry_date"]
    list_filter = ["category"]
    search_fields = ["name", "barcode", "batch_number"]


admin.site.register([Supplier, Customer, CustomerPayment, Purchase, Expense, StockMovement, AuditLog, ShopSettings])
