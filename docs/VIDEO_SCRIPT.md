# 5-minute walkthrough — suggested script

Timings are targets; total ≈ 4:50. Have two browser windows ready (agent, manager) and one for Finance.

**0:00–0:30 · Problem.** Cash is handed over four times before it reaches the company account. Each hand-off
can lose, delay or double-count money. CMRS tracks *custody*: every receipt is always with one custodian,
every hand-off compares expected with actual, and any gap becomes a discrepancy at the exact stage.
Show the sign-in page's five-stage strip.

**0:30–1:10 · Architecture.** React + TypeScript SPA → DRF API → PostgreSQL. Views are thin; every state change
goes through a service function that runs in a transaction with row locks and writes the audit log.
Critical rules are enforced twice: in services *and* in PostgreSQL (CHECK constraints, unique bank reference,
triggers that freeze reconciled records). Show `docs/ARCHITECTURE.md` diagram.

**1:10–1:50 · Database.** ER diagram: Loan → Instalments; Collection (receipt) with allocations; CashSubmission
and BankDeposit as many-to-many so rejections and failed deposits keep history; Discrepancy points at the
hand-over or deposit where it arose. Money is NUMERIC(14,2), strings over the wire, paise BigInt in the UI.

**1:50–3:40 · Demo.**
1. `agent.ravi` → *My day*: due/overdue list. Record a part payment (show "part payment" hint), then try the
   same amount again → duplicate warning. Show the receipt and which EMI it was applied to.
2. Try more than the outstanding → over-collection message.
3. *Hand over cash* → select receipts.
4. `manager.mum` → *Cash hand-overs* → *Count*: type a lower figure, the shortage appears live, notes become
   required → approve with discrepancy. *Bank deposits* → cash in safe → record deposit; reuse an old
   reference to show the duplicate-reference error.
5. `finance` → *Settlements*: the delayed Bengaluru deposit; match a credit ₹100 short → mismatch + discrepancy.
6. Dashboard as admin: money trail (with agents → awaiting count → safe → in transit → credited), period
   lifecycle bar, discrepancies by stage, branch table; filter by branch/agent.
7. *Audit trail*: every action with actor and IP.

**3:40–4:20 · Business rules & trade-offs.** Customer liability is discharged at the receipt; losses after that
belong to staff, not the customer. Deposits are compared with cash *counted* — so an agent shortage isn't
double-reported. Failed deposit returns cash to the safe. JWT in localStorage vs httpOnly cookies; no Celery
because nothing needs async yet; gateway left out to keep the cash path rigorous.

**4:20–4:50 · Challenges & next steps.** Making immutability real (ORM guards are bypassable → triggers, tested);
history vs current state; float-free frontend. Next: UPI via gateway sandbox entering at DEPOSITED,
bank statement import for auto-matching, Celery alerts for SLA breaches, offline agent PWA.
