from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .models import Customer, Product, Purchase, Sale, SaleItem, StockMovement, Supplier


class InventoryWorkflowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="manager", password="test-pass-12345")
        self.client.force_login(self.user)
        self.supplier = Supplier.objects.create(name="Test supplier")
        self.customer = Customer.objects.create(name="Test customer")
        self.product = Product.objects.create(
            name="Test medicine",
            barcode="TEST-001",
            stock_quantity=10,
            reorder_level=2,
            unit_cost=Decimal("80"),
            selling_price=Decimal("150"),
            supplier=self.supplier,
        )

    def test_authenticated_views_render(self):
        for url_name in (
            "dashboard", "products", "sales", "purchases", "customers",
            "alerts", "reports", "expenses", "audit", "settings",
        ):
            with self.subTest(page=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)

    def test_sale_deducts_stock_and_records_cost_snapshot(self):
        response = self.client.post(reverse("sale-create"), {
            "product": self.product.pk,
            "quantity": 3,
            "customer": "",
            "payment_method": "Cash",
            "discount": "50",
        })

        self.assertRedirects(response, reverse("sale-receipt", args=[Sale.objects.get().pk]))
        self.product.refresh_from_db()
        sale = Sale.objects.get()
        item = SaleItem.objects.get(sale=sale)
        self.assertEqual(self.product.stock_quantity, 7)
        self.assertEqual(sale.total, Decimal("400"))
        self.assertEqual(sale.cost_total, Decimal("240"))
        self.assertEqual(item.unit_cost, Decimal("80"))
        self.assertEqual(StockMovement.objects.get().quantity_change, -3)

    def test_sale_rejects_insufficient_stock_without_partial_records(self):
        response = self.client.post(reverse("sale-create"), {
            "product": self.product.pk,
            "quantity": 11,
            "customer": "",
            "payment_method": "Cash",
            "discount": "0",
        })

        self.assertEqual(response.status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 10)
        self.assertFalse(Sale.objects.exists())
        self.assertFalse(StockMovement.objects.exists())

    def test_credit_sale_and_void_restore_stock_and_customer_balance(self):
        self.client.post(reverse("sale-create"), {
            "product": self.product.pk,
            "quantity": 2,
            "customer": self.customer.pk,
            "payment_method": "Credit",
            "discount": "0",
        })
        sale = Sale.objects.get()
        self.customer.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.customer.balance, Decimal("300"))
        self.assertEqual(self.product.stock_quantity, 8)

        response = self.client.post(reverse("sale-void", args=[sale.pk]))

        self.assertRedirects(response, reverse("sales"))
        sale.refresh_from_db()
        self.customer.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(sale.status, "Voided")
        self.assertEqual(self.customer.balance, Decimal("0"))
        self.assertEqual(self.product.stock_quantity, 10)

    def test_purchase_receipt_updates_stock_cost_and_supplier_balance(self):
        response = self.client.post(reverse("purchase-create"), {
            "supplier": self.supplier.pk,
            "product": self.product.pk,
            "quantity": 4,
            "unit_cost": "50",
            "amount_paid": "100",
            "batch_number": "B-1",
            "expiry_date": date(2027, 1, 1).isoformat(),
            "invoice_reference": "INV-SUP-1",
        })

        self.assertRedirects(response, reverse("purchases"))
        self.product.refresh_from_db()
        self.supplier.refresh_from_db()
        purchase = Purchase.objects.get()
        self.assertEqual(self.product.stock_quantity, 14)
        self.assertEqual(self.product.unit_cost, Decimal("50"))
        self.assertEqual(self.supplier.balance, Decimal("100"))
        self.assertEqual(purchase.total, Decimal("200"))

    def test_pages_require_sign_in(self):
        self.client.logout()
        response = self.client.get(reverse("products"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('products')}")

    def test_credit_sale_cannot_be_voided_after_balance_repayment(self):
        self.client.post(reverse("sale-create"), {
            "product": self.product.pk,
            "quantity": 2,
            "customer": self.customer.pk,
            "payment_method": "Credit",
            "discount": "0",
        })
        sale = Sale.objects.get()
        self.client.post(reverse("customer-repay", args=[self.customer.pk]), {
            "amount": "100",
            "method": "Cash",
            "reference": "",
        })

        response = self.client.post(reverse("sale-void", args=[sale.pk]))

        self.assertRedirects(response, reverse("sales"))
        sale.refresh_from_db()
        self.product.refresh_from_db()
        self.customer.refresh_from_db()
        self.assertEqual(sale.status, "Completed")
        self.assertEqual(self.product.stock_quantity, 8)
        self.assertEqual(self.customer.balance, Decimal("200"))

    def test_demo_seed_command_is_repeatable(self):
        call_command("seed_demo", verbosity=0)
        call_command("seed_demo", verbosity=0)
        self.assertEqual(Product.objects.filter(barcode__startswith="61610010000").count(), 7)
        self.assertEqual(Supplier.objects.filter(name="Kampala Medical Supplies").count(), 1)

    def test_customer_account_creation_and_detail(self):
        response = self.client.post(reverse("customer-create"), {
            "name": "New account customer",
            "phone": "0700000000",
            "balance": "0",
            "notes": "Account notes",
        })

        customer = Customer.objects.get(name="New account customer")
        self.assertRedirects(response, reverse("customers"))
        self.assertEqual(customer.account_number, f"CUS-{customer.pk:06d}")
        detail = self.client.get(reverse("customer-detail", args=[customer.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, customer.account_number)
        self.assertContains(detail, "Order history")

    def test_customer_edit_does_not_change_account_balance(self):
        self.customer.balance = Decimal("500")
        self.customer.save()

        response = self.client.post(reverse("customer-edit", args=[self.customer.pk]), {
            "name": "Updated customer",
            "phone": "0700111222",
            "notes": "Updated notes",
        })

        self.assertRedirects(response, reverse("customer-detail", args=[self.customer.pk]))
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.name, "Updated customer")
        self.assertEqual(self.customer.balance, Decimal("500"))

    def test_completed_sale_opens_printable_receipt(self):
        response = self.client.post(reverse("sale-create"), {
            "product": self.product.pk,
            "quantity": 2,
            "customer": self.customer.pk,
            "payment_method": "Cash",
            "discount": "25",
        })

        sale = Sale.objects.get()
        self.assertRedirects(response, reverse("sale-receipt", args=[sale.pk]))
        receipt = self.client.get(reverse("sale-receipt", args=[sale.pk]))
        self.assertEqual(receipt.status_code, 200)
        self.assertContains(receipt, sale.receipt_number)
        self.assertContains(receipt, "Test medicine")
        self.assertContains(receipt, "Print customer receipt")
        self.assertContains(receipt, "window.print()")
