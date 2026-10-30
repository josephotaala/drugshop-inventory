from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("products/", views.product_list, name="products"),
    path("products/new/", views.product_create, name="product-create"),
    path("products/<int:pk>/edit/", views.product_edit, name="product-edit"),
    path("products/<int:pk>/adjust/", views.stock_adjust, name="stock-adjust"),
    path("sales/", views.sales_list, name="sales"),
    path("sales/new/", views.sale_create, name="sale-create"),
    path("sales/<int:pk>/void/", views.sale_void, name="sale-void"),
    path("sales/<int:pk>/receipt/", views.sale_receipt, name="sale-receipt"),
    path("sales/export.csv", views.export_sales, name="sales-export"),
    path("purchases/", views.purchases_list, name="purchases"),
    path("purchases/receive/", views.purchase_create, name="purchase-create"),
    path("suppliers/new/", views.supplier_create, name="supplier-create"),
    path("customers/", views.customers_list, name="customers"),
    path("customers/new/", views.customer_create, name="customer-create"),
    path("customers/<int:pk>/", views.customer_detail, name="customer-detail"),
    path("customers/<int:pk>/edit/", views.customer_edit, name="customer-edit"),
    path("customers/<int:pk>/repay/", views.customer_repay, name="customer-repay"),
    path("expenses/", views.expenses_list, name="expenses"),
    path("expenses/new/", views.expense_create, name="expense-create"),
    path("alerts/", views.alerts, name="alerts"),
    path("reports/", views.reports, name="reports"),
    path("audit/", views.audit_list, name="audit"),
    path("settings/", views.settings_view, name="settings"),
    path("backup.json", views.backup_json, name="backup-json"),
]
