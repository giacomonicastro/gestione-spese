import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import os
from datetime import datetime, timedelta

app = Flask(__name__)
# IMPORTANTE: Configura una SECRET_KEY univoca e segreta!
app.secret_key = 'SostituisciConUnaChiaveCasualeMoltoLungaDifficile!' 

# Configurazioni Percorsi
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'spese.db')
SCHEMA_FILE = os.path.join(BASE_DIR, 'schema.sql')

# Lista predefinita per le categorie di spesa
CATEGORIE_SPESA = [
    "Alimenti", "Salute", "Viaggi", "Uscite-Amici", "Uscite-Coppia", 
    "Shopping", "Benzina", "Abbonamenti", "Finanziamenti", "Casa", "Regali", "Varie"
]

# Mapping per i nomi dei mesi in italiano
MESI_ITALIANI = {
    1: "Gennaio", 2: "Febbraio", 3: "Marzo", 4: "Aprile", 5: "Maggio", 6: "Giugno",
    7: "Luglio", 8: "Agosto", 9: "Settembre", 10: "Ottobre", 11: "Novembre", 12: "Dicembre"
}

# In app.py
# In app.py

@app.template_filter('format_decimali_italiano')
def format_decimali_italiano(valore, con_euro=True):
    sufixo = " €" if con_euro else ""
    
    # DEBUG: Stampa il valore e il tipo ricevuto dal filtro
    # print(f"DEBUG format_decimali_italiano - Valore ricevuto: '{valore}', Tipo: {type(valore)}")

    if valore is None or str(valore).strip() == "": # Gestisce None e stringhe vuote/spazi
        return "0" + sufixo 
    
    try:
        valore_float = float(valore) 
        if valore_float == int(valore_float):
            return f"{int(valore_float)}{sufixo}"
        else:
            return f"{valore_float:,.2f}".replace('.', '#').replace(',', '.').replace('#', ',') + sufixo
    except (ValueError, TypeError) as e:
        print(f"ERRORE nel filtro format_decimali_italiano: impossibile convertire '{valore}' (tipo: {type(valore)}) in float. Errore: {e}")
        # Se non è un numero, ma vogliamo comunque un output con suffisso (es. per "N/D €")
        # Altrimenti, potresti voler restituire solo str(valore) o un messaggio di errore.
        return str(valore) + sufixo

# --- Funzioni Helper per il Database ---
def get_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    print(f"Tentativo di inizializzare il database usando lo schema: {SCHEMA_FILE}")
    print(f"Il database verrà creato/usato qui: {DATABASE}")
    if not os.path.exists(SCHEMA_FILE):
        print(f"ERRORE CRITICO: Il file '{SCHEMA_FILE}' non è stato trovato.")
        return
    db_conn = None
    try:
        db_conn = get_db()
        with open(SCHEMA_FILE, mode='r') as f:
            db_conn.cursor().executescript(f.read())
        db_conn.commit()
        print("Database inizializzato con successo.")
    except sqlite3.Error as e:
        print(f"Errore SQLite durante init_db: {e}")
    except Exception as e_gen:
        print(f"Errore generico durante init_db: {e_gen}")
    finally:
        if db_conn:
            db_conn.close()

