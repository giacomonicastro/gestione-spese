DROP TABLE IF EXISTS spese;

CREATE TABLE spese (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT NOT NULL,
    descrizione TEXT NOT NULL,
    categoria TEXT NOT NULL,
    importo REAL NOT NULL,
    pagato_da TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- NUOVA TABELLA PER LE ENTRATE
DROP TABLE IF EXISTS entrate;

CREATE TABLE entrate (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT NOT NULL,                 -- Data dell'entrata
    tipo_entrata TEXT NOT NULL,         -- Es. "Stipendio", "Bonus", "Regalo", "Vendita", "Extra"
    descrizione TEXT,                   -- Motivazione o dettaglio aggiuntivo (opzionale)
    importo REAL NOT NULL,              -- Importo dell'entrata (sempre positivo)
    ricevuto_da TEXT NOT NULL,          -- Chi ha ricevuto l'entrata: "Giacomo" o "Erica"
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);