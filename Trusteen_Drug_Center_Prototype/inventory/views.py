import csv
import json
import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import (
    CustomerEditForm, CustomerForm, ExpenseForm, ProductForm, PurchaseForm, RepaymentForm,
    SaleForm, SettingsForm, StockAdjustmentForm, SupplierForm,
)
from .models import (
    AuditLog, Customer, CustomerPayment, Expense, Product, Purchase, Sale,
    SaleItem, ShopSettings, StockMovement, Supplier,
)


def audit(user, action, details=""):
    AuditLog.objects.create(user=user if user.is_authenticated else None, action=action, details=details)


def shop_settings():
    settings, _ = ShopSettings.objects.get_or_create(pk=1)
    return settings


@login_required
def dashboard(request):
    today = timezone.localdate()
    todays_sales = Sale.objects.filter(sold_at__date=today, status="Completed")
    revenue = todays_sales.aggregate(total=Sum("total"))["total"] or Decimal("0")
    gross = sum((sale.total - sale.cost_total for sale in todays_sales), Decimal("0"))
    products = Product.objects.all()
    context = {
        "today": today,
        "revenue": revenue,
        "gross_profit": gross,
        "stock_units": products.aggregate(total=Sum("stock_quantity"))["total"] or 0,
        "low_stock_count": products.filter(stock_quantity__lte=F("reorder_level")).count(),
        "products_count": products.count(),
        "alerts_count": alert_products().count(),
        "expiry_limit": today + timedelta(days=shop_settings().expiry_alert_days),
        "recent_sales": Sale.objects.select_related("customer").prefetch_related("items")[:8],
        "alerts": alert_products()[:6],
        "fast_movers": products.order_by("-average_daily_sales")[:5],
        "shop": shop_settings(),
    }
    return render(request, "inventory/dashboard.html", context)


def alert_products():
    settings = shop_settings()
    today = timezone.localdate()
    expiry_limit = today + timedelta(days=settings.expiry_alert_days)
    return Product.objects.filter(
        Q(stock_quantity__lte=F("reorder_level"))
        | Q(expiry_date__lte=expiry_limit)
        | Q(stock_quantity__lte=F("average_daily_sales") * settings.reorder_coverage_days)
    ).order_by("stock_quantity", "expiry_date")


@login_required
def product_list(request):
    query = request.GET.get("q", "").strip()
    products = Product.objects.select_related("supplier")
    if query:
        products = products.filter(Q(name__icontains=query) | Q(category__icontains=query) | Q(barcode__icontains=query))
    today = timezone.localdate()
    return render(request, "inventory/products.html", {
        "products": products,
        "query": query,
        "today": today,
        "expiry_limit": today + timedelta(days=shop_settings().expiry_alert_days),
    })


@login_required
def product_create(request):
    form = ProductForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            product = form.save(commit=False)
            opening_stock = form.cleaned_data.get("initial_stock") or 0
            product.stock_quantity = opening_stock
            product.save()
            if opening_stock:
                StockMovement.objects.create(product=product, quantity_change=opening_stock, movement_type="Opening stock", reason="Initial product stock", created_by=request.user)
            audit(request.user, "Product added", product.name)
        messages.success(request, "Product added.")
        return redirect("products")
    return render(request, "inventory/form_page.html", {"form": form, "title": "Add product", "back_url": "products"})


@login_required
def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)
    form = ProductForm(request.POST or None, instance=product)
    form.fields.pop("initial_stock", None)
    if request.method == "POST" and form.is_valid():
        form.save()
        audit(request.user, "Product updated", product.name)
        messages.success(request, "Product updated.")
        return redirect("products")
    return render(request, "inventory/form_page.html", {"form": form, "title": "Edit product", "back_url": "products"})


@login_required
def stock_adjust(request, pk):
    product = get_object_or_404(Product, pk=pk)
    form = StockAdjustmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        change = form.cleaned_data["quantity_change"]
        if not change:
            form.add_error("quantity_change", "Enter a non-zero adjustment.")
        else:
            with transaction.atomic():
                locked = Product.objects.select_for_update().get(pk=product.pk)
                if locked.stock_quantity + change < 0:
                    form.add_error("quantity_change", "Stock cannot be adjusted below zero.")
                else:
                    locked.stock_quantity += change
                    locked.save(update_fields=["stock_quantity", "updated_at"])
                    StockMovement.objects.create(product=locked, quantity_change=change, movement_type="Adjustment", reason=form.cleaned_data["reason"], created_by=request.user)
                    audit(request.user, "Stock adjusted", f"{locked.name}: {change:+} ({form.cleaned_data['reason']})")
                    messages.success(request, "Stock adjusted.")
                    return redirect("products")
    return render(request, "inventory/form_page.html", {"form": form, "title": f"Adjust stock: {product.name}", "back_url": "products"})


