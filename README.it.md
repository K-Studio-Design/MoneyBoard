# MoneyBoard 💶

*[Read in English](README.md)*

App per gestire spese, entrate, abbonamenti, obiettivi di risparmio e investimenti, con i dati salvati **solo sul
tuo computer** (nessun server, nessun account online). Interfaccia in italiano e in inglese.

Fatta da **K Studio Design** in Italia · versione 1.1.0 · licenza
[PolyForm Noncommercial 1.0.0](LICENSE.md): gratuita per uso personale e non commerciale (vedi sotto).

## Avvio rapido

### Windows
1. Installa **Python 3.10 o più recente** da <https://www.python.org/downloads/>
   e durante l'installazione spunta **"Add python.exe to PATH"**.
2. Fai doppio clic su **`avvia_app.bat`**.
   Al primo avvio crea l'ambiente e installa i pacchetti (qualche minuto), poi apre il browser.
   Dalle volte successive parte in pochi secondi.
   Per aggiornare i pacchetti: da terminale `avvia_app.bat aggiorna`.

### macOS / Linux
1. Serve **Python 3.10 o più recente** (`python3 --version`).
2. Da terminale, nella cartella dell'app: `chmod +x avvia_app.sh` (solo la prima volta) e poi `./avvia_app.sh`.
   Per aggiornare i pacchetti: `./avvia_app.sh aggiorna`.

Avvio manuale (qualsiasi sistema): `pip install -r requirements.txt` e poi `streamlit run app.py`.

## Primo avvio: il tuo account

La prima volta che apri l'app ti chiede di **creare il tuo account** (nome utente e password, almeno 8 caratteri):
sarai l'**amministratore**. Non ci sono account o password predefiniti.

- La password non viene mai salvata in chiaro: solo la sua impronta PBKDF2-SHA256 (300.000 iterazioni, sale
  casuale) nel file `amministratore.json` della cartella dati.
- Dal menu dell'avatar (in alto a destra) → **Utenti** puoi cambiare il tuo nome e la tua password e creare altri
  utenti (per esempio i familiari). Ognuno ha i **suoi dati separati** in `AppSpese_dati/utenti/<nome>` e non può
  vedere né usare le cartelle degli altri. Un utente creato come **account di prova** parte con circa 460
  movimenti fittizi, utile per far provare l'app.
- Se cambi la password di un utente o lo elimini, le sue sessioni aperte e i suoi «resta connesso» si chiudono.
- Il nome utente non distingue maiuscole e minuscole, la password sì. Dopo 5 tentativi sbagliati l'accesso si
  blocca per un minuto. «Resta connesso su questo browser per 30 giorni» evita di riscrivere la password.

**Password dell'amministratore dimenticata?** Chiudi l'app, cancella il file `amministratore.json` nella cartella
dati (`AppSpese_dati` nella tua cartella utente) e riapri: l'app ti chiede di creare di nuovo l'account. I dati
(movimenti, impostazioni, altri utenti) restano tutti. Proprio per questo chi può accedere ai file del tuo computer
può accedere anche all'app: proteggi il computer con la sua password.

## Privacy

- Tutti i dati (database SQLite, estratti, backup, chiavi delle banche) stanno nella cartella dati sul tuo
  computer, di default `AppSpese_dati` nella tua cartella utente, fuori dalla cartella dell'app.
- L'app si collega a internet solo per: cambi valuta (BCE/Frankfurter, Yahoo Finance), quotazioni dei titoli
  (Yahoo Finance), e, solo se li configuri tu, le banche (Enable Banking) e gli exchange crypto (API in sola
  lettura). Nessuna statistica d'uso viene inviata (anche quella di Streamlit è disattivata).
- La funzione **Tasse USA** (Profilo → Funzioni in prova) è in **alpha**: è una stima, non una consulenza
  fiscale. Verifica sempre con un professionista.

## Lingua (italiano / inglese)

L'app è in italiano o in inglese. La lingua si sceglie:
- nella schermata di accesso (IT / EN in alto a destra);
- dal menu dell'avatar (riga «Lingua»), dal Profilo o da *Impostazioni → Generali*.

Ogni utente ha la sua lingua (salvata nel suo database) e il browser ricorda l'ultima usata per la schermata di
accesso. In inglese cambiano anche i formati: date MM/DD/YYYY, importi €1,234.56, CSV esportati con virgola come
separatore. Restano come sono i **dati**: nomi delle categorie e dei conti, descrizioni dei movimenti.
Le traduzioni stanno in `core/i18n_en.py` (testo italiano → testo inglese).

## Carte

Menu dell'avatar → **Carte**: le carte trovate nei movimenti (dal numero scritto nella descrizione, per esempio
«Carta N. ***** 123» di Fineco) e quelle collegate via Open Banking, con lo speso del mese, il saldo sincronizzato
dalla banca e, cliccando, tutte le spese fatte con quella carta. Nome personalizzabile, carte vecchie nascondibili.
Per riconoscere le carte anche nello storico, importa di nuovo l'ultimo estratto Fineco (i movimenti non si
duplicano). Revolut non indica con quale carta è stato fatto un pagamento.

