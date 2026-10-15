"""Test settings: same as production settings, with a throwaway key and fast hashing."""
import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-secret-key-that-is-long-enough-for-hs256")
os.environ.setdefault("DJANGO_DEBUG", "0")
os.environ.setdefault("SECURE_SSL_REDIRECT", "0")

from .settings import *  # noqa: E402,F401,F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": {"login": "1000/min"}}  # noqa: F405
