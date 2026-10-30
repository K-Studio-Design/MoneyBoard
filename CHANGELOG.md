# Changelog

## 1.2.1 (2026-10-30)

- **Revolut pockets**: Revolut doesn't share pockets with linked apps, so MoneyBoard follows them from the transfers
  in the main account ("To EUR MB:…" / "From EUR MB:…"): each pocket becomes its own account, with its balance
  included in the totals, and the transfers count neither as spending nor as income. You can rename it in
  Connect banks (for example "Revolut Taxes").
- If a bank does share a new account (or pocket), link the bank again and select all accounts: it appears with its
  own balance.
- **Renewing a bank link no longer duplicates anything**: accounts you already had are recognized (Enable Banking
  gives new ids at every consent), keep their name in the app and history, and transactions aren't downloaded twice.
- Moving money between two linked accounts of the same bank (for example into a pocket) counts as a transfer on
  both sides, not as spending or income.
- Cards: pockets show up as their own entries next to the main account (you can hide one from the card itself,
  and show it again from Connect banks).
- Connect banks: each linked account has its own sync button, so you can sync just one account.

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
