from django import forms
from django.db.models import Q

from .models import Customer, Expense, Product, Sale, Supplier


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "input")


class ProductForm(StyledModelForm):
    initial_stock = forms.IntegerField(min_value=0, required=False, initial=0, label="Opening stock")

    def clean_barcode(self):
        return self.cleaned_data.get("barcode") or None

    class Meta:
        model = Product
        fields = [
            "name", "category", "barcode", "unit", "reorder_level", "unit_cost",
            "selling_price", "batch_number", "expiry_date", "average_daily_sales", "supplier",
        ]
        widgets = {"expiry_date": forms.DateInput(attrs={"type": "date"})}


class StockAdjustmentForm(forms.Form):
    quantity_change = forms.IntegerField(label="Quantity change (+ or -)")
    reason = forms.CharField(max_length=200)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "input"


class SaleForm(forms.Form):
    product = forms.ModelChoiceField(queryset=Product.objects.none())
    quantity = forms.IntegerField(min_value=1, initial=1)
    customer = forms.ModelChoiceField(queryset=Customer.objects.none(), required=False)
    payment_method = forms.ChoiceField(choices=Sale.PAYMENT_METHODS)
    discount = forms.DecimalField(min_value=0, max_digits=14, decimal_places=2, initial=0, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.filter(stock_quantity__gt=0)
        self.fields["customer"].queryset = Customer.objects.all()
        for field in self.fields.values():
            field.widget.attrs["class"] = "input"

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("payment_method") == "Credit" and not cleaned.get("customer"):
            self.add_error("customer", "Select a customer for a credit sale.")
        return cleaned


class CustomerForm(StyledModelForm):
    class Meta:
        model = Customer
        fields = ["name", "phone", "balance", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}


class CustomerEditForm(StyledModelForm):
    class Meta:
        model = Customer
        fields = ["name", "phone", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}


class SupplierForm(StyledModelForm):
    class Meta:
        model = Supplier
        fields = ["name", "phone", "email", "balance"]


class PurchaseForm(forms.Form):
    supplier = forms.ModelChoiceField(queryset=Supplier.objects.all())
    product = forms.ModelChoiceField(queryset=Product.objects.all())
    quantity = forms.IntegerField(min_value=1, initial=1)
    unit_cost = forms.DecimalField(min_value=0, max_digits=12, decimal_places=2)
    amount_paid = forms.DecimalField(min_value=0, max_digits=14, decimal_places=2, initial=0)
    batch_number = forms.CharField(max_length=80, required=False)
    expiry_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    invoice_reference = forms.CharField(max_length=80, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "input"

    def clean(self):
        cleaned = super().clean()
        if all(cleaned.get(k) is not None for k in ("quantity", "unit_cost", "amount_paid")):
            total = cleaned["quantity"] * cleaned["unit_cost"]
            if cleaned["amount_paid"] > total:
                self.add_error("amount_paid", "Amount paid cannot exceed the purchase total.")
        return cleaned


class RepaymentForm(forms.Form):
    METHODS = [("Cash", "Cash"), ("Mobile Money", "Mobile Money"), ("Bank transfer", "Bank transfer")]
    amount = forms.DecimalField(min_value=0.01, max_digits=14, decimal_places=2)
    method = forms.ChoiceField(choices=METHODS)
    reference = forms.CharField(max_length=80, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "input"


class ExpenseForm(StyledModelForm):
    class Meta:
        model = Expense
        fields = ["date", "category", "description", "amount"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"})}


class SettingsForm(forms.Form):
    shop_name = forms.CharField(max_length=160)
    expiry_alert_days = forms.IntegerField(min_value=1)
    reorder_coverage_days = forms.IntegerField(min_value=1)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "input"