## Estratti e collegamento banca insieme

Si possono usare entrambi: lo stesso movimento arrivato dall'estratto e dal collegamento viene riconosciuto
(stesso conto, valuta e importo, data vicina) e tenuto una volta sola. In *Collega banche* scegli per ogni
collegamento il **conto dell'app** (lo stesso degli estratti, es. «Fineco»); se ci sono doppioni già presenti,
compare il riquadro «Movimenti doppi» con il pulsante per toglierli (prima fa un backup).

## Conti e valute

Nella barra laterale:
- **Conti**: scegli Fineco, Revolut o entrambi; vale per Panoramica, Movimenti e Analisi.
- **Valuta**: «Tutte, convertite in EUR» (ogni importo convertito; per Revolut si usa il cambio
  effettivamente applicato da Revolut) oppure «Solo USD» ecc. per vedere solo i movimenti in quella
  valuta con gli importi originali.
In *Analisi → Per valuta* trovi spese ed entrate divise per valuta, in originale e in euro.
Le scelte restano salvate anche chiudendo l'app.

## Temi

In fondo alla barra laterale ci sono quattro icone: sole (chiaro), luna (scuro), mezzo cerchio
(automatico, segue Windows) e **Liquid Glass** (card e barra laterale di vetro traslucido sopra uno
sfondo colorato, in stile Apple). Accanto, il pulsante circolare aggiorna le quotazioni.
La scelta resta salvata. Il carattere è Segoe UI Variable, già installato su Windows 11 (su sistemi
senza questo font si usa Segoe UI o il carattere di sistema): non serve internet. L'effetto vetro richiede un browser recente (Chrome, Edge, Safari).

## Dove sono i dati

