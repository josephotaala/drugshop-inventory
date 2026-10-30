from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from inventory.models import Customer, Expense, Product, ShopSettings, Supplier


class Command(BaseCommand):
    help = "Create the Trusteen sample suppliers, products, customer, and expense."

    def handle(self, *args, **options):
        suppliers = {}
        for name, phone in [
            ("Kampala Medical Supplies", "0701 111 222"),
            ("Uganda Pharma Ltd", "0755 111 333"),
            ("HealthLink Distributors", "0780 222 333"),
        ]:
            suppliers[name], _ = Supplier.objects.get_or_create(name=name, defaults={"phone": phone})

        samples = [
            ("Paracetamol 500mg", "Analgesic", "616100100001", "tablet", 420, 100, 80, 150, "PCM2408", 210, 28, "Kampala Medical Supplies"),
            ("Amoxicillin 500mg", "Antibiotic", "616100100002", "capsule", 48, 60, 180, 300, "AMX119", 65, 12, "Uganda Pharma Ltd"),
            ("ORS Sachets", "Rehydration", "616100100003", "sachet", 17, 40, 450, 700, "ORS-77", 300, 8, "Kampala Medical Supplies"),
            ("Cetirizine 10mg", "Antihistamine", "616100100004", "tablet", 96, 30, 100, 200, "CET502", 12, 5, "Uganda Pharma Ltd"),
            ("Vitamin C 100mg", "Vitamins", "616100100005", "tablet", 230, 50, 70, 120, "VTC811", 450, 9, "HealthLink Distributors"),
            ("Cough Syrup 100ml", "Cough & cold", "616100100006", "bottle", 8, 12, 3200, 4500, "CS009", 95, 3, "HealthLink Distributors"),
            ("Disposable gloves", "Medical supplies", "616100100007", "pair", 155, 40, 250, 400, "GLV42", 900, 6, "Kampala Medical Supplies"),
        ]
        for name, category, barcode, unit, qty, minimum, cost, price, batch, expiry_days, daily, supplier in samples:
            Product.objects.get_or_create(
                barcode=barcode,
                defaults={
                    "name": name, "category": category, "unit": unit, "stock_quantity": qty,
                    "reorder_level": minimum, "unit_cost": cost, "selling_price": price,
                    "batch_number": batch, "expiry_date": timezone.localdate() + timedelta(days=expiry_days),
                    "average_daily_sales": daily, "supplier": suppliers[supplier],
                },
            )
        Customer.objects.get_or_create(name="Grace A.", defaults={"phone": "0700 000 111", "balance": 18000, "notes": "Regular customer"})
        Expense.objects.get_or_create(description="Stock delivery", defaults={"category": "Transport", "amount": 15000})
        ShopSettings.objects.get_or_create(pk=1)
        self.stdout.write(self.style.SUCCESS("Trusteen demo inventory data is ready."))
