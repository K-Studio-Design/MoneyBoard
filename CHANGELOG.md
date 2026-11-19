# Changelog

## 1.5.2 (2026-11-19)

**Fixes**
- Month-end forecast and calendar: the salary could disappear from the expected credits when the bank started
  writing its description differently (for example after switching from statement import to the direct bank
  connection, "Salary from COMPANY…" became "Ord: COMPANY Ben: …"). All credits in the Salary category are now
  one series, whatever the description says, so the next salary is expected again on its date.
- Recurring payments are no longer split when the same charge comes with different descriptions (e.g.
  "SpotifyIT Stockholm" and "Spotify P47BC8C353 Stockholm", or "CLAUDE" and "Anthropic* Claude Sub"): same
  account, category and amount on the usual schedule count as the same subscription, so it stays active and
  shows up in the expected charges. Occasional spending categories (restaurants, groceries…) are never merged.
- Incoming SEPA transfers written as "Ord: <payer> Ben: <payee> …" are now grouped by who paid.

## 1.5.1 (2026-11-14)

**Donut charts**
- Hovering a slice (or its row in the legend) lifts it above the others with a soft pop, and the centre of the
  chart shows its name, amount and share. On a phone, tap a slice.
- Large-enough slices show a small icon of their category (cart for groceries, house for rent, plane for travel,
  and so on); slices that are too small for the icon to fit entirely inside them show none. Custom categories get
  an icon from their name or emoji.
- Clicking a slice in the Overview opens the category detail, like the legend.
- The charts by currency (Analysis) and by holding and type (Investments) use the same donut, with currency and
  asset-type icons.
- Icons from Lucide (ISC license).

## 1.5.0 (2026-11-14)

**AI assistant (optional)**
- New *Assistant* page: ask questions about your money in plain words ("where did I spend the most this month?",
  "will I reach my goals?") and get answers from Claude, by Anthropic, based on your MoneyBoard data. Answers
  appear as they're written.
- It works with your own Anthropic API key (Claude Console → API keys), which you pay per use directly to
  Anthropic: usually a few cents per question. The key is stored encrypted. Set it up from the Assistant page or
  in *Settings → AI assistant*, where you also pick the model.
- Nothing is sent until you agree. With each question the app sends a summary of your data (totals by month and
  category, top merchants, budgets, goals, recurring payments, balances and, if you leave it on, the latest 80
  transactions), never the database, files or passwords. The assistant is off in the online demo.

**Animations**
- Pages come in with a soft staggered rise, amounts count up to their value, progress bars and the small daily
  charts in the summary cards grow, chart bars rise one after another and lines draw from left to right. Charts
  animate only the first time and when their data changes, not at every click.
- Tabs are a pill bar with a sliding highlight. Everything stays still if your system asks for reduced motion.

**Look**
- Overview: a "Today" badge with today's transactions, 30-day mini charts in the Spending and Income cards, and a
  summary under the 12-month chart (income, spending, monthly average, saved).
- Budget: a gauge with how much of the month's budget is spent, what's left, the month-end forecast and how much
  you can spend per day.
- Goals: the progress rings fill up when the page opens.

## 1.4.0 (2026-11-12)

**Security**
- The app now opens only on the computer it runs on. To use it from a phone or tablet on your home network, turn
  on *Settings → General → Access from other devices on the network* and restart it with `avvia_app`.
- Users created by the administrator can use only their own data folder for database, statements and backups.
  Before, a user could point the statements folder at another folder of the computer and read (and move) files
  that weren't theirs.
- Automatic import no longer moves files it doesn't recognize: they stay where they are and aren't checked again
  until they change. Files over 50 MB are skipped.
- Sign-in lock after 5 wrong attempts now applies to that username only, so nobody can lock everyone out.
- Email password and crypto exchange API keys are stored encrypted (the key is in the data folder and is not part
  of backups). Older plain-text values are encrypted automatically.
- Imported files and pictures that would take gigabytes of memory once opened (zip bombs, huge images) are refused.
- CSV exports can no longer carry spreadsheet formulas from bank descriptions.
- Notes and names coming from the bank are shown as plain text (no links or remote images).
- Online demo: at most 300 visitor accounts at a time.

**Fixes**
- A category color that isn't a valid #RRGGBB code no longer breaks the Analysis page; it's checked when you save.
- Budget table: empty cells show "–" instead of "None", amounts use your browser's number format.
- Imports ignore amounts like "inf" or "NaN" and understand the typographic minus sign (−).
- Calendar on the phone: amounts no longer cut off. Chart axis labels are no longer clipped.
- Overview chart: month labels no longer overlap at the turn of the year.
- Cards: no stray dash when the balance isn't synced.
- Page header: search, alerts and avatar stay on one line even with long subtitles.
- Settings → Folders & backup reads the database only when you download a copy, not at every visit.

**Look and navigation**
- Overview opens with your account balance today. Early in the month, a negative month balance says that this
  month's income hasn't arrived yet instead of "spending is higher than income".
- Calmer summary cards: neutral background with a colored accent, in every theme.
- Alerts have a bell with the count next to the avatar. The side menu is grouped into Spending, Plan and Assets;
  Cards (now "Cards and accounts") moved into it. "Subscriptions" is now "Recurring".
- On the phone: a bottom bar with the main pages, a more compact header.
- Transactions are grouped by day, with each day's spending; categories and type are under "Filters".
- Budgets turn orange when, at the current pace, you'll go over.
- Liquid Glass theme: category labels are easier to read.

## 1.3.1 (2026-11-12)

Faster and smoother, with nothing removed:

- Pages open faster: settings and transactions are read from the database once per page instead of dozens of
  times (about 85% fewer database opens), and recurring payments and alerts are computed about twice as fast.
- The first page after signing in no longer computes alerts twice.
- Exchange rates: today's rate is kept for a few minutes instead of being downloaded at every click, and the
  US taxes page no longer downloads rates it already has.
- Smoother scrolling with the Liquid Glass theme (the colored background is drawn once instead of at every
  scroll, and small buttons no longer blur what's behind them).
- No more "fading" of the page at every click: it dims slightly only when an update takes long.
- Respects the system setting to reduce motion.

## 1.3.0 (2026-11-03)

- **Goal pictures**: every goal has an image on its card. By default the app picks one of 15 built-in illustrations
  from the goal's name (emergency fund, vacation, trip, home, car, education, retirement, wedding, tech, gifts,
  taxes, family, pets, health, savings); you can choose another one, upload your own photo or turn it off.
- **Cards that look like cards**: in Cards, every card and account is drawn like a real card (bank, last digits,
  name, chip). Choose its color, or upload the card design from your bank's app; the image is cropped to the shape
  of a card and stays in your database.
- Fixed: the progress ring on goals wasn't showing.

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
