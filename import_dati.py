import csv
import sqlite3
import argparse
from datetime import datetime

DATABASE = 'spese.db'

def import_spese(file_path):
    """Importa i dati delle spese da un file CSV nel database."""
    con = sqlite3.connect(DATABASE)
    cur = con.cursor()
    
    righe_inserite = 0
    righe_lette = 0

    print(f"\n--- Inizio importazione SPESE dal file: {file_path} ---")

    try:
        with open(file_path, mode='r', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile, delimiter=';')
            
            for row in reader:
                righe_lette += 1
                
                # --- NUOVO CONTROLLO: Salta le righe vuote o malformate ---
                if not row or not row.get('data'):
                    print(f"INFO alla riga {righe_lette + 1}: Trovata riga vuota o malformata. Riga saltata.")
                    continue
                
                data_str = row.get('data')
                importo_str = row.get('importo')
                categoria = row.get('categoria')
                pagato_da = row.get('pagato_da')

                try:
                    datetime.strptime(data_str, '%Y-%m-%d')
                    
                    # Controlla che importo non sia nullo prima di usare .replace()
                    if importo_str is None:
                        raise ValueError("La colonna 'importo' è mancante o vuota.")
                    importo = float(importo_str.replace(',', '.'))

                    if importo <= 0:
                        raise ValueError("L'importo deve essere positivo.")
                        
                    if not categoria or not categoria.strip():
                        raise ValueError("La categoria non può essere vuota.")
                        
                    if pagato_da not in ['Giacomo', 'Erica']:
                        raise ValueError(f"Valore non valido per 'pagato_da': '{pagato_da}'")

                except (ValueError, TypeError) as e:
                    print(f"ERRORE alla riga {righe_lette + 1}: {e} -> Dati: {row}")
                    continue

                descrizione = row.get('descrizione', '')
                
                cur.execute(
                    "INSERT INTO spese (data, descrizione, categoria, importo, pagato_da) VALUES (?, ?, ?, ?, ?)",
                    (data_str, descrizione, categoria, importo, pagato_da)
                )
                righe_inserite += 1

        con.commit()
        print(f"--- Importazione SPESE completata ---")
        print(f"Righe lette: {righe_lette}")
        print(f"Righe inserite con successo: {righe_inserite}")

    except FileNotFoundError:
        print(f"ERRORE: File non trovato all'indirizzo '{file_path}'.")
    except Exception as e:
        print(f"ERRORE CRITICO durante l'importazione: {e}")
        con.rollback()
    finally:
        con.close()


def import_entrate(file_path):
    # Logica identica per le entrate
    con = sqlite3.connect(DATABASE)
    cur = con.cursor()
    righe_inserite = 0
    righe_lette = 0
    print(f"\n--- Inizio importazione ENTRATE dal file: {file_path} ---")
    try:
        with open(file_path, mode='r', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile, delimiter=';')
            for row in reader:
                righe_lette += 1
                
                # --- NUOVO CONTROLLO: Salta le righe vuote o malformate ---
                if not row or not row.get('data'):
                    print(f"INFO alla riga {righe_lette + 1}: Trovata riga vuota o malformata. Riga saltata.")
                    continue

                data_str = row.get('data')
                importo_str = row.get('importo')
                tipo_entrata = row.get('tipo_entrata')
                ricevuto_da = row.get('ricevuto_da')
                try:
                    datetime.strptime(data_str, '%Y-%m-%d')
                    
                    if importo_str is None:
                        raise ValueError("La colonna 'importo' è mancante o vuota.")
                    importo = float(importo_str.replace(',', '.'))
                    
                    if importo <= 0: raise ValueError("L'importo deve essere positivo.")
                    if not tipo_entrata or not tipo_entrata.strip(): raise ValueError("Il tipo_entrata non può essere vuoto.")
                    if ricevuto_da not in ['Giacomo', 'Erica']: raise ValueError(f"Valore non valido per 'ricevuto_da': '{ricevuto_da}'")
                except (ValueError, TypeError) as e:
                    print(f"ERRORE alla riga {righe_lette + 1}: {e} -> Dati: {row}")
                    continue
                descrizione = row.get('descrizione', '')
                cur.execute(
                    "INSERT INTO entrate (data, tipo_entrata, descrizione, importo, ricevuto_da) VALUES (?, ?, ?, ?, ?)",
                    (data_str, tipo_entrata, descrizione, importo, ricevuto_da)
                )
                righe_inserite += 1
        con.commit()
        print(f"--- Importazione ENTRATE completata ---")
        print(f"Righe lette: {righe_lette}")
        print(f"Righe inserite con successo: {righe_inserite}")
    except FileNotFoundError:
        print(f"ERRORE: File non trovato all'indirizzo '{file_path}'.")
    except Exception as e:
        print(f"ERRORE CRITICO durante l'importazione: {e}")
        con.rollback()
    finally:
        con.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Script per importare dati di spese o entrate da file CSV nel database spese.db.")
    parser.add_argument('--tipo', required=True, choices=['spesa', 'entrata'], help="Il tipo di dati da importare: 'spesa' o 'entrata'.")
    parser.add_argument('--file', required=True, help="Il percorso del file CSV da importare.")
    
    args = parser.parse_args()
    
    if args.tipo == 'spesa':
        import_spese(args.file)
    elif args.tipo == 'entrata':
        import_entrate(args.file)