# --- Funzione Helper per calcolare i sommari del mese (per i riquadri) ---
def calcola_sommari_mese(db_conn, anno, mese):
    anno_mese_str = f"{anno:04d}-{mese:02d}"
    s_entrate_giacomo, s_entrate_erica = 0.0, 0.0
    s_spese_giacomo, s_spese_erica = 0.0, 0.0

    cursore_entrate_persona = db_conn.execute('SELECT ricevuto_da, SUM(importo) as totale FROM entrate WHERE strftime("%Y-%m", data) = ? GROUP BY ricevuto_da', (anno_mese_str,))
    for row in cursore_entrate_persona:
        if row['ricevuto_da'] == 'Giacomo': s_entrate_giacomo = row['totale'] or 0.0
        elif row['ricevuto_da'] == 'Erica': s_entrate_erica = row['totale'] or 0.0
    
    cursore_spese_persona = db_conn.execute('SELECT pagato_da, SUM(importo) as totale FROM spese WHERE strftime("%Y-%m", data) = ? GROUP BY pagato_da', (anno_mese_str,))
    for row in cursore_spese_persona:
        if row['pagato_da'] == 'Giacomo': s_spese_giacomo = row['totale'] or 0.0
        elif row['pagato_da'] == 'Erica': s_spese_erica = row['totale'] or 0.0
    
    s_risparmio_giacomo = s_entrate_giacomo - s_spese_giacomo
    s_risparmio_erica = s_entrate_erica - s_spese_erica
    s_totale_entrate_mese = s_entrate_giacomo + s_entrate_erica
    s_totale_spese_mese = s_spese_giacomo + s_spese_erica
    s_risparmio_mese = s_totale_entrate_mese - s_totale_spese_mese
    
    # Per i riquadri sommario, vogliamo SEMPRE il simbolo €, quindi con_euro=True
    return {
        "entrate_giacomo_str": format_decimali_italiano(s_entrate_giacomo, con_euro=True),
        "entrate_erica_str": format_decimali_italiano(s_entrate_erica, con_euro=True),
        "totale_entrate_str": format_decimali_italiano(s_totale_entrate_mese, con_euro=True),
        "spese_giacomo_str": format_decimali_italiano(s_spese_giacomo, con_euro=True),
        "spese_erica_str": format_decimali_italiano(s_spese_erica, con_euro=True),
        "totale_spese_str": format_decimali_italiano(s_totale_spese_mese, con_euro=True),
        "risparmio_giacomo_str": format_decimali_italiano(s_risparmio_giacomo, con_euro=True),
        "risparmio_erica_str": format_decimali_italiano(s_risparmio_erica, con_euro=True),
        "totale_risparmio_str": format_decimali_italiano(s_risparmio_mese, con_euro=True)
    }

# --- Funzioni Helper per ottenere dati per le tabelle aggregate ---
def _get_dati_tabella_entrate(db_conn, anno, mese):
    anno_mese_str = f"{anno:04d}-{mese:02d}"
    raw_entrate = db_conn.execute('''
        SELECT tipo_entrata, ricevuto_da, SUM(importo) as totale_parziale 
        FROM entrate
        WHERE strftime("%Y-%m", data) = ? 
        GROUP BY tipo_entrata, ricevuto_da 
        ORDER BY LOWER(tipo_entrata), ricevuto_da
    ''', (anno_mese_str,)).fetchall()
    
    entrate_pivot = {}
    for row in raw_entrate:
        tipo = row['tipo_entrata']
        ricevente = row['ricevuto_da'] 
        totale = row['totale_parziale'] if row['totale_parziale'] is not None else 0.0
        
        if tipo not in entrate_pivot:
            entrate_pivot[tipo] = {'Giacomo': 0.0, 'Erica': 0.0, 'Totale': 0.0} # Inizializza correttamente
        
        if ricevente == 'Giacomo':
            entrate_pivot[tipo]['Giacomo'] += totale
        elif ricevente == 'Erica':
            entrate_pivot[tipo]['Erica'] += totale
        entrate_pivot[tipo]['Totale'] += totale
    
    display_list = []
    for tipo, data_pivot in entrate_pivot.items():
        display_list.append({
            'tipo_entrata': tipo, 
            'importo_giacomo': data_pivot['Giacomo'], 
            'importo_erica': data_pivot['Erica'], 
            'importo_totale': data_pivot['Totale']
        })
    display_list.sort(key=lambda x: x['tipo_entrata'].lower())
    # DEBUG DENTRO LA FUNZIONE
    print(f"DEBUG _get_dati_tabella_entrate - display_list FINALE: {display_list}") 
    return display_list

def _get_dati_tabella_spese(db_conn, anno, mese):
    anno_mese_str = f"{anno:04d}-{mese:02d}"
    raw_spese = db_conn.execute('''
        SELECT categoria, pagato_da, SUM(importo) as totale_parziale 
        FROM spese
        WHERE strftime("%Y-%m", data) = ? 
        GROUP BY categoria, pagato_da 
        ORDER BY LOWER(categoria), pagato_da
    ''', (anno_mese_str,)).fetchall()

    spese_pivot = {}
    for row in raw_spese:
        cat = row['categoria']
        pagante = row['pagato_da'] 
        totale = row['totale_parziale'] if row['totale_parziale'] is not None else 0.0
        if cat not in spese_pivot: 
            spese_pivot[cat] = {'Giacomo': 0.0, 'Erica': 0.0, 'Totale': 0.0}
        if pagante == 'Giacomo': 
            spese_pivot[cat]['Giacomo'] += totale
        elif pagante == 'Erica': 
            spese_pivot[cat]['Erica'] += totale
        spese_pivot[cat]['Totale'] += totale
    
    display_list = []
    for cat, data_pivot in spese_pivot.items():
        display_list.append({
            'categoria': cat, 
            'importo_giacomo': data_pivot['Giacomo'], 
            'importo_erica': data_pivot['Erica'], 
            'importo_totale_categoria': data_pivot['Totale'] # Chiave diversa qui per il totale riga
        })
    display_list.sort(key=lambda x: x['categoria'].lower())
    print(f"DEBUG _get_dati_tabella_spese - display_list FINALE: {display_list}")
    return display_list