@login_required
def sales_list(request):
    query = request.GET.get("q", "").strip()
    sales = Sale.objects.prefetch_related("items")
    if query:
        sales = sales.filter(Q(receipt_number__icontains=query) | Q(customer_name__icontains=query))
    return render(request, "inventory/sales.html", {"sales": sales, "query": query})


@login_required
def sale_create(request):
    form = SaleForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                product = Product.objects.select_for_update().get(pk=form.cleaned_data["product"].pk)
                quantity = form.cleaned_data["quantity"]
                if product.stock_quantity < quantity:
                    raise ValueError(f"Only {product.stock_quantity} units of {product.name} are in stock.")
                customer = form.cleaned_data["customer"]
                discount = form.cleaned_data.get("discount") or Decimal("0")
                subtotal = product.selling_price * quantity
                if discount > subtotal:
                    raise ValueError("Discount cannot be greater than the sale subtotal.")
                customer_name = customer.name if customer else "Walk-in customer"
                sale = Sale.objects.create(
                    customer=customer,
                    customer_name=customer_name,
                    payment_method=form.cleaned_data["payment_method"],
                    subtotal=subtotal,
                    discount=discount,
                    total=subtotal - discount,
                    cost_total=product.unit_cost * quantity,
                    created_by=request.user,
                )
                SaleItem.objects.create(
                    sale=sale, product=product, product_name=product.name,
                    quantity=quantity, unit_price=product.selling_price, unit_cost=product.unit_cost,
                )
                product.stock_quantity -= quantity
                product.save(update_fields=["stock_quantity", "updated_at"])
                if sale.payment_method == "Credit" and customer:
                    Customer.objects.filter(pk=customer.pk).update(balance=F("balance") + sale.total)
                StockMovement.objects.create(product=product, quantity_change=-quantity, movement_type="Sale", reason=sale.receipt_number, created_by=request.user)
                audit(request.user, "Sale completed", f"{sale.receipt_number}: {product.name} x {quantity}; UGX {sale.total}")
            messages.success(request, f"Sale {sale.receipt_number} recorded; stock updated.")
            return redirect("sale-receipt", pk=sale.pk)
        except (Product.DoesNotExist, ValueError) as exc:
            form.add_error(None, str(exc))
    return render(request, "inventory/sale_form.html", {"form": form, "title": "New sale / POS"})


@login_required
@require_POST
def sale_void(request, pk):
    with transaction.atomic():
        sale = get_object_or_404(Sale.objects.select_for_update().prefetch_related("items"), pk=pk)
        if sale.status == "Voided":
            messages.error(request, "This sale has already been voided.")
            return redirect("sales")
        if sale.payment_method == "Credit" and sale.customer_id:
            customer = Customer.objects.select_for_update().get(pk=sale.customer_id)
            if customer.balance < sale.total:
                messages.error(request, "This credit sale cannot be voided because some of its balance has already been repaid.")
                return redirect("sales")
            customer.balance -= sale.total
            customer.save(update_fields=["balance"])
        for item in sale.items.all():
            product = Product.objects.select_for_update().get(pk=item.product_id)
            product.stock_quantity += item.quantity
            product.save(update_fields=["stock_quantity", "updated_at"])
            StockMovement.objects.create(product=product, quantity_change=item.quantity, movement_type="Sale void", reason=sale.receipt_number, created_by=request.user)
        sale.status = "Voided"
        sale.save(update_fields=["status"])
        audit(request.user, "Sale voided", f"{sale.receipt_number}; stock restored")
    messages.success(request, "Sale voided and stock restored.")
    return redirect("sales")


@login_required
def purchases_list(request):
    return render(request, "inventory/purchases.html", {
        "purchases": Purchase.objects.select_related("supplier", "product"),
        "suppliers": Supplier.objects.all(),
        "purchase_total": sum((p.total for p in Purchase.objects.all()), Decimal("0")),
    })


