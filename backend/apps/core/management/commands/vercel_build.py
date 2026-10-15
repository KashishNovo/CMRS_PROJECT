"""
Build step for Vercel (see the root vercel.json): apply migrations and load demo data.

Skips the database work, with a clear message, when DATABASE_URL isn't available yet
(e.g. the first deploy before a database is connected), so the build itself still succeeds.
"""
import os

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Migrate and seed demo data during a Vercel build."

    def handle(self, *args, **options):
        if not os.environ.get("DATABASE_URL"):
            self.stdout.write(self.style.WARNING(
                "DATABASE_URL is not set: skipping migrations and demo data. "
                "Connect a database (Storage -> Neon) and redeploy."
            ))
            return
        call_command("migrate", interactive=False, verbosity=1)
        if os.environ.get("SEED_DEMO_DATA", "true").lower() in {"1", "true", "yes"}:
            call_command("seed_demo")  # no-op when data already exists
