from django.contrib import admin
from .models import House, Season, Flock

@admin.register(House)
class HouseAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "code")
    search_fields = ("name", "code")

@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "start_date", "end_date", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)

@admin.register(Flock)
class FlockAdmin(admin.ModelAdmin):
    list_display = (
        "id", "season", "house", "start_date",
        "initial_count", "initial_white_count", "initial_colored_count",
        "breed", "supplier",
    )
    list_filter = ("season", "house")