@login_required
def purchase_create(request):
    form = PurchaseForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            data = form.cleaned_data
            product = Product.objects.select_for_update().get(pk=data["product"].pk)
            supplier = Supplier.objects.select_for_update().get(pk=data["supplier"].pk)
            purchase = Purchase.objects.create(**data)
            product.stock_quantity += purchase.quantity
            product.unit_cost = purchase.unit_cost
            product.supplier = supplier
            if purchase.batch_number:
                product.batch_number = purchase.batch_number
            if purchase.expiry_date:
                product.expiry_date = purchase.expiry_date
            product.save()
            due = purchase.total - purchase.amount_paid
            if due:
                supplier.balance = F("balance") + due
                supplier.save(update_fields=["balance"])
            StockMovement.objects.create(product=product, quantity_change=purchase.quantity, movement_type="Purchase", reason=purchase.reference, created_by=request.user)
            audit(request.user, "Stock received", f"{product.name} x {purchase.quantity} from {supplier.name}")
        messages.success(request, f"Received {purchase.quantity} units of {product.name}.")
        return redirect("purchases")
    return render(request, "inventory/form_page.html", {"form": form, "title": "Receive stock", "back_url": "purchases"})


@login_required
def supplier_create(request):
    form = SupplierForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        supplier = form.save()
        audit(request.user, "Supplier added", supplier.name)
        messages.success(request, "Supplier added.")
        return redirect("purchases")
    return render(request, "inventory/form_page.html", {"form": form, "title": "Add supplier", "back_url": "purchases"})


@login_required
def customers_list(request):
    return render(request, "inventory/customers.html", {"customers": Customer.objects.annotate(sale_count=Count("sales"))})


@login_required
def customer_create(request):
    form = CustomerForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        customer = form.save()
        audit(request.user, "Customer added", customer.name)
        messages.success(request, "Customer added.")
        return redirect("customers")
    return render(request, "inventory/form_page.html", {"form": form, "title": "Add customer", "back_url": "customers"})