# --- Rotte Principali ---

@app.route('/')
@app.route('/<int:anno>/<int:mese>')
def index(anno=None, mese=None):
    # ... (setup date come prima) ...
    oggi = datetime.today()
    if anno is None: anno = oggi.year
    if mese is None: mese = oggi.month
    try: data_corrente_dt = datetime(anno, mese, 1)
    except ValueError: # ... (gestione errore data) ...
        flash("Data non valida, mostro il mese corrente.", "warning")
        anno, mese = oggi.year, oggi.month
        data_corrente_dt = datetime(anno, mese, 1)
    
    nome_mese_corrente = f"{MESI_ITALIANI.get(data_corrente_dt.month, '')} {data_corrente_dt.year}"
    # ... (calcolo navigazione mesi come prima) ...
    mese_precedente_dt = data_corrente_dt - timedelta(days=1)
    anno_prec, mese_prec = mese_precedente_dt.year, mese_precedente_dt.month
    if data_corrente_dt.month == 12: primo_giorno_mese_successivo_dt = datetime(data_corrente_dt.year + 1, 1, 1)
    else: primo_giorno_mese_successivo_dt = datetime(data_corrente_dt.year, data_corrente_dt.month + 1, 1)
    anno_succ, mese_succ = primo_giorno_mese_successivo_dt.year, primo_giorno_mese_successivo_dt.month

    # Variabili per i totali NUMERICI (per i tfoot delle tabelle nel rendering iniziale)
    val_entrate_giacomo, val_entrate_erica = 0.0, 0.0
    val_spese_giacomo, val_spese_erica = 0.0, 0.0
    
    entrate_per_tabella = [] # Per tbody tabella entrate
    spese_per_tabella = []   # Per tbody tabella spese
    
    db = None
    try:
        db = get_db()
        anno_mese_str = f"{anno:04d}-{mese:02d}"

        # Calcola totali NUMERICI per persona per i tfoot e per i sommari
        cursore_entrate_persona = db.execute('SELECT ricevuto_da, SUM(importo) as totale FROM entrate WHERE strftime("%Y-%m", data) = ? GROUP BY ricevuto_da', (anno_mese_str,))
        for row in cursore_entrate_persona:
            if row['ricevuto_da'] == 'Giacomo': val_entrate_giacomo = row['totale'] or 0.0
            elif row['ricevuto_da'] == 'Erica': val_entrate_erica = row['totale'] or 0.0
        
        cursore_spese_persona = db.execute('SELECT pagato_da, SUM(importo) as totale FROM spese WHERE strftime("%Y-%m", data) = ? GROUP BY pagato_da', (anno_mese_str,))
        for row in cursore_spese_persona:
            if row['pagato_da'] == 'Giacomo': val_spese_giacomo = row['totale'] or 0.0
            elif row['pagato_da'] == 'Erica': val_spese_erica = row['totale'] or 0.0

        # Dati per i tbody delle tabelle (già numeri grezzi)
        entrate_per_tabella = _get_dati_tabella_entrate(db, anno, mese)
        spese_per_tabella = _get_dati_tabella_spese(db, anno, mese)
            
    except sqlite3.Error as e:
        flash(f"Errore nel caricare i dati finanziari del mese: {e}", "danger")
        print(f"Errore SQLite nel caricare dati per {anno_mese_str}: {e}")
    finally:
        if db: db.close()

    # Calcola i totali e risparmi NUMERICI
    val_totale_entrate_mese = val_entrate_giacomo + val_entrate_erica
    val_totale_spese_mese = val_spese_giacomo + val_spese_erica
    val_risparmio_giacomo = val_entrate_giacomo - val_spese_giacomo
    val_risparmio_erica = val_entrate_erica - val_spese_erica
    val_risparmio_mese = val_totale_entrate_mese - val_totale_spese_mese

    return render_template('index.html', 
                           titolo="Bilancio Mensile", nome_mese_corrente=nome_mese_corrente,
                           anno_prec=anno_prec, mese_prec=mese_prec, anno_succ=anno_succ, mese_succ=mese_succ,
                           current_anno=anno, current_mese=mese,
                           
                           # Valori GIA' FORMATTATI CON EURO per i riquadri sommario
                           entrate_giacomo=format_decimali_italiano(val_entrate_giacomo, con_euro=True), 
                           entrate_erica=format_decimali_italiano(val_entrate_erica, con_euro=True),
                           spese_giacomo=format_decimali_italiano(val_spese_giacomo, con_euro=True), 
                           spese_erica=format_decimali_italiano(val_spese_erica, con_euro=True),
                           risparmio_giacomo=format_decimali_italiano(val_risparmio_giacomo, con_euro=True), 
                           risparmio_erica=format_decimali_italiano(val_risparmio_erica, con_euro=True),
                           totale_entrate_mese=format_decimali_italiano(val_totale_entrate_mese, con_euro=True),
                           totale_spese_mese=format_decimali_italiano(val_totale_spese_mese, con_euro=True),
                           risparmio_mese=format_decimali_italiano(val_risparmio_mese, con_euro=True),
                           
                           # Valori NUMERICI GREZZI per i TFOOT delle tabelle (verranno formattati nel template con con_euro=False)
                           val_entrate_giacomo_tf=val_entrate_giacomo,
                           val_entrate_erica_tf=val_entrate_erica,
                           val_totale_entrate_mese_tf=val_totale_entrate_mese,
                           val_spese_giacomo_tf=val_spese_giacomo,
                           val_spese_erica_tf=val_spese_erica,
                           val_totale_spese_mese_tf=val_totale_spese_mese,

                           # Liste per i tbody delle tabelle (contengono numeri grezzi)
                           entrate_mese_dettagliate=entrate_per_tabella, 
                           spese_mese_dettagliate=spese_per_tabella,
                           
                           categorie_spesa_disponibili=CATEGORIE_SPESA,
                           datetime=datetime)

