"""
Populate a realistic demo dataset by driving the real service layer (so every
business rule, audit entry and discrepancy is produced exactly as in production).

    python manage.py seed_demo            # only if the database has no branches yet
    python manage.py seed_demo --reset    # wipe CMRS data and reseed

Creates 3 branches, one user per role (+ managers and agents per branch), ~70 customers
with loans (~70), and three weeks of collections moving through every lifecycle stage,
including shortages, an excess, a rejected hand-over, a deposit mismatch, a bank
settlement mismatch, a failed deposit and a delayed settlement.
"""
import random
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.banking import services as banking
from apps.banking.models import BankDeposit
from apps.cash import services as cash
from apps.cash.models import CashSubmission, Collection
from apps.core.models import Branch
from apps.lending import services as lending
from apps.lending.models import Loan
from apps.reconciliation.models import Discrepancy
from apps.reconciliation.services import resolve_discrepancy

PASSWORD = "Cmrs@2026"
DAYS = 21

BRANCHES = [
    ("MUM01", "Mumbai - Andheri East", "Mumbai", "HDFC Bank", "50200011112222"),
    ("DEL01", "Delhi - Lajpat Nagar", "New Delhi", "ICICI Bank", "000405012345"),
    ("BLR01", "Bengaluru - Koramangala", "Bengaluru", "State Bank of India", "39876543210"),
]
STAFF = [
    ("admin", "Asha", "Verma", User.Role.ADMIN, None),
    ("finance", "Farhan", "Qureshi", User.Role.FINANCE, None),
    ("manager.mum", "Meera", "Kulkarni", User.Role.BRANCH_MANAGER, "MUM01"),
    ("manager.del", "Rohit", "Malhotra", User.Role.BRANCH_MANAGER, "DEL01"),
    ("manager.blr", "Kavya", "Rao", User.Role.BRANCH_MANAGER, "BLR01"),
    ("agent.ravi", "Ravi", "Patil", User.Role.AGENT, "MUM01"),
    ("agent.sneha", "Sneha", "Desai", User.Role.AGENT, "MUM01"),
    ("agent.amit", "Amit", "Sharma", User.Role.AGENT, "DEL01"),
    ("agent.pooja", "Pooja", "Bansal", User.Role.AGENT, "DEL01"),
    ("agent.kiran", "Kiran", "Gowda", User.Role.AGENT, "BLR01"),
]
FIRST = ["Rajesh", "Sunita", "Mohammed", "Lakshmi", "Vikram", "Anjali", "Suresh", "Fatima", "Deepak", "Priya",
         "Arjun", "Geeta", "Imran", "Neha", "Sanjay", "Rekha", "Harish", "Nazia", "Manoj", "Divya", "Prakash",
         "Shabana", "Gopal", "Swati", "Naveen", "Kamala", "Yusuf", "Pallavi", "Ramesh", "Bhavna"]
LAST = ["Yadav", "Iyer", "Khan", "Reddy", "Singh", "Joshi", "Naidu", "Shaikh", "Gupta", "Pillai", "Mehta",
        "Chauhan", "Ansari", "Menon", "Thakur", "Nair", "Kamath", "Siddiqui", "Pandey", "Hegde"]
TABLES = [
    "reconciliation_discrepancy", "banking_bankdeposit_submissions", "banking_bankdeposit",
    "cash_cashsubmission_collections", "cash_cashsubmission", "cash_repaymentallocation", "cash_collection",
    "lending_installment", "lending_loan", "lending_customer", "core_auditlog", "core_documentsequence",
]


def at(day, hour, minute=0):
    return timezone.make_aware(datetime.combine(day, time(hour, minute)))


