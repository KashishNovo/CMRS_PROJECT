from datetime import timedelta
from decimal import Decimal


import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.core.models import Branch
from apps.lending import services as lending


@pytest.fixture
def branch(db):
    return Branch.objects.create(code="MUM01", name="Mumbai")


@pytest.fixture
def other_branch(db):
    return Branch.objects.create(code="DEL01", name="Delhi")


def make_user(username, role, branch=None):
    user = User.objects.create_user(username=username, password="Test@12345", role=role, branch=branch,
                                    first_name=username.title())
    return user


@pytest.fixture
def admin(db):
    return make_user("admin", User.Role.ADMIN)


@pytest.fixture
def finance(db):
    return make_user("finance", User.Role.FINANCE)


@pytest.fixture
def manager(branch):
    return make_user("manager", User.Role.BRANCH_MANAGER, branch)


@pytest.fixture
def other_manager(other_branch):
    return make_user("manager2", User.Role.BRANCH_MANAGER, other_branch)


@pytest.fixture
def agent(branch):
    return make_user("agent", User.Role.AGENT, branch)


@pytest.fixture
def other_agent(branch):
    return make_user("agent2", User.Role.AGENT, branch)


@pytest.fixture
def customer(manager, agent):
    return lending.create_customer(actor=manager, full_name="Rajesh Yadav", phone="9876543210", branch=manager.branch,
                                   assigned_agent=agent)


@pytest.fixture
def loan(admin, customer):
    """₹1,00,000 @ 12% for 12 months -> EMI ₹8,884.88."""
    return lending.create_loan(actor=admin, customer=customer, principal=Decimal("100000.00"),
                               annual_interest_rate=Decimal("12.00"), tenure_months=12,
                               disbursement_date=timezone.localdate() - timedelta(days=40))


@pytest.fixture
def api():
    def _client(user=None):
        client = APIClient()
        if user:
            client.force_authenticate(user)
        return client
    return _client