# In app.py, sostituisci SOLO la funzione aggiungi_transazione con questa:
# In app.py

# In app.py

# In app.py, sostituisci SOLO la funzione aggiungi_transazione con questa:

@app.route('/aggiungi_transazione', methods=['POST'])
def aggiungi_transazione():
    if request.method == 'POST':
        tipo_transazione = request.form.get('tipo_transazione')
        data_str = request.form.get('data')
        importo_str = request.form.get('importo')

        if not all([tipo_transazione, data_str, importo_str]):
            return jsonify({'status': 'errore', 'messaggio': 'Tipo transazione, data e importo sono obbligatori!'}), 400
        
        try:
            importo = float(importo_str)
            if importo <= 0:
                return jsonify({'status': 'errore', 'messaggio': "L'importo deve essere un numero positivo."}), 400
            data_transazione_dt = datetime.strptime(data_str, '%Y-%m-%d')
        except ValueError:
            return jsonify({'status': 'errore', 'messaggio': "L'importo o la data inseriti non sono validi."}), 400

        db = None
        messaggio_successo_specifico = ""
        try:
            db = get_db()
            # ... (Logica di INSERT per spesa o entrata e db.commit() come prima) ...
            if tipo_transazione == 'spesa':
                categoria = request.form.get('categoria_spesa_select')
                descrizione = request.form.get('descrizione_spesa')
                pagato_da = request.form.get('pagato_da')
                if not all([categoria, pagato_da]):
                    return jsonify({'status': 'errore', 'messaggio': "Categoria e 'pagato da' sono obbligatori per una spesa!"}), 400
                db.execute('INSERT INTO spese (data, descrizione, categoria, importo, pagato_da) VALUES (?, ?, ?, ?, ?)',
                           (data_str, descrizione if descrizione else "", categoria, importo, pagato_da))
                messaggio_successo_specifico = f"Spesa '{categoria}{' - ' + descrizione if descrizione else ''}' aggiunta!"
            elif tipo_transazione == 'entrata':
                tipo_entrata_val = request.form.get('tipo_entrata_val')
                descrizione_entrata = request.form.get('descrizione_entrata')
                ricevuto_da = request.form.get('ricevuto_da')
                if not all([tipo_entrata_val, ricevuto_da]):
                     return jsonify({'status': 'errore', 'messaggio': "Tipo entrata e 'ricevuto da' sono obbligatori!"}), 400
                db.execute('INSERT INTO entrate (data, tipo_entrata, descrizione, importo, ricevuto_da) VALUES (?, ?, ?, ?, ?)',
                           (data_str, tipo_entrata_val, descrizione_entrata if descrizione_entrata else "", importo, ricevuto_da))
                messaggio_successo_specifico = f"Entrata '{tipo_entrata_val}{' - ' + descrizione_entrata if descrizione_entrata else ''}' aggiunta!"
            else:
                return jsonify({'status': 'errore', 'messaggio': 'Tipo di transazione non valido.'}), 400
            db.commit()
            
            current_anno = data_transazione_dt.year
            current_mese = data_transazione_dt.month

            # 1. Dati per i riquadri sommario (stringhe CON €)
            sommari_per_riquadri_json = calcola_sommari_mese(db, current_anno, current_mese)
            
            # 2. Dati NUMERICI GREZZI per i tfoot dei parziali e per il rendering iniziale di index.html
            val_entrate_giacomo_tf, val_entrate_erica_tf = 0.0, 0.0
            val_spese_giacomo_tf, val_spese_erica_tf = 0.0, 0.0
            
            cursore_entrate_p = db.execute('SELECT ricevuto_da, SUM(importo) as totale FROM entrate WHERE strftime("%Y-%m", data) = ? GROUP BY ricevuto_da', (f"{current_anno:04d}-{current_mese:02d}",))
            for row in cursore_entrate_p:
                if row['ricevuto_da'] == 'Giacomo': val_entrate_giacomo_tf = row['totale'] or 0.0
                elif row['ricevuto_da'] == 'Erica': val_entrate_erica_tf = row['totale'] or 0.0
            val_totale_entrate_mese_tf = val_entrate_giacomo_tf + val_entrate_erica_tf
            
            cursore_spese_p = db.execute('SELECT pagato_da, SUM(importo) as totale FROM spese WHERE strftime("%Y-%m", data) = ? GROUP BY pagato_da', (f"{current_anno:04d}-{current_mese:02d}",))
            for row in cursore_spese_p:
                if row['pagato_da'] == 'Giacomo': val_spese_giacomo_tf = row['totale'] or 0.0
                elif row['pagato_da'] == 'Erica': val_spese_erica_tf = row['totale'] or 0.0
            val_totale_spese_mese_tf = val_spese_giacomo_tf + val_spese_erica_tf

            # 3. Dati per i tbody delle tabelle (liste di dict con numeri grezzi)
            entrate_per_tbody_aggiornate = _get_dati_tabella_entrate(db, current_anno, current_mese)
            spese_per_tbody_aggiornate = _get_dati_tabella_spese(db, current_anno, current_mese)

            # Renderizza i parziali HTML per le tabelle
            html_tbody_entrate = render_template('_righe_tbody_entrate.html',
                                                 entrate_mese_dettagliate=entrate_per_tbody_aggiornate,
                                                 current_anno=current_anno, current_mese=current_mese)
            html_tfoot_entrate = render_template('_righe_tfoot_entrate.html',
                                                 entrate_giacomo_tf=val_entrate_giacomo_tf,
                                                 entrate_erica_tf=val_entrate_erica_tf,
                                                 totale_entrate_mese_tf=val_totale_entrate_mese_tf)
            
            html_tbody_spese = render_template('_righe_tbody_spese.html',
                                               spese_mese_dettagliate=spese_per_tbody_aggiornate,
                                               current_anno=current_anno, current_mese=current_mese)
            html_tfoot_spese = render_template('_righe_tfoot_spese.html',
                                               spese_giacomo_tf=val_spese_giacomo_tf,
                                               spese_erica_tf=val_spese_erica_tf,
                                               totale_spese_mese_tf=val_totale_spese_mese_tf)
            
            return jsonify({
                'status': 'successo', 
                'messaggio': messaggio_successo_specifico,
                'sommario_aggiornato': sommari_per_riquadri_json, # Per i riquadri (stringhe con €)
                'html_tbody_entrate': html_tbody_entrate,
                'html_tfoot_entrate': html_tfoot_entrate,
                'html_tbody_spese': html_tbody_spese,
                'html_tfoot_spese': html_tfoot_spese
            })

        except sqlite3.Error as e:
            print(f"Errore SQLite in aggiungi_transazione: {e}")
            return jsonify({'status': 'errore', 'messaggio': f"Errore database: {e}"}), 500
        except Exception as e_gen:
            print(f"Errore generico in aggiungi_transazione: {e_gen}")
            return jsonify({'status': 'errore', 'messaggio': f"Errore generico: {e_gen}"}), 500
        finally:
            if db: db.close()
    return jsonify({'status': 'errore', 'messaggio': 'Richiesta non valida, atteso POST.'}), 405

