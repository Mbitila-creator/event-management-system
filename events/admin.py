from django.contrib import admin

from .models import Event, EventCategory, Venue


@admin.register(EventCategory)
class EventCategoryAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name_sw",
        "name_en",
        "display_order",
        "is_active",
        "created_by",
        "created_at",
    )

    list_filter = (
        "is_active",
        "created_at",
        "updated_at",
    )

    search_fields = (
        "code",
        "name_sw",
        "name_en",
        "description_sw",
        "description_en",
    )

    ordering = (
        "display_order",
        "name_sw",
    )

    readonly_fields = (
        "slug",
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "Category Information",
            {
                "fields": (
                    "code",
                    "name_sw",
                    "name_en",
                    "slug",
                    "description_sw",
                    "description_en",
                    "display_order",
                    "is_active",
                )
            },
        ),
        (
            "Audit Information",
            {
                "fields": (
                    "created_by",
                    "updated_by",
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        if not obj.pk or not obj.created_by:
            obj.created_by = request.user

        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "council",
        "venue_type",
        "capacity",
        "contact_phone",
        "is_active",
    )

    list_filter = (
        "venue_type",
        "council__region",
        "council",
        "is_active",
    )

    search_fields = (
        "name",
        "address",
        "council__name_sw",
        "council__name_en",
        "contact_person",
        "contact_phone",
        "contact_email",
    )

    ordering = (
        "name",
    )

    readonly_fields = (
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "Venue Information",
            {
                "fields": (
                    "name",
                    "council",
                    "address",
                    "venue_type",
                    "capacity",
                    "is_active",
                )
            },
        ),
        (
            "Contact Information",
            {
                "fields": (
                    "contact_person",
                    "contact_phone",
                    "contact_email",
                )
            },
        ),
        (
            "Location and Online Access",
            {
                "fields": (
                    "latitude",
                    "longitude",
                    "online_link",
                )
            },
        ),
        (
            "Additional Information",
            {
                "fields": (
                    "notes",
                )
            },
        ),
        (
            "Audit Information",
            {
                "fields": (
                    "created_by",
                    "updated_by",
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        if not obj.pk or not obj.created_by:
            obj.created_by = request.user

        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "title_sw",
        "category",
        "venue",
        "starts_at",
        "ends_at",
        "status",
        "registration_enabled",
        "payment_enabled",
        "is_active",
    )

    list_filter = (
        "status",
        "category",
        "registration_enabled",
        "payment_enabled",
        "evaluation_enabled",
        "qr_checkin_enabled",
        "badge_enabled",
        "certificate_enabled",
        "booth_enabled",
        "is_public",
        "is_active",
    )

    search_fields = (
        "code",
        "title_sw",
        "title_en",
        "organizer_name_sw",
        "organizer_name_en",
        "contact_person",
        "contact_email",
        "contact_phone",  
    )

    ordering = (
        "-starts_at",
    )

    date_hierarchy = "starts_at"

    readonly_fields = (
        "slug",
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "Basic Information",
            {
                "fields": (
                    "code",
                    "category",
                    "title_sw",
                    "title_en",
                    "slug",
                    "description_sw",
                    "description_en",
                    "status",
                    "is_public",
                    "is_active",
                )
            },
        ),
        (
            "Organizer Information",
            {
                "fields": (
                    "organizer_name_sw",
                    "organizer_name_en",
                    "contact_person",
                    "contact_email",
                    "contact_phone",
                )
            },
        ),
        (
            "Venue and Capacity",
            {
                "fields": (
                    "venue",
                    "maximum_participants",
                )
            },
        ),
        (
            "Dates and Registration Period",
            {
                "fields": (
                    "registration_opens_at",
                    "registration_closes_at",
                    "starts_at",
                    "ends_at",
                )
            },
        ),
        (
            "Branding",
            {
                "fields": (
                    "logo",
                    "banner",
                )
            },
        ),
        (
            "Enabled Services",
            {
                "fields": (
                    "registration_enabled",
                    "evaluation_enabled",
                    "qr_checkin_enabled",
                    "badge_enabled",
                    "certificate_enabled",
                    "booth_enabled",
                    "payment_enabled",
                )
            },
        ),
        (
            "Payment Configuration",
            {
                "fields": (
                    "participation_fee",
                    "payment_currency",
                    "payment_instructions_sw",
                    "payment_instructions_en",
                )
            },
        ),
        (
            "Audit Information",
            {
                "fields": (
                    "created_by",
                    "updated_by",
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        if not obj.pk or not obj.created_by:
            obj.created_by = request.user

        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