Tutto si configura in *Impostazioni → Cartelle e backup* (menu dell'avatar in alto a destra):
- **Database**: di default `C:\Users\<utente>\AppSpese_dati\spese.db`, fuori da OneDrive apposta (dati bancari
  privati e SQLite non va d'accordo con la sincronizzazione). Si può spostare in un'altra cartella con
  «Sposta il database qui»: prima viene fatto un backup, la copia vecchia resta dov'era.
- **Estratti da importare**: metti in questa cartella i file scaricati da Fineco, Revolut, Chase (o l'export del
  portafoglio titoli). All'avvio dell'app, e poi ogni 30 secondi mentre è aperta, vengono importati da soli (senza
  doppioni) e spostati in «Importati/AAAA-MM»; quelli non riconosciuti finiscono in «Non riconosciuti».
- **Backup**: copia automatica del database ogni N giorni (default 7), tenendo gli ultimi N (default 8).
  Consigliato scegliere una cartella di OneDrive (pulsante «Usa OneDrive»). Da lì si può anche ripristinare.

## Funzioni

| Pagina | Cosa fa |
|---|---|
| 🏠 Panoramica | Spese/entrate del mese vs mese scorso, ultimi 12 mesi, categorie, **previsione a fine mese** (accrediti e addebiti attesi + spesa quotidiana tipica; con i saldi reali indicati nel Profilo prevede il saldo dei conti e avvisa se rischi di andare in rosso), patrimonio. Le quattro card colorate sono cliccabili: spese (andamento giorno per giorno contro il mese scorso, categorie, negozi, spese più alte), entrate, saldo (mese per mese e perché è negativo), media al giorno |
| 🔎 Ricerca | Casella in alto in ogni pagina: cerca nelle descrizioni, note, categorie, conti o per importo (es. 6,99); mostra totale, andamento e movimenti |
| 👤 Profilo | Clic sull'avatar in alto a destra: nome, colore dell'avatar, intestatari dei conti, riepilogo dei conti importati; dallo stesso menu si aprono Importa estratti, Collega banche e Impostazioni |
| 🔎 Dettaglio | Clic su un movimento (Panoramica o Movimenti): importo, data, quante volte e quanto hai speso da quell'esercente, andamento mensile, peso sul mese; cambio categoria anche per tutti i movimenti simili |
| 🗂️ Dettaglio categoria | Clic su una categoria (legenda della ciambella in Panoramica, barre in *Analisi → Per categoria*): totale del periodo, confronto col periodo precedente e con la media mensile, andamento a 12 mesi, dove spendi, elenco dei movimenti (cliccabili). «Altre N categorie» mostra tutte le voci |
| 🧾 Movimenti | Inserimento manuale in qualsiasi valuta (cambio automatico alla data), modifica, eliminazione, filtri, export CSV, regole |
| 📊 Analisi | Periodi preimpostati o personalizzati; totali, medie (mensile/giornaliera/per movimento), tasso di risparmio, confronto col periodo precedente, grafici per mese e categoria, andamento, top esercenti, tabella mesi × categorie |
| 📅 Calendario | Il mese come calendario: ogni giorno colorato in base a quanto hai speso, entrate in verde, addebiti previsti (abbonamenti, stipendio) nei giorni futuri. Clic su un giorno per i movimenti; giorni senza spese, giorno più costoso, spesa media per giorno della settimana |
| 🔁 Abbonamenti | Pagamenti ricorrenti trovati in automatico (le date previste tengono conto di regole come «ultimo giorno lavorativo del mese», con weekend e festività italiane; per lo stipendio si sceglie nel Profilo: ultimo o primo giorno lavorativo, uno o più giorni del mese a scelta, ogni settimana o ogni 2 settimane, con festività italiane o americane) (Netflix, Spotify, rate, canoni, bollette…): costo al mese e all'anno, prossimo addebito, cambi di prezzo, quelli non più addebitati; entrate ricorrenti (stipendio). Si possono rinominare o nascondere |
| 🔔 Avvisi | Possibili addebiti doppi, spese molto più alte del solito presso lo stesso negozio, le spese più alte dell'anno, categorie già sopra la media del mese, abbonamenti nuovi, aumentati o non più addebitati. Il numero compare nel menu; «Ignora» li toglie |
| 🎯 Obiettivi | Obiettivi di risparmio con scadenza: versamenti a mano, saldo di un conto (es. il conto deposito) oppure risparmio (entrate meno spese) da una data. Avanzamento, quanto serve al mese, previsione al ritmo attuale, confronto con il tuo risparmio medio |
| 📥 Importa (menu dell'avatar) | Estratti **Fineco** (Excel), **Revolut** (estratto *consolidato* Excel con tutti i conti/valute, oppure CSV), **Chase** (CSV del conto o della carta, oppure QFX/OFX: riconosce da solo il tipo, i pagamenti della carta, gli Zelle verso te stesso e i resi), o qualunque CSV/Excel con mappatura colonne. Duplicati ignorati, categorie automatiche |
| 🏦 Collega banche (menu dell'avatar) | Sincronizzazione automatica via Open Banking (Enable Banking) per Fineco, Revolut e altre banche UE |
| 📈 Investimenti | Dividendi, ritenute, bollo e imposte sul capital gain letti dagli estratti (con le quote possedute), import dell'export del portafoglio titoli (colonne ISIN e Quantità), rendimento netto complessivo; titoli per ISIN (ticker trovato in automatico), operazioni di acquisto/vendita, prezzo medio, P/L latente e realizzato, grafici; saldi degli exchange crypto via API in sola lettura |
| 💱 Valute | Convertitore (anche storico e crypto), grafico del cambio, tabella cambi |
| ⚙️ Impostazioni (menu dell'avatar) | Valuta base, categorie, regole automatiche, backup |

### Categorie
32 categorie predefinite (spesa alimentare, ristoranti e bar, casa, bollette, carburante, abbonamenti…),
quasi 600 parole chiave per riconoscere negozi e servizi più comuni (Italia e anche USA). Le categorie **neutre**
(giroconti, investimenti) non contano nei totali, così la ricarica Revolut da Fineco non viene contata due volte.
Se correggi a mano una categoria, la regola automatica non la sovrascrive più.
I **bonifici tra i tuoi conti** (es. da Fineco a Revolut) vengono riconosciuti dal nome
dell'intestatario, letto in automatico dall'estratto Fineco (modificabile nel *Profilo*),
e non contano come spese/entrate. Le ricariche Satispay contano come spesa (gli acquisti fatti
con Satispay non compaiono nell'estratto). Storni e sconti riducono la spesa della categoria originale.

### Fonti dati
- **Cambi**: BCE tramite Frankfurter (gratuito, senza chiave) e Yahoo Finance come riserva.
- **Quotazioni**: Yahoo Finance (`yfinance`). Google Finance non ha un'API pubblica, quindi non è collegabile da Python.
- **Banche**: Enable Banking (PSD2). GoCardless/Nordigen non accetta nuove iscrizioni dal 2025.
- **Exchange**: libreria `ccxt` (Binance, Kraken, Coinbase, Bitvavo, Bitstamp, OKX, Bybit…).

## Collegare Fineco e Revolut in automatico
Vedi la guida nella pagina *🏦 Collega banche* (menu dell'avatar in alto a destra). In sintesi: account gratuito su enablebanking.com →
crei un'applicazione *Production* (modalità restricted per uso personale) → scarichi il `.pem` →
fai *Link accounts* dei tuoi conti nel Control Panel → inserisci Application ID e `.pem` nell'app.
Il consenso PSD2 scade in genere dopo 90–180 giorni e va rinnovato.

## Licenza

Copyright © 2026 K Studio Design, Italia.

MoneyBoard è distribuita con la licenza **PolyForm Noncommercial 1.0.0** (testo completo in
[LICENSE.md](LICENSE.md)). In breve, e senza sostituire il testo della licenza:
- puoi usarla, copiarla, modificarla e condividerla **gratis per scopi non commerciali** (uso personale, studio,
  hobby, enti non profit, scuole…);
- chi la ridistribuisce (anche modificata) deve includere la licenza e la riga `Required Notice:`;
- **non** puoi venderla né usarla per guadagnarci (per esempio come servizio a pagamento) senza il permesso
  di K Studio Design;
- è fornita «così com'è», senza garanzie.
