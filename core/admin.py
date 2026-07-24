from django.contrib import admin

from .models import Council, Country, District, Region


class AuditAdminMixin:
    readonly_fields = (
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
    )

    def save_model(self, request, obj, form, change):
        if not obj.pk or not obj.created_by:
            obj.created_by = request.user

        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Country)
class CountryAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display = (
        "code",
        "name_sw",
        "name_en",
        "phone_code",
        "is_active",
    )

    list_filter = (
        "is_active",
    )

    search_fields = (
        "code",
        "name_sw",
        "name_en",
        "phone_code",
    )

    ordering = (
        "name_en",
    )

    readonly_fields = AuditAdminMixin.readonly_fields + (
        "slug",
    )


@admin.register(Region)
class RegionAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display = (
        "code",
        "name_sw",
        "name_en",
        "country",
        "is_active",
    )

    list_filter = (
        "country",
        "is_active",
    )

    search_fields = (
        "code",
        "name_sw",
        "name_en",
        "country__name_sw",
        "country__name_en",
    )

    ordering = (
        "name_sw",
    )

    readonly_fields = AuditAdminMixin.readonly_fields + (
        "slug",
    )


@admin.register(District)
class DistrictAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display = (
        "code",
        "name_sw",
        "name_en",
        "region",
        "is_active",
    )

    list_filter = (
        "region__country",
        "region",
        "is_active",
    )

    search_fields = (
        "code",
        "name_sw",
        "name_en",
        "region__name_sw",
        "region__name_en",
    )

    ordering = (
        "region__name_sw",
        "name_sw",
    )

    readonly_fields = AuditAdminMixin.readonly_fields + (
        "slug",
    )

@admin.register(Council)
class CouncilAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display = (
        "code",
        "name_sw",
        "name_en",
        "region",
        "council_type",
        "is_active",
    )

    list_filter = (
        "region__country",
        "region",
        "council_type",
        "is_active",
    )

    search_fields = (
        "code",
        "name_sw",
        "name_en",
        "region__name_sw",
        "region__name_en",
    )

    ordering = (
        "region__name_sw",
        "name_sw",
    )

    readonly_fields = AuditAdminMixin.readonly_fields + (
        "slug",
    )