class Command(BaseCommand):
    help = "Seed demo data for every role and lifecycle stage."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing CMRS data first")

    def handle(self, *args, **opts):
        if opts["reset"]:
            with connection.cursor() as c:
                if connection.vendor == "postgresql":
                    # TRUNCATE bypasses the row-level immutability triggers by design (demo reset only).
                    c.execute("TRUNCATE " + ", ".join(TABLES) + " RESTART IDENTITY CASCADE")
                else:  # SQLite quick-start: no triggers, plain deletes in dependency order
                    for table in TABLES:
                        c.execute(f"DELETE FROM {table}")
            User.objects.filter(username__in=[s[0] for s in STAFF]).delete()
            Branch.objects.filter(code__in=[b[0] for b in BRANCHES]).delete()
        elif Branch.objects.exists():
            self.stdout.write("Data already present; use --reset to reseed.")
            return
        random.seed(2026)
        with transaction.atomic():
            self.seed()
        self.stdout.write(self.style.SUCCESS(f"Demo data ready. Every user's password: {PASSWORD}"))

    # ------------------------------------------------------------------ setup
    def seed(self):
        today = timezone.localdate()
        start = today - timedelta(days=DAYS)
        self.branches = {code: Branch.objects.create(code=code, name=name, city=city)
                         for code, name, city, *_ in BRANCHES}
        self.bank = {code: (bank, acct) for code, _, _, bank, acct in BRANCHES}
        users = {}
        for username, first, last, role, branch in STAFF:
            u = User(username=username, first_name=first, last_name=last, role=role, email=f"{username}@cmrs.demo",
                     branch=self.branches.get(branch), is_staff=role == User.Role.ADMIN,
                     is_superuser=role == User.Role.ADMIN)
            u.set_password(PASSWORD)
            u.save()
            users[username] = u
        self.users = users
        admin = users["admin"]
        agents = [u for u in users.values() if u.is_agent]
        self.managers = {u.branch.code: u for u in users.values() if u.is_manager}

        names = [(f, l) for f in FIRST for l in LAST]
        random.shuffle(names)
        loans_by_agent = {a.id: [] for a in agents}
        i = 0
        for agent in agents:
            for _ in range(14):
                first, last = names[i]
                i += 1
                customer = lending.create_customer(
                    actor=self.managers[agent.branch.code], full_name=f"{first} {last}",
                    phone=f"9{random.randint(100000000, 999999999)}", address=f"{random.randint(1, 300)}, "
                    f"{random.choice(['MG Road', 'Station Road', 'Main Bazaar', 'Gandhi Nagar', 'Nehru Chowk'])}, "
                    f"{agent.branch.city}", branch=agent.branch, assigned_agent=agent,
                    id_number=f"XXXX-XXXX-{random.randint(1000, 9999)}",
                )
                loan = lending.create_loan(
                    actor=admin, customer=customer,
                    principal=Decimal(random.choice([25000, 40000, 50000, 75000, 100000, 150000])),
                    annual_interest_rate=Decimal(random.choice(["14.00", "18.00", "21.50", "24.00"])),
                    tenure_months=random.choice([6, 12, 12, 18, 24]),
                    disbursement_date=today - timedelta(days=random.randint(35, 200)),
                )
                loans_by_agent[agent.id].append(loan)

        # One borrower per agent stops paying during the demo window (shows up as overdue).
        delinquent = {loans[0].id for loans in loans_by_agent.values()}

        # Bring older loans up to date before the demo window with a single historical receipt each.
        for agent in agents:
            for loan in loans_by_agent[agent.id]:
                due = loan.installments.filter(due_date__lt=start).order_by("installment_number")
                arrears = sum((x.amount_due for x in due), Decimal("0"))
                if arrears and random.random() < 0.85:
                    self._collect(agent, loan, arrears, at(start - timedelta(days=3), 11))
        # Old receipts are reconciled end-to-end so the demo window starts clean.
        self._settle_history(agents, start - timedelta(days=3))

        # ------------------------------------------------------------ daily cycle
        self.done = set()
        for offset in range(DAYS, -1, -1):
            day = today - timedelta(days=offset)
            if day.weekday() == 6:  # no field collection on Sundays
                continue
            for agent in agents:
                # Visit customers whose instalment is due (or overdue); some aren't home, some pay part.
                visits_today = 0
                for loan in loans_by_agent[agent.id]:
                    if loan.id in delinquent or (offset == 0 and visits_today >= 2):
                        continue
                    nxt = loan.installments.exclude(status="PAID").order_by("installment_number").first()
                    if not nxt or nxt.due_date > day + timedelta(days=2) or (offset > 0 and random.random() > 0.55):
                        continue
                    visits_today += 1
                    amount = nxt.balance if random.random() < 0.7 else (nxt.balance * Decimal("0.5")).quantize(Decimal("1"))
                    self._collect(agent, loan, amount, at(day, random.randint(9, 17), random.choice([0, 15, 30, 45])))

            if offset == 0:
                break  # today's cash stays with the agents
            for agent in agents:
                todays = list(Collection.objects.filter(agent=agent, status="COLLECTED", collected_at__date=day))
                if not todays:
                    continue
                expected = sum((c.amount for c in todays), Decimal("0"))
                if offset == 1 and agent.username in ("agent.ravi", "agent.amit"):
                    # Yesterday's hand-over still awaiting the manager's count.
                    sub = cash.submit_cash(agent=agent, collection_ids=[c.id for c in todays],
                                           declared_amount=expected, as_of=day)
                    self._backdate_submission(sub, day, None)
                    continue
                declared, received, notes = expected, expected, ""
                if agent.username == "agent.pooja" and self._once("reject", 8 <= offset <= 13):
                    sub = cash.submit_cash(agent=agent, collection_ids=[c.id for c in todays],
                                           declared_amount=expected, as_of=day)
                    cash.reject_submission(sub.id, actor=self.managers[agent.branch.code],
                                           reason="Two ₹500 notes suspected counterfeit; agent to re-verify bundle.")
                    self._backdate_submission(sub, day, at(day, 19))
                    # Agent re-submits the same receipts the next morning.
                    sub = cash.submit_cash(agent=agent, collection_ids=[c.id for c in todays],
                                           declared_amount=expected, notes="Re-submitted after verification",
                                           as_of=day)
                    cash.approve_submission(sub.id, actor=self.managers[agent.branch.code], received_amount=expected)
                    self._backdate_submission(sub, day, at(day + timedelta(days=1), 10))
                    continue
                if (agent.username == "agent.sneha" and self._once("short1", 9 <= offset <= 16)) or (
                        agent.username == "agent.kiran" and self._once("short2", 3 <= offset <= 8)):
                    received = expected - Decimal("1500.00")
                    declared = received
                    notes = "Agent short by ₹1,500; says change given to customer. Recovery from salary."
                elif agent.username == "agent.amit" and self._once("excess", 4 <= offset <= 10):
                    received = expected + Decimal("200.00")
                    notes = "₹200 excess; receipt for customer payment not issued in field."
                sub = cash.submit_cash(agent=agent, collection_ids=[c.id for c in todays],
                                       declared_amount=declared, as_of=day)
                cash.approve_submission(sub.id, actor=self.managers[agent.branch.code], received_amount=received,
                                        notes=notes)
                self._backdate_submission(sub, day, at(day, 19))

            # Branches bank the previous days' cash every morning (DEL01 skips yesterday's).
            if offset >= 2:
                for code in self.branches:
                    self._deposit(code, day, offset)

        self._resolve_some()

    # ------------------------------------------------------------------ helpers
    def _once(self, key, condition=True):
        """True the first time `key` is asked for while `condition` holds (weekday-proof edge cases)."""
        if condition and key not in self.done:
            self.done.add(key)
            return True
        return False

    def _collect(self, agent, loan, amount, when):
        loan.refresh_from_db()
        amount = min(Decimal(amount), loan.outstanding)
        if amount <= 0:
            return None
        c, _ = cash.record_collection(agent=agent, loan_id=loan.id, amount=amount, confirm_duplicate=True,
                                      collected_at=when)
        return c

    def _backdate_submission(self, sub, day, reviewed):
        updates = {"created_at": at(day, 18, 30)}
        if reviewed:
            updates["reviewed_at"] = reviewed
        CashSubmission.objects.filter(pk=sub.pk).update(**updates)

    def _settle_history(self, agents, day):
        for agent in agents:
            ids = list(Collection.objects.filter(agent=agent, status="COLLECTED").values_list("id", flat=True))
            if not ids:
                continue
            total = sum(Collection.objects.filter(id__in=ids).values_list("amount", flat=True))
            sub = cash.submit_cash(agent=agent, collection_ids=ids, declared_amount=total, as_of=day)
            cash.approve_submission(sub.id, actor=self.managers[agent.branch.code], received_amount=total)
            self._backdate_submission(sub, day, at(day, 19))
        for code in self.branches:
            dep = self._make_deposit(code, day + timedelta(days=1))
            if dep:
                banking.settle_deposit(dep.id, actor=self.users["finance"], settled_amount=dep.amount,
                                       settlement_date=day + timedelta(days=2))

    def _make_deposit(self, code, day, amount_delta=Decimal("0"), reason=""):
        manager = self.managers[code]
        subs = list(banking.depositable_submissions(self.branches[code].id).filter(reviewed_at__date__lt=day))
        if not subs:
            return None
        reconciled = sum((s.received_amount for s in subs), Decimal("0"))
        bank, acct = self.bank[code]
        return banking.create_deposit(
            actor=manager, submission_ids=[s.id for s in subs], bank_name=bank, account_number=acct,
            reference_number=f"{code[:3]}{day:%y%m%d}{random.randint(100000, 999999)}", deposit_date=day,
            amount=reconciled + amount_delta, mismatch_reason=reason,
        )

    def _deposit(self, code, day, offset):
        finance = self.users["finance"]
        if code == "DEL01" and offset <= 2:
            return  # Delhi's cash from the last two days is still in the branch safe
        if not banking.depositable_submissions(self.branches[code].id).filter(reviewed_at__date__lt=day).exists():
            return
        delta, reason = Decimal("0"), ""
        if code == "MUM01" and 9 <= offset <= 14 and self._once("slip_short"):
            delta, reason = Decimal("-500.00"), "One ₹500 note rejected by bank teller as soiled; kept for exchange."
        dep = self._make_deposit(code, day, delta, reason)
        if not dep:
            return
        if offset <= 2:
            return  # recent: awaiting bank credit, within the settlement SLA
        if code == "BLR01" and 4 <= offset <= 6 and self._once("delayed"):
            return  # never credited: shows up as a delayed settlement
        if code == "DEL01" and 8 <= offset <= 9 and self._once("failed"):
            banking.fail_deposit(dep.id, actor=finance,
                                 reason="Bank returned the deposit slip: account number mismatch on challan.")
            return  # next morning's deposit picks the same submissions up again
        settled = dep.amount
        notes = ""
        if code == "MUM01" and 6 <= offset <= 7 and self._once("bank_short"):
            settled, notes = dep.amount - Decimal("100.00"), "Bank levied ₹100 cash handling charge; raised with RM."
        banking.settle_deposit(dep.id, actor=finance, settled_amount=settled,
                               settlement_date=min(day + timedelta(days=1), timezone.localdate()),
                               settlement_reference=f"STMT{day:%Y%m%d}{code}", notes=notes)

    def _resolve_some(self):
        first = Discrepancy.objects.filter(stage=Discrepancy.Stage.SUBMISSION).order_by("created_at").first()
        if first:
            resolve_discrepancy(first.id, actor=self.managers[first.branch.code], resolution="RECOVERED",
                                notes="Recovered ₹1,500 from agent; receipt RV-2231 issued.")
