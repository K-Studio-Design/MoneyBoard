# MoneyBoard

**Personal finance that stays on your computer.**
Track spending, income, subscriptions, savings goals and investments in a clean dashboard. No cloud account,
no servers: all your data stays in a local database on your own machine.

*Made by **K Studio Design** in Italy · version 1.2.1 · free for personal and noncommercial use
([PolyForm Noncommercial 1.0.0](LICENSE.md)) · [Leggi in italiano](README.it.md)*

**▶ [Try the live demo](https://moneyboard-demo.streamlit.app)** — no install, no sign-up, made-up data.

![MoneyBoard demo](docs/media/moneyboard-demo.gif)

> All names, amounts and transactions in these screenshots are made-up demo data.

## Features

- **Overview**: this month's spending and income compared with last month, the last 12 months, spending by
  category and a month-end forecast.
- **Transactions**: add, edit, filter and export to CSV. Categories are assigned automatically by hundreds of built-in
  keywords plus your own rules. Click any transaction to see how often and how much you spend there.
- **Budgets**: a monthly cap per category (and for total spending), with progress bars, a daily allowance for the
  rest of the month and alerts at 80% and when you go over. One click fills them in from your last 3 months.
- **Split transactions**: split one payment across several categories (for example an online order with a gift and
  something for the house). The total stays the one from the bank.
- **Shared expenses**: keep track of money with friends, a partner or roommates. Share part of an expense you paid,
  link repayments, and see who owes whom. Only your part counts in your spending.
- **Analysis**: any period you like, with totals, averages, savings rate, trends, top merchants and a
  months × categories table.
- **Calendar**: each day colored by how much you spent, plus the charges expected in the coming days.
- **Subscriptions**: recurring payments are detected automatically, with monthly and yearly cost, next charge
  and price changes.
- **Salary schedule**: tell the app when you get paid (last or first working day, any days of the month such as
  the 15th and the 31st, every week or every 2 weeks, with Italian or US holidays), and it predicts your next
  paychecks.
- **Alerts and reminders**: possible double charges, unusual expenses, categories above average, budgets at 80% or
  over, new or more expensive subscriptions, and reminders of charges coming up in the next few days.
- **Email (optional)**: a monthly summary on the 1st and reminders of upcoming charges, sent through your own email
  account (Gmail, iCloud, Yahoo or any SMTP server).
- **Goals**: savings goals with deadlines, from manual deposits, an account balance or your savings since a date.
- **Investments**: securities by ISIN with live prices (Yahoo Finance), gains and losses, dividends and
  taxes read from your statements, plus read-only balances from crypto exchanges.
- **Currencies**: multi-currency accounts converted at ECB rates, plus a currency converter.
- **Import**: ready-made profiles for 60+ banks (Italy, US, UK, Germany, France, Spain, the Netherlands…), any CSV
  or Excel file with column mapping, and the OFX/QFX, QIF, CAMT.053 and MT940 standard formats.
  Duplicates are skipped automatically. A watched folder imports new statements by itself.
- **Bank sync (optional)**: automatic daily sync through Open Banking (PSD2) with
  [Enable Banking](https://enablebanking.com), using your own free account.
- **US taxes (alpha, optional)**: an estimate of federal, state and FICA taxes, based on your salary, payslips and
  1099 forms. It's an estimate, not tax advice.
- **Multiple users**: each person gets separate data and a password. A demo account with made-up data is also available.
- **Themes and languages**: light, dark, automatic and "Liquid Glass" themes. The interface is in English or Italian.
- **Phone friendly**: the layout adapts to small screens, so you can use it from your phone (for example with the
  app running on a NAS at home).
- **Update notice**: the app tells you when a new version is published here (you can turn it off).

## Screenshots

| | |
|---|---|
| ![Overview](docs/media/01-overview.png) | ![Transactions](docs/media/02-transactions.png) |
| **Overview** | **Transactions** |
| ![Transaction detail](docs/media/13-transaction-detail.png) | ![Analysis](docs/media/03-analysis.png) |
| **Transaction detail** | **Analysis** |
| ![Calendar](docs/media/04-calendar.png) | ![Subscriptions](docs/media/05-subscriptions.png) |
| **Calendar** | **Subscriptions** |
| ![Alerts](docs/media/06-alerts.png) | ![Goals](docs/media/07-goals.png) |
| **Alerts** | **Goals** |
| ![Investments](docs/media/08-investments.png) | ![Cards](docs/media/09-cards.png) |
| **Investments** | **Cards** |
| ![Budgets](docs/media/14-budgets.png) | ![Shared expenses](docs/media/15-shared-expenses.png) |
| **Budgets** | **Shared expenses** |
| ![Split a transaction](docs/media/16-split-transaction.png) | ![On the phone](docs/media/17-phone.png) |
| **Split a transaction** | **On the phone** |
| ![Light theme](docs/media/10-overview-light.png) | ![Liquid Glass theme](docs/media/11-overview-liquid-glass.png) |
| **Light theme** | **Liquid Glass theme** |
| ![First run](docs/media/00-first-run.png) | ![Sign in](docs/media/12-sign-in.png) |
| **First run: create your account** | **Sign in** |

## Getting started

You need **Python 3.10 or newer**.

1. Download the app: click the green **Code** button → **Download ZIP**, and unzip it.
2. Start it:
   - **Windows**: install Python from [python.org](https://www.python.org/downloads/) and tick
     **"Add python.exe to PATH"** during setup. Then double-click **`avvia_app.bat`**.
   - **macOS / Linux**: open a terminal in the app folder and run `chmod +x avvia_app.sh` (first time only), then
     `./avvia_app.sh`.

   The first start creates a private Python environment and installs the packages. This takes a few minutes.
   After that the app opens in your browser in a few seconds.
3. **Create your account.** The first time you open the app it asks for a username and password. You become the
   administrator. There are no default accounts or passwords.
4. Pick your language (IT / EN) and import your first bank statement from the avatar menu → **Import statements**.

Manual start on any system: `pip install -r requirements.txt`, then `streamlit run app.py`.
To update the packages, run `avvia_app.bat aggiorna` or `./avvia_app.sh aggiorna`.

## Privacy and security

- Your data (SQLite database, imported statements, backups, bank keys) lives in a data folder on your computer.
  By default this is `AppSpese_dati` in your user folder, outside the app folder. You can move the data folder
  and set up automatic backups from Settings → Folders & backup.
- Passwords are never stored. The app keeps only a salted PBKDF2-SHA256 hash (300,000 iterations). After 5 wrong
  attempts, sign-in is locked for one minute.
- The app goes online only for:
  - exchange rates (ECB via Frankfurter, Yahoo Finance);
  - security prices (Yahoo Finance);
  - your bank and crypto exchanges, and only if you connect them yourself;
  - your email server, only if you turn on emails;
  - once a day, GitHub's public API to check for a new version (no app data is sent; it can be turned off in
    Settings → General).

  No analytics are sent, and Streamlit's usage statistics are turned off.
- **Forgot the administrator password?** Close the app, delete `amministratore.json` from the data folder and
  open the app again. It will ask you to create the account again, and all your data stays. This also means that
  anyone who can open the files on your computer can get into the app, so protect your computer with its own
  password.

## Online demo

**Try it now: [moneyboard-demo.streamlit.app](https://moneyboard-demo.streamlit.app)** (if it has been idle for a while, click the button to wake it up and wait a few seconds).

The app has a demo mode for trying it in the browser. With the setting `MONEYBOARD_DEMO = "1"` it doesn't ask for
a sign-in: every visitor gets their own sandbox with made-up data, which is deleted after a few hours. Bank
connections, folders, backups and emails are turned off. To publish it for free on
[Streamlit Community Cloud](https://streamlit.io/cloud), create an app from this repository (main file `app.py`)
and add `MONEYBOARD_DEMO = "1"` to its **Secrets**. Never use demo mode with your real data.

## Built with

[Python](https://www.python.org) · [Streamlit](https://streamlit.io) · [pandas](https://pandas.pydata.org) ·
[Plotly](https://plotly.com/python/) · [yfinance](https://github.com/ranaroussi/yfinance) ·
[ccxt](https://github.com/ccxt/ccxt) · [pdfplumber](https://github.com/jsvine/pdfplumber) · SQLite

## License

Copyright © 2026 K Studio Design, Italy.

MoneyBoard is **source-available** under the **PolyForm Noncommercial License 1.0.0**. The full text is in
[LICENSE.md](LICENSE.md). In short, and without replacing the license text:

- you may use, copy, modify and share it **free of charge for any noncommercial purpose**: personal use, study,
  hobby projects, charities, schools and public institutions;
- if you share it, modified or not, you must include the license and the `Required Notice:` line;
- you may **not** sell it or use it to make money, for example as a paid service, without permission from
  K Studio Design;
- it comes as is, without any warranty.

MoneyBoard is a personal finance tool, not financial or tax advice.
