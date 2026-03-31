from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, MemberProfile, Technique, PointsHistory, Cheer


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'full_name', 'email', 'role', 'is_active')
    list_filter = ('role', 'is_active')
    fieldsets = UserAdmin.fieldsets + (
        ('PLAGENOR', {'fields': ('role', 'organization', 'phone', 'student_level', 'student_level_other', 'supervisor', 'laboratory')}),
    )

    def full_name(self, obj):
        return obj.get_full_name()


@admin.register(MemberProfile)
class MemberProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'max_load', 'current_load', 'available', 'productivity_score', 'total_points')
    list_filter = ('available', 'productivity_status')


@admin.register(Technique)
class TechniqueAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'active')
    list_filter = ('category', 'active')


admin.site.register(PointsHistory)
admin.site.register(Cheer)
