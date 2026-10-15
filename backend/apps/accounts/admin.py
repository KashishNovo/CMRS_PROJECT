from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["username", "first_name", "last_name", "role", "branch", "is_active"]
    list_filter = ["role", "branch", "is_active"]
    fieldsets = BaseUserAdmin.fieldsets + (("CMRS", {"fields": ("role", "branch", "phone")}),)
    add_fieldsets = BaseUserAdmin.add_fieldsets + (("CMRS", {"fields": ("role", "branch", "phone")}),)
