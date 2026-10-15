from django.contrib import admin

from .models import AuditLog, Branch, DocumentSequence


class ReadOnlyAdmin(admin.ModelAdmin):
    """Financial records are created and changed only through the API's service layer."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "city", "is_active"]
    search_fields = ["code", "name"]


@admin.register(AuditLog)
class AuditLogAdmin(ReadOnlyAdmin):
    list_display = ["created_at", "actor", "action", "entity_type", "entity_ref", "branch"]
    list_filter = ["action", "entity_type", "branch"]
    search_fields = ["entity_ref"]


admin.site.register(DocumentSequence, ReadOnlyAdmin)