# --- Il resto di app.py (index, calcola_sommari_mese, _get_dati_tabella_*, dettagli_*, modifica_*, etc.)
# --- rimane come nell'ultima versione completa che ti ho fornito. ---
# --- Non lo ripeto qui per brevità. ---

# Assicurati che anche tutte le altre rotte e funzioni helper siano quelle dell'ultima versione completa.
# --- ASSICURATI CHE TUTTE LE ALTRE ROTTE E FUNZIONI HELPER ---
# --- (index, calcola_sommari_mese, _get_dati_tabella_entrate, _get_dati_tabella_spese, 
#      dettagli_*, modifica_*, processa_*, elimina_*)
# --- SIANO PRESENTI E SIANO QUELLE DELL'ULTIMA VERSIONE COMPLETA CHE TI HO FORNITO ---

# --- Rotte per Dettagli, Modifica, Elimina SPESE ---
@app.route('/dettagli_spese/<int:anno>/<int:mese>/<path:nome_categoria>')
def dettagli_categoria_mese(anno, mese, nome_categoria):
    transazioni_dettaglio = []
    nome_mese_format = f"{MESI_ITALIANI.get(mese, '')} {anno}"
    totale_categoria = 0.0
    db = None
    try:
        db = get_db()
        anno_mese_str = f"{anno:04d}-{mese:02d}"
        cursore = db.execute('SELECT id, data, descrizione, importo, pagato_da FROM spese WHERE strftime("%Y-%m", data) = ? AND categoria = ? ORDER BY data DESC, id DESC', (anno_mese_str, nome_categoria))
        transazioni_dettaglio = cursore.fetchall()
        for transazione in transazioni_dettaglio:
            totale_categoria += transazione['importo']
    except sqlite3.Error as e:
        flash(f"Errore nel caricare i dettagli per '{nome_categoria}': {e}", "danger")
        return redirect(url_for('index', anno=anno, mese=mese))
    finally:
        if db: db.close()
    return render_template('dettagli_categoria_mese.html',
                           titolo_pagina=f"Dettaglio Spese: {nome_categoria}",
                           nome_categoria=nome_categoria,
                           nome_mese=nome_mese_format,
                           transazioni=transazioni_dettaglio,
                           totale_categoria_mese=totale_categoria,
                           current_anno=anno, current_mese=mese, datetime=datetime)

