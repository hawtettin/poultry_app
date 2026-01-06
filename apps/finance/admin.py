from django.contrib import admin
from .models import Partner, Category, Document, DocumentLine, Payment, ExpenseAttachment

@admin.register(Partner)
class PartnerAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "partner_type", "tax_id")
    list_filter = ("partner_type",)
    search_fields = ("name", "tax_id")

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "kind")
    list_filter = ("kind",)

class DocumentLineInline(admin.TabularInline):
    model = DocumentLine
    extra = 1

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "doc_type", "status", "doc_no", "date", "season", "flock", "partner", "vat_rate", "total", "currency")
    list_filter = ("doc_type", "status", "season")
    inlines = [DocumentLineInline]

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "document", "status", "due_date", "paid_date", "amount", "method")
    list_filter = ("status", "method")


@admin.register(ExpenseAttachment)
class ExpenseAttachmentAdmin(admin.ModelAdmin):
    list_display = ("id", "document", "original_name", "uploaded_at", "uploaded_by")
    search_fields = ("original_name", "document__doc_no", "document__partner__name")
