from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group

ROLE_NAMES = ["ADMIN", "MANAGER", "EMPLOYEE"]

class Command(BaseCommand):
    help = "Creeaza grupurile de roluri: ADMIN, MANAGER, EMPLOYEE"

    def handle(self, *args, **options):
        for name in ROLE_NAMES:
            Group.objects.get_or_create(name=name)
        self.stdout.write(self.style.SUCCESS("OK: Grupurile au fost create/exista deja."))