@login_required
def customer_detail(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    return render(request, "inventory/customer_detail.html", {
        "customer": customer,
        "sales": customer.sales.prefetch_related("items"),
        "payments": customer.payments.select_related("recorded_by"),
    })


@login_required
def customer_edit(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    form = CustomerEditForm(request.POST or None, instance=customer)
    if request.method == "POST" and form.is_valid():
        customer = form.save()
        audit(request.user, "Customer account updated", f"{customer.account_number}: {customer.name}")
        messages.success(request, "Customer account updated.")
        return redirect("customer-detail", pk=customer.pk)
    return render(request, "inventory/form_page.html", {
        "form": form,
        "title": f"Edit customer: {customer.name}",
        "back_url": "customer-detail",
        "back_args": [customer.pk],
    })


@login_required
def customer_repay(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    form = RepaymentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            customer = Customer.objects.select_for_update().get(pk=pk)
            amount = form.cleaned_data["amount"]
            if amount > customer.balance:
                form.add_error("amount", "Payment cannot exceed the outstanding balance.")
            else:
                CustomerPayment.objects.create(customer=customer, recorded_by=request.user, **form.cleaned_data)
                customer.balance -= amount
                customer.save(update_fields=["balance"])
                audit(request.user, "Customer repayment", f"{customer.name} paid UGX {amount}")
                messages.success(request, "Customer payment recorded.")
                return redirect("customers")
    return render(request, "inventory/form_page.html", {"form": form, "title": f"Record payment: {customer.name}", "back_url": "customers"})


@login_required
def expenses_list(request):
    expenses = Expense.objects.select_related("recorded_by")
    return render(request, "inventory/expenses.html", {"expenses": expenses, "total_expenses": expenses.aggregate(total=Sum("amount"))["total"] or 0})


@login_required
def expense_create(request):
    form = ExpenseForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        expense = form.save(commit=False)
        expense.recorded_by = request.user
        expense.save()
        audit(request.user, "Expense added", f"{expense.category}: UGX {expense.amount}")
        messages.success(request, "Expense saved.")
        return redirect("expenses")
    return render(request, "inventory/form_page.html", {"form": form, "title": "Add expense", "back_url": "expenses"})


@login_required
def alerts(request):
    settings = shop_settings()
    return render(request, "inventory/alerts.html", {
        "products": alert_products(),
        "settings": settings,
        "expiry_limit": timezone.localdate() + timedelta(days=settings.expiry_alert_days),
    })


@login_required
def reports(request):
    today = timezone.localdate()
    completed = Sale.objects.filter(status="Completed")
    today_sales = completed.filter(sold_at__date=today)
    today_gross = sum((sale.total - sale.cost_total for sale in today_sales), Decimal("0"))
    today_expenses = Expense.objects.filter(date=today).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    all_gross = sum((sale.total - sale.cost_total for sale in completed), Decimal("0"))
    expenses_total = Expense.objects.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    product_profit = []
    for product in Product.objects.all():
        rows = SaleItem.objects.filter(product=product, sale__status="Completed")
        totals = rows.aggregate(units=Sum("quantity"), revenue=Sum(F("quantity") * F("unit_price")), cost=Sum(F("quantity") * F("unit_cost")))
        product_profit.append({
            "product": product,
            "units": totals["units"] or 0,
            "revenue": totals["revenue"] or 0,
            "cost": totals["cost"] or 0,
            "profit": (totals["revenue"] or 0) - (totals["cost"] or 0),
        })
    payment_totals = {method: completed.filter(payment_method=method).aggregate(total=Sum("total"))["total"] or 0 for method, _ in Sale.PAYMENT_METHODS}
    return render(request, "inventory/reports.html", {
        "today_revenue": today_sales.aggregate(total=Sum("total"))["total"] or 0,
        "today_gross": today_gross,
        "today_expenses": today_expenses,
        "today_net": today_gross - today_expenses,
        "stock_value": sum((p.stock_value for p in Product.objects.all()), Decimal("0")),
        "all_gross": all_gross,
        "expenses_total": expenses_total,
        "all_net": all_gross - expenses_total,
        "product_profit": product_profit,
        "payment_totals": payment_totals,
    })


@login_required
def audit_list(request):
    return render(request, "inventory/audit.html", {"entries": AuditLog.objects.select_related("user")[:300]})


@login_required
def settings_view(request):
    settings = shop_settings()
    form = SettingsForm(request.POST or None, initial={
        "shop_name": settings.shop_name,
        "expiry_alert_days": settings.expiry_alert_days,
        "reorder_coverage_days": settings.reorder_coverage_days,
    })
    if request.method == "POST" and form.is_valid():
        for field, value in form.cleaned_data.items():
            setattr(settings, field, value)
        settings.save()
        audit(request.user, "Settings updated", "Shop and alert settings saved")
        messages.success(request, "Settings saved.")
        return redirect("settings")
    return render(request, "inventory/settings.html", {"form": form})


@login_required
def export_sales(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="trusteen-sales.csv"'
    writer = csv.writer(response)
    writer.writerow(["Receipt", "Date", "Customer", "Payment", "Total UGX", "Cost UGX", "Gross profit UGX", "Status"])
    for sale in Sale.objects.all():
        writer.writerow([sale.receipt_number, sale.sold_at.date(), sale.customer_name, sale.payment_method, sale.total, sale.cost_total, sale.total - sale.cost_total, sale.status])
    audit(request.user, "Sales exported", "CSV sales report downloaded")
    return response


@login_required
def backup_json(request):
    data = {
        "products": list(Product.objects.values()),
        "customers": list(Customer.objects.values()),
        "suppliers": list(Supplier.objects.values()),
        "sales": list(Sale.objects.values()),
        "sale_items": list(SaleItem.objects.values()),
        "purchases": list(Purchase.objects.values()),
        "expenses": list(Expense.objects.values()),
        "stock_movements": list(StockMovement.objects.values()),
    }
    response = HttpResponse(json.dumps(data, default=str, indent=2), content_type="application/json")
    response["Content-Disposition"] = f'attachment; filename="trusteen-backup-{timezone.localdate()}.json"'
    audit(request.user, "Backup downloaded", "JSON backup downloaded")
    return response


@login_required
def sale_receipt(request, pk):
    sale = get_object_or_404(
        Sale.objects.select_related("customer", "created_by").prefetch_related("items"),
        pk=pk,
    )
    return render(request, "inventory/receipt.html", {"sale": sale, "shop": shop_settings()})
