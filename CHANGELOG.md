# Changelog

## 1.2.0 (2026-10-28)

- **Budgets**: a monthly cap per category and for total spending, with progress bars, a daily allowance for the rest
  of the month and alerts at 80% and when you go over. "Use the last 3 months' average" fills them in for you.
- **Split transactions**: from a transaction's details, split it across several categories. The total stays the one
  from the bank, and re-importing the same statement or syncing the bank doesn't create duplicates.
- **Shared expenses**: share part of an expense you paid with someone, link repayments, and see who owes whom.
  Only your part counts in your spending.
- **Reminders** of recurring charges coming up in the next few days, in Alerts and (optionally) by email.
- **Email (optional)**: a monthly summary on the 1st and reminders of upcoming charges, through your own email account.
- **New version notice** in the sidebar (checks GitHub once a day; can be turned off).
- **Phone layout**: compact top bar, two cards per row, a readable calendar and buttons side by side.
- **Online demo mode** (`MONEYBOARD_DEMO = "1"`): a private sandbox with made-up data for every visitor, in English.
- New category "Shared expenses" (neutral: it doesn't count as spending or income).

## 1.1.0 (2026-10-27)

- **Salary schedule**: in Profile → "Salary arrives" you can now choose
  - one or more days of the month (for example the 15th and the 31st, if you're paid twice a month),
  - every week or every 2 weeks, counted from any payday,
  - what happens when a payday falls on a weekend or holiday (the working day before, the working day after, or keep
    the date), with Italian or US public holidays.
  The calendar, the "Coming up" list and the month-end forecast use these dates, even after just one or two paychecks.
- Payments repeating every 2 weeks are now recognized automatically.

## 1.0.0 (2026-10-26)

- First public release.