@app.route('/modifica_spesa/<int:spesa_id>', methods=['GET'])
def modifica_spesa_form(spesa_id):
    spesa = None; db = None
    try:
        db = get_db()
        spesa = db.execute('SELECT id, data, descrizione, categoria, importo, pagato_da FROM spese WHERE id = ?', (spesa_id,)).fetchone()
    except sqlite3.Error as e:
        flash("Errore nel caricare la spesa da modificare.", "danger")
        return redirect(url_for('index'))
    finally:
        if db: db.close()
    if spesa is None:
        flash(f"Spesa con ID {spesa_id} non trovata.", "danger")
        return redirect(url_for('index'))
    return render_template('modifica_spesa.html', spesa=spesa, titolo_pagina="Modifica Spesa", categorie_spesa_disponibili=CATEGORIE_SPESA, datetime=datetime)

@app.route('/modifica_spesa/<int:spesa_id>/salva', methods=['POST'])
def processa_modifica_spesa(spesa_id):
    # ... (Logica per determinare anno_redirect, mese_redirect come prima) ...
    anno_redirect, mese_redirect = datetime.today().year, datetime.today().month
    db_temp = None
    try: 
        db_temp = get_db()
        data_record_orig = db_temp.execute('SELECT data FROM spese WHERE id = ?', (spesa_id,)).fetchone()
        if data_record_orig:
            dt_orig = datetime.strptime(data_record_orig['data'], '%Y-%m-%d')
            anno_redirect, mese_redirect = dt_orig.year, dt_orig.month
    finally:
        if db_temp: db_temp.close()

    if request.method == 'POST':
        # ... (Validazione e logica di update come prima, usando categoria_spesa_select) ...
        data_nuova = request.form.get('data')
        categoria = request.form.get('categoria_spesa_select') 
        descrizione = request.form.get('descrizione_spesa')
        importo_str = request.form.get('importo')
        pagato_da = request.form.get('pagato_da')
        if not all([data_nuova, categoria, importo_str, pagato_da]): 
            flash("Errore: Data, Categoria, Importo e Pagato Da sono obbligatori!", "danger")
            return redirect(url_for('modifica_spesa_form', spesa_id=spesa_id))
        try:
            importo = float(importo_str)
            if importo <=0: raise ValueError("Importo non positivo")
            dt_nuova = datetime.strptime(data_nuova, '%Y-%m-%d')
            anno_redirect, mese_redirect = dt_nuova.year, dt_nuova.month # Aggiorna per il redirect
        except ValueError:
            flash("Errore: importo o data non validi.", "danger")
            return redirect(url_for('modifica_spesa_form', spesa_id=spesa_id))
        db = None
        try:
            db = get_db()
            db.execute('UPDATE spese SET data = ?, descrizione = ?, categoria = ?, importo = ?, pagato_da = ? WHERE id = ?',
                       (data_nuova, descrizione if descrizione else "", categoria, importo, pagato_da, spesa_id))
            db.commit()
            flash(f"Spesa '{categoria}{' - ' + descrizione if descrizione else ''}' aggiornata!", "success")
        except sqlite3.Error as e: flash(f"Errore aggiornamento spesa: {e}", "danger")
        finally:
            if db: db.close()
        return redirect(url_for('index', anno=anno_redirect, mese=mese_redirect))
    return redirect(url_for('index', anno=anno_redirect, mese=mese_redirect))

@app.route('/elimina_spesa/<int:spesa_id>', methods=['POST'])
def elimina_spesa(spesa_id):
    # ... (Logica per determinare anno_redirect, mese_redirect come prima) ...
    anno_redirect, mese_redirect = datetime.today().year, datetime.today().month
    db = None
    try:
        db = get_db()
        spesa_info = db.execute('SELECT data, descrizione, categoria FROM spese WHERE id = ?', (spesa_id,)).fetchone()
        if spesa_info:
            dt_spesa = datetime.strptime(spesa_info['data'], '%Y-%m-%d')
            anno_redirect, mese_redirect = dt_spesa.year, dt_spesa.month
            desc_spesa_eliminata = f"{spesa_info['categoria']}{' - ' + spesa_info['descrizione'] if spesa_info['descrizione'] else ''}"
        else: 
            flash(f"Spesa ID {spesa_id} non trovata.", "warning"); return redirect(url_for('index'))
        db.execute('DELETE FROM spese WHERE id = ?', (spesa_id,))
        db.commit()
        flash(f"Spesa '{desc_spesa_eliminata}' eliminata!", "success")
    except sqlite3.Error as e: flash(f"Errore eliminazione spesa: {e}", "danger")
    finally:
        if db: db.close()
    return redirect(url_for('index', anno=anno_redirect, mese=mese_redirect))

# --- Rotte CRUD ENTRATE (invariate) ---
@app.route('/dettagli_entrate/<int:anno>/<int:mese>/<path:nome_tipo_entrata>')
def dettagli_tipo_entrata_mese(anno, mese, nome_tipo_entrata):
    transazioni_dettaglio = []
    nome_mese_format = f"{MESI_ITALIANI.get(mese, '')} {anno}"
    totale_tipo_entrata = 0.0
    db = None
    try:
        db = get_db()
        anno_mese_str = f"{anno:04d}-{mese:02d}"
        cursore = db.execute('SELECT id, data, tipo_entrata, descrizione, importo, ricevuto_da FROM entrate WHERE strftime("%Y-%m", data) = ? AND tipo_entrata = ? ORDER BY data DESC, id DESC', (anno_mese_str, nome_tipo_entrata))
        transazioni_dettaglio = cursore.fetchall()
        for transazione in transazioni_dettaglio:
            totale_tipo_entrata += transazione['importo']
    except sqlite3.Error as e:
        flash(f"Errore nel caricare i dettagli per il tipo entrata '{nome_tipo_entrata}': {e}", "danger")
        return redirect(url_for('index', anno=anno, mese=mese))
    finally:
        if db: db.close()
    return render_template('dettagli_tipo_entrata_mese.html',
                           titolo_pagina=f"Dettaglio Entrate: {nome_tipo_entrata}",
                           nome_tipo_entrata=nome_tipo_entrata,
                           nome_mese=nome_mese_format,
                           transazioni=transazioni_dettaglio,
                           totale_tipo_entrata_mese=totale_tipo_entrata,
                           current_anno=anno, current_mese=mese, datetime=datetime)

@app.route('/modifica_entrata/<int:entrata_id>', methods=['GET'])
def modifica_entrata_form(entrata_id):
    entrata = None; db = None
    try:
        db = get_db()
        entrata = db.execute('SELECT id, data, tipo_entrata, descrizione, importo, ricevuto_da FROM entrate WHERE id = ?', (entrata_id,)).fetchone()
    except sqlite3.Error as e:
        flash("Errore nel caricare l'entrata da modificare.", "danger")
        return redirect(url_for('index'))
    finally:
        if db: db.close()
    if entrata is None:
        flash(f"Entrata con ID {entrata_id} non trovata.", "danger")
        return redirect(url_for('index'))
    tipi_entrata_disponibili = ["Stipendio", "Bonus", "Regalo", "Vendita", "Extra", "Altro"] # Definisci o passa da una costante
    return render_template('modifica_entrata.html', entrata=entrata, tipi_entrata=tipi_entrata_disponibili, titolo_pagina="Modifica Entrata", datetime=datetime)

@app.route('/modifica_entrata/<int:entrata_id>/salva', methods=['POST'])
def processa_modifica_entrata(entrata_id):
    # ... (Logica per determinare anno_redirect, mese_redirect come prima) ...
    anno_redirect, mese_redirect = datetime.today().year, datetime.today().month
    db_temp = None
    try: 
        db_temp = get_db()
        data_record_orig = db_temp.execute('SELECT data FROM entrate WHERE id = ?', (entrata_id,)).fetchone()
        if data_record_orig:
            dt_orig = datetime.strptime(data_record_orig['data'], '%Y-%m-%d')
            anno_redirect, mese_redirect = dt_orig.year, dt_orig.month
    finally:
        if db_temp: db_temp.close()
    
    if request.method == 'POST':
        # ... (Validazione e logica di update come prima) ...
        data_nuova = request.form.get('data')
        tipo_entrata = request.form.get('tipo_entrata_val')
        descrizione = request.form.get('descrizione_entrata')
        importo_str = request.form.get('importo')
        ricevuto_da = request.form.get('ricevuto_da')
        if not all([data_nuova, tipo_entrata, importo_str, ricevuto_da]):
            flash("Errore: Data, Tipo, Importo e Ricevuto Da sono obbligatori!", "danger")
            return redirect(url_for('modifica_entrata_form', entrata_id=entrata_id))
        try:
            importo = float(importo_str)
            if importo <= 0: raise ValueError("Importo non positivo")
            dt_nuova = datetime.strptime(data_nuova, '%Y-%m-%d')
            anno_redirect, mese_redirect = dt_nuova.year, dt_nuova.month # Aggiorna per il redirect
        except ValueError:
            flash("Errore: Importo o Data non validi.", "danger")
            return redirect(url_for('modifica_entrata_form', entrata_id=entrata_id))
        db = None
        try:
            db = get_db()
            db.execute('UPDATE entrate SET data = ?, tipo_entrata = ?, descrizione = ?, importo = ?, ricevuto_da = ? WHERE id = ?',
                       (data_nuova, tipo_entrata, descrizione if descrizione else "", importo, ricevuto_da, entrata_id))
            db.commit()
            flash(f"Entrata '{tipo_entrata}{' - ' + descrizione if descrizione else ''}' aggiornata!", "success")
        except sqlite3.Error as e: flash(f"Errore aggiornamento entrata: {e}", "danger")
        finally:
            if db: db.close()
        return redirect(url_for('index', anno=anno_redirect, mese=mese_redirect))
    return redirect(url_for('index', anno=anno_redirect, mese=mese_redirect))

@app.route('/elimina_entrata/<int:entrata_id>', methods=['POST'])
def elimina_entrata(entrata_id):
    # ... (Logica per determinare anno_redirect, mese_redirect come prima) ...
    anno_redirect, mese_redirect = datetime.today().year, datetime.today().month
    db = None
    try:
        db = get_db()
        entrata_info = db.execute('SELECT data, tipo_entrata, descrizione FROM entrate WHERE id = ?', (entrata_id,)).fetchone()
        if entrata_info:
            dt_entrata = datetime.strptime(entrata_info['data'], '%Y-%m-%d')
            anno_redirect, mese_redirect = dt_entrata.year, dt_entrata.month
            desc_entrata_eliminata = f"{entrata_info['tipo_entrata']}{' - ' + entrata_info['descrizione'] if entrata_info['descrizione'] else ''}"
        else:
            flash(f"Entrata ID {entrata_id} non trovata.", "warning"); return redirect(url_for('index'))
        db.execute('DELETE FROM entrate WHERE id = ?', (entrata_id,))
        db.commit()
        flash(f"Entrata '{desc_entrata_eliminata}' eliminata!", "success")
    except sqlite3.Error as e: flash(f"Errore eliminazione entrata: {e}", "danger")
    finally:
        if db: db.close()
    return redirect(url_for('index', anno=anno_redirect, mese=mese_redirect))


# --- Blocco Main ---
if __name__ == '__main__':
    print("Avvio applicazione...")
    #init_db() # Decommenta solo per il setup iniziale del DB!
    app.run(debug=True)