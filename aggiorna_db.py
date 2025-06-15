import sqlite3

DATABASE = 'spese.db'

print("--- Avvio script di aggiornamento database ---")
con = sqlite3.connect(DATABASE)
cur = con.cursor()

# Funzione per aggiungere una colonna in modo sicuro
def aggiungi_colonna(tabella, colonna, tipo):
    try:
        print(f"Aggiungo colonna '{colonna}' alla tabella '{tabella}'...")
        cur.execute(f"ALTER TABLE {tabella} ADD COLUMN {colonna} {tipo}")
        print(f"Colonna '{colonna}' aggiunta con successo.")
    except sqlite3.OperationalError as e:
        # Controlla se l'errore è dovuto a una colonna già esistente
        if "duplicate column name" in str(e):
            print(f"La colonna '{colonna}' esiste già. Nessuna modifica apportata.")
        else:
            # Se l'errore è diverso, lo solleva per non nascondere altri problemi
            raise e

# Aggiorna la tabella 'spese'
aggiungi_colonna('spese', 'pagato_da', 'TEXT')

# Aggiorna la tabella 'entrate'
aggiungi_colonna('entrate', 'ricevuto_da', 'TEXT')

con.commit()
con.close()

print("\n--- Aggiornamento database completato con successo! ---")
print("Ora puoi eseguire lo script di importazione.")