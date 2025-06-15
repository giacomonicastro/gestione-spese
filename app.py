import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import os
from datetime import datetime, timedelta
from dateutil.rrule import rrule, MONTHLY # Assicurati che python-dateutil sia installato

app = Flask(__name__)
app.secret_key = 'LaTuaChiaveSegretaSuperSicura_CambialaAppenaPuoi_Definitiva!'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'spese.db')
SCHEMA_FILE = os.path.join(BASE_DIR, 'schema.sql')

CATEGORIE_SPESA = [
    "Alimenti", "Salute", "Viaggi", "Uscite-Amici", "Uscite-Coppia",
    "Shopping", "Benzina", "Abbonamenti", "Finanziamenti", "Casa", "Regali", "Varie"
]
MESI_ITALIANI = {
    1: "Gennaio", 2: "Febbraio", 3: "Marzo", 4: "Aprile", 5: "Maggio", 6: "Giugno",
    7: "Luglio", 8: "Agosto", 9: "Settembre", 10: "Ottobre", 11: "Novembre", 12: "Dicembre"
}
# _# MODIFICA_: Aggiunto il nuovo tipo di report
TIPI_REPORT_STATISTICHE = {
    "risparmi": "Risparmi Mensili e Andamento",
    "spese_categoria": "Dettaglio Spese per Categoria",
    "entrate_tipo": "Dettaglio Entrate per Tipo",
    "rapporto_entrate_spese": "Rapporto Entrate/Spese",
    "top_spender": "Report Top Spender"
}

@app.template_filter('format_decimali_italiano')
def format_decimali_italiano(valore, con_euro=True):
    sufixo = " €" if con_euro else ""
    if valore is None or str(valore).strip() == "": return "0" + sufixo
    try:
        valore_float = float(valore)
        # Formatta con 2 decimali se ci sono decimali, altrimenti come intero
        if valore_float == int(valore_float):
            # Per interi, usa i punti come separatori delle migliaia (formato italiano)
            return f"{int(valore_float):,}".replace(',', '.') + sufixo
        else:
            # Per i float, assicurati che il separatore decimale sia la virgola e migliaia il punto
            return f"{valore_float:,.2f}".replace('.', '#').replace(',', '.').replace('#', ',') + sufixo
    except (ValueError, TypeError): return str(valore) + sufixo

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
        if db_conn: db_conn.close()

def calcola_sommari_mese_numerici(db_conn, anno, mese):
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
    return {
        "entrate_giacomo": s_entrate_giacomo, "entrate_erica": s_entrate_erica,
        "totale_entrate_mese": s_entrate_giacomo + s_entrate_erica,
        "spese_giacomo": s_spese_giacomo, "spese_erica": s_spese_erica,
        "totale_spese_mese": s_spese_giacomo + s_spese_erica,
        "risparmio_giacomo": s_entrate_giacomo - s_spese_giacomo,
        "risparmio_erica": s_entrate_erica - s_spese_erica,
        "totale_risparmio_mese": (s_entrate_giacomo + s_entrate_erica) - (s_spese_giacomo + s_spese_erica)
    }

def _get_dati_tabella_entrate(db_conn, anno, mese):
    anno_mese_str = f"{anno:04d}-{mese:02d}"
    raw_entrate = db_conn.execute('SELECT tipo_entrata, ricevuto_da, SUM(importo) as totale_parziale FROM entrate WHERE strftime("%Y-%m", data) = ? GROUP BY tipo_entrata, ricevuto_da ORDER BY LOWER(tipo_entrata), ricevuto_da', (anno_mese_str,)).fetchall()
    entrate_pivot = {}
    for row in raw_entrate:
        tipo, ricevente, totale = row['tipo_entrata'], row['ricevuto_da'], row['totale_parziale'] or 0.0
        if tipo not in entrate_pivot: entrate_pivot[tipo] = {'Giacomo': 0.0, 'Erica': 0.0, 'Totale': 0.0}
        if ricevente == 'Giacomo': entrate_pivot[tipo]['Giacomo'] += totale
        elif ricevente == 'Erica': entrate_pivot[tipo]['Erica'] += totale
        entrate_pivot[tipo]['Totale'] += totale
    display_list = [{'tipo_entrata': tipo, 'importo_giacomo': v['Giacomo'], 'importo_erica': v['Erica'], 'importo_totale': v['Totale']} for tipo, v in entrate_pivot.items()]
    display_list.sort(key=lambda x: x['tipo_entrata'].lower())
    return display_list

def _get_dati_tabella_spese(db_conn, anno, mese):
    anno_mese_str = f"{anno:04d}-{mese:02d}"
    raw_spese = db_conn.execute('SELECT categoria, pagato_da, SUM(importo) as totale_parziale FROM spese WHERE strftime("%Y-%m", data) = ? GROUP BY categoria, pagato_da ORDER BY LOWER(categoria), pagato_da', (anno_mese_str,)).fetchall()
    spese_pivot = {}
    for row in raw_spese:
        cat, pagante, totale = row['categoria'], row['pagato_da'], row['totale_parziale'] or 0.0
        if cat not in spese_pivot: spese_pivot[cat] = {'Giacomo': 0.0, 'Erica': 0.0, 'Totale': 0.0}
        if pagante == 'Giacomo': spese_pivot[cat]['Giacomo'] += totale
        elif pagante == 'Erica': spese_pivot[cat]['Erica'] += totale
        spese_pivot[cat]['Totale'] += totale
    display_list = [{'categoria': cat, 'importo_giacomo': v['Giacomo'], 'importo_erica': v['Erica'], 'importo_totale_categoria': v['Totale']} for cat, v in spese_pivot.items()]
    display_list.sort(key=lambda x: x['categoria'].lower())
    return display_list

@app.route('/')
@app.route('/<int:anno>/<int:mese>')
def index(anno=None, mese=None):
    oggi = datetime.today()
    if anno is None: anno = oggi.year
    if mese is None: mese = oggi.month
    try: data_corrente_dt = datetime(anno, mese, 1)
    except ValueError: flash("Data non valida, mostro il mese corrente.", "warning"); anno, mese = oggi.year, oggi.month; data_corrente_dt = datetime(anno, mese, 1)

    nome_mese_corrente = f"{MESI_ITALIANI.get(data_corrente_dt.month, '')} {data_corrente_dt.year}"
    mese_precedente_dt = data_corrente_dt - timedelta(days=1)
    anno_prec, mese_prec = mese_precedente_dt.year, mese_precedente_dt.month
    if data_corrente_dt.month == 12: primo_giorno_mese_successivo_dt = datetime(data_corrente_dt.year + 1, 1, 1)
    else: primo_giorno_mese_successivo_dt = datetime(data_corrente_dt.year, data_corrente_dt.month + 1, 1)
    anno_succ, mese_succ = primo_giorno_mese_successivo_dt.year, primo_giorno_mese_successivo_dt.month

    sommari_numerici_mese = {}
    entrate_per_tabella = []
    spese_per_tabella = []
    # Le variabili 'ultime_spese' sono state rimosse perché non più necessarie
    db = None
    try:
        db = get_db()
        sommari_numerici_mese = calcola_sommari_mese_numerici(db, anno, mese)
        entrate_per_tabella = _get_dati_tabella_entrate(db, anno, mese)
        spese_per_tabella = _get_dati_tabella_spese(db, anno, mese)
        # Le query per le ultime spese sono state rimosse
    except Exception as e:
        print(f"Errore nel caricamento dati per index: {e}"); flash("Errore caricamento dati.", "danger")
    finally:
        if db: db.close()

    return render_template('index.html',
                           titolo="Bilancio Mensile", nome_mese_corrente=nome_mese_corrente,
                           anno_prec=anno_prec, mese_prec=mese_prec, anno_succ=anno_succ, mese_succ=mese_succ,
                           current_anno=anno, current_mese=mese,
                           entrate_giacomo=format_decimali_italiano(sommari_numerici_mese.get('entrate_giacomo', 0.0)),
                           entrate_erica=format_decimali_italiano(sommari_numerici_mese.get('entrate_erica', 0.0)),
                           spese_giacomo=format_decimali_italiano(sommari_numerici_mese.get('spese_giacomo', 0.0)),
                           spese_erica=format_decimali_italiano(sommari_numerici_mese.get('spese_erica', 0.0)),
                           risparmio_giacomo=format_decimali_italiano(sommari_numerici_mese.get('risparmio_giacomo', 0.0)),
                           risparmio_erica=format_decimali_italiano(sommari_numerici_mese.get('risparmio_erica', 0.0)),
                           totale_entrate_mese=format_decimali_italiano(sommari_numerici_mese.get('totale_entrate_mese', 0.0)),
                           totale_spese_mese=format_decimali_italiano(sommari_numerici_mese.get('totale_spese_mese', 0.0)),
                           risparmio_mese=format_decimali_italiano(sommari_numerici_mese.get('totale_risparmio_mese', 0.0)),
                           val_entrate_giacomo_tf=sommari_numerici_mese.get('entrate_giacomo', 0.0),
                           val_entrate_erica_tf=sommari_numerici_mese.get('entrate_erica', 0.0),
                           val_totale_entrate_mese_tf=sommari_numerici_mese.get('totale_entrate_mese', 0.0),
                           val_spese_giacomo_tf=sommari_numerici_mese.get('spese_giacomo', 0.0),
                           val_spese_erica_tf=sommari_numerici_mese.get('spese_erica', 0.0),
                           val_totale_spese_mese_tf=sommari_numerici_mese.get('totale_spese_mese', 0.0),
                           entrate_mese_dettagliate=entrate_per_tabella,
                           spese_mese_dettagliate=spese_per_tabella,
                           categorie_spesa_disponibili=CATEGORIE_SPESA, datetime=datetime)

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
        html_tbody_entrate, html_tfoot_entrate = "", ""
        html_tbody_spese, html_tfoot_spese = "", ""

        try:
            db = get_db()

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

            sommari_numerici_agg = calcola_sommari_mese_numerici(db, current_anno, current_mese)

            sommari_per_riquadri_json = {
                "entrate_giacomo_str": format_decimali_italiano(sommari_numerici_agg.get('entrate_giacomo', 0.0), con_euro=True),
                "entrate_erica_str": format_decimali_italiano(sommari_numerici_agg.get('entrate_erica', 0.0), con_euro=True),
                "totale_entrate_str": format_decimali_italiano(sommari_numerici_agg.get('totale_entrate_mese', 0.0), con_euro=True),
                "spese_giacomo_str": format_decimali_italiano(sommari_numerici_agg.get('spese_giacomo', 0.0), con_euro=True),
                "spese_erica_str": format_decimali_italiano(sommari_numerici_agg.get('spese_erica', 0.0), con_euro=True),
                "totale_spese_str": format_decimali_italiano(sommari_numerici_agg.get('totale_spese_mese', 0.0), con_euro=True),
                "risparmio_giacomo_str": format_decimali_italiano(sommari_numerici_agg.get('risparmio_giacomo', 0.0), con_euro=True),
                "risparmio_erica_str": format_decimali_italiano(sommari_numerici_agg.get('risparmio_erica', 0.0), con_euro=True),
                "totale_risparmio_str": format_decimali_italiano(sommari_numerici_agg.get('totale_risparmio_mese', 0.0), con_euro=True)
            }

            entrate_per_tbody_aggiornate = _get_dati_tabella_entrate(db, current_anno, current_mese)
            spese_per_tbody_aggiornate = _get_dati_tabella_spese(db, current_anno, current_mese)

            html_tbody_entrate = render_template('_righe_tbody_entrate.html', entrate_mese_dettagliate=entrate_per_tbody_aggiornate, current_anno=current_anno, current_mese=current_mese)
            html_tfoot_entrate = render_template('_righe_tfoot_entrate.html',
                                                 entrate_giacomo_tf=sommari_numerici_agg.get('entrate_giacomo',0.0),
                                                 entrate_erica_tf=sommari_numerici_agg.get('entrate_erica',0.0),
                                                 totale_entrate_mese_tf=sommari_numerici_agg.get('totale_entrate_mese',0.0))

            html_tbody_spese = render_template('_righe_tbody_spese.html', spese_mese_dettagliate=spese_per_tbody_aggiornate, current_anno=current_anno, current_mese=current_mese)
            html_tfoot_spese = render_template('_righe_tfoot_spese.html',
                                               spese_giacomo_tf=sommari_numerici_agg.get('spese_giacomo',0.0),
                                               spese_erica_tf=sommari_numerici_agg.get('spese_erica',0.0),
                                               totale_spese_mese_tf=sommari_numerici_agg.get('totale_spese_mese',0.0))

            return jsonify({
                'status': 'successo',
                'messaggio': messaggio_successo_specifico,
                'sommario_aggiornato': sommari_per_riquadri_json,
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

    return jsonify({'status': 'errore', 'messaggio': 'Richiesta non POST.'}), 405

@app.route('/statistiche', methods=['GET', 'POST'])
def statistiche():
    oggi = datetime.today()
    anni_disponibili = list(range(oggi.year - 5, oggi.year + 2))

    form_data = request.form if request.method == 'POST' else request.args

    selected_anno_da = form_data.get('anno_da', default=oggi.year, type=int)
    selected_mese_da = form_data.get('mese_da', default=1, type=int)
    selected_anno_a = form_data.get('anno_a', default=oggi.year, type=int)
    selected_mese_a = form_data.get('mese_a', default=oggi.month, type=int)
    selected_report_type = form_data.get('report_type', default='risparmi')

    form_submitted = bool(request.form) or bool(request.args.get('anno_da'))

    nome_mese_da_str = MESI_ITALIANI.get(selected_mese_da, '')
    nome_mese_a_str = MESI_ITALIANI.get(selected_mese_a, '')
    periodo_visualizzato_str = f"Da {nome_mese_da_str} {selected_anno_da} a {nome_mese_a_str} {selected_anno_a}"

    # _# MODIFICA_: Aggiunte nuove chiavi per il report top_spender
    dati_stat = {
        "periodo_visualizzato_str": periodo_visualizzato_str,
        "messaggio_placeholder": "",
        "lista_risparmi_mensili": [], "medie_risparmi": None,
        "chart_labels": [], "chart_data_giacomo": [], "chart_data_erica": [], "chart_data_totale": [],
        "dettaglio_spese_categoria": [], "chart_spese_giacomo": None, "chart_spese_erica": None,
        "dettaglio_entrate_tipo": [], "medie_entrate": None,
        "chart_entrate_labels": [], "chart_entrate_data_giacomo": [],
        "chart_entrate_data_erica": [], "chart_entrate_data_totale": [],
        "forecast_report": None,
        "top_spese_totali": [], "top_spese_giacomo": [], "top_spese_erica": [],
        "totale_entrate_periodo_str": "0 €", "totale_spese_periodo_str": "0 €"
    }

    if form_submitted:
        db = None
        try:
            db = get_db()
            start_date = datetime(selected_anno_da, selected_mese_da, 1)
            if selected_mese_a == 12:
                end_date_exclusive = datetime(selected_anno_a + 1, 1, 1)
            else:
                end_date_exclusive = datetime(selected_anno_a, selected_mese_a + 1, 1)

            if start_date >= end_date_exclusive:
                flash("Il periodo 'Da' deve essere precedente al periodo 'A'.", "warning")
                dati_stat["messaggio_placeholder"] = "Periodo non valido: 'Da' deve precedere 'A'."
            else:
                num_mesi_periodo = 0
                temp_date_for_count = start_date
                while temp_date_for_count < end_date_exclusive:
                    num_mesi_periodo += 1
                    if temp_date_for_count.month == 12:
                        temp_date_for_count = datetime(temp_date_for_count.year + 1, 1, 1)
                    else:
                        temp_date_for_count = datetime(temp_date_for_count.year, temp_date_for_count.month + 1, 1)
                if num_mesi_periodo == 0: num_mesi_periodo = 1

                if selected_report_type == 'risparmi':
                    current_date_iter = start_date
                    while current_date_iter < end_date_exclusive:
                        anno_iter, mese_iter = current_date_iter.year, current_date_iter.month
                        sommari_mese_iter = calcola_sommari_mese_numerici(db, anno_iter, mese_iter)
                        nome_mese_display = f"{MESI_ITALIANI.get(mese_iter, '')} {anno_iter}"
                        dati_stat["lista_risparmi_mensili"].append({'periodo': nome_mese_display,'risparmio_giacomo': sommari_mese_iter.get('risparmio_giacomo', 0.0),'risparmio_erica': sommari_mese_iter.get('risparmio_erica', 0.0),'risparmio_totale': sommari_mese_iter.get('totale_risparmio_mese', 0.0)})
                        dati_stat["chart_labels"].append(nome_mese_display)
                        dati_stat["chart_data_giacomo"].append(sommari_mese_iter.get('risparmio_giacomo', 0.0))
                        dati_stat["chart_data_erica"].append(sommari_mese_iter.get('risparmio_erica', 0.0))
                        dati_stat["chart_data_totale"].append(sommari_mese_iter.get('totale_risparmio_mese', 0.0))
                        if current_date_iter.month == 12: current_date_iter = datetime(current_date_iter.year + 1, 1, 1)
                        else: current_date_iter = datetime(current_date_iter.year, current_date_iter.month + 1, 1)
                    if dati_stat["lista_risparmi_mensili"]:
                        num_items = len(dati_stat["lista_risparmi_mensili"])
                        dati_stat["medie_risparmi"] = {"giacomo": sum(item['risparmio_giacomo'] for item in dati_stat["lista_risparmi_mensili"]) / num_items,"erica": sum(item['risparmio_erica'] for item in dati_stat["lista_risparmi_mensili"]) / num_items,"totale": sum(item['risparmio_totale'] for item in dati_stat["lista_risparmi_mensili"]) / num_items}
                    if not dati_stat["lista_risparmi_mensili"]:
                         dati_stat["messaggio_placeholder"] = "Nessun dato di risparmio trovato per il periodo."

                elif selected_report_type == 'spese_categoria':
                    spese_cat_periodo_raw = {}
                    date_from_sql = start_date.strftime('%Y-%m-%d')
                    date_to_sql = end_date_exclusive.strftime('%Y-%m-%d')
                    query_spese = """SELECT categoria, pagato_da, SUM(importo) as totale_cat_persona FROM spese WHERE data >= ? AND data < ? GROUP BY categoria, pagato_da ORDER BY LOWER(categoria), pagato_da"""
                    cursor_spese = db.execute(query_spese, (date_from_sql, date_to_sql))
                    for row in cursor_spese.fetchall():
                        cat, pagante, totale = row['categoria'], row['pagato_da'], row['totale_cat_persona'] or 0.0
                        if cat not in spese_cat_periodo_raw: spese_cat_periodo_raw[cat] = {'Giacomo': 0.0, 'Erica': 0.0, 'Totale': 0.0}
                        if pagante in spese_cat_periodo_raw[cat]: spese_cat_periodo_raw[cat][pagante] += totale
                        spese_cat_periodo_raw[cat]['Totale'] += totale
                    chart_g_labels, chart_g_data = [], []
                    chart_e_labels, chart_e_data = [], []
                    for cat_key in sorted(spese_cat_periodo_raw.keys(), key=lambda x: x.lower()):
                        data_cat = spese_cat_periodo_raw[cat_key]
                        media_mensile = (data_cat['Totale'] / num_mesi_periodo) if num_mesi_periodo > 0 else 0.0
                        dati_stat['dettaglio_spese_categoria'].append({'categoria': cat_key,'spesa_giacomo': data_cat['Giacomo'],'spesa_erica': data_cat['Erica'],'spesa_totale': data_cat['Totale'],'media_mensile': media_mensile})
                        if data_cat['Giacomo'] > 0: chart_g_labels.append(cat_key); chart_g_data.append(data_cat['Giacomo'])
                        if data_cat['Erica'] > 0: chart_e_labels.append(cat_key); chart_e_data.append(data_cat['Erica'])
                    dati_stat['chart_spese_giacomo'] = {'labels': chart_g_labels, 'data': chart_g_data}
                    dati_stat['chart_spese_erica'] = {'labels': chart_e_labels, 'data': chart_e_data}
                    if not dati_stat['dettaglio_spese_categoria']:
                        dati_stat["messaggio_placeholder"] = "Nessuna spesa trovata per il periodo selezionato."

                elif selected_report_type == 'entrate_tipo':
                    entrate_tipo_periodo_raw = {}
                    date_from_sql = start_date.strftime('%Y-%m-%d')
                    date_to_sql = end_date_exclusive.strftime('%Y-%m-%d')
                    query_entrate = """SELECT tipo_entrata, ricevuto_da, SUM(importo) as totale_tipo_persona FROM entrate WHERE data >= ? AND data < ? GROUP BY tipo_entrata, ricevuto_da ORDER BY LOWER(tipo_entrata), ricevuto_da"""
                    cursor_entrate = db.execute(query_entrate, (date_from_sql, date_to_sql))
                    for row in cursor_entrate.fetchall():
                        tipo, ricevente, totale = row['tipo_entrata'], row['ricevuto_da'], row['totale_tipo_persona'] or 0.0
                        if tipo not in entrate_tipo_periodo_raw: entrate_tipo_periodo_raw[tipo] = {'Giacomo': 0.0, 'Erica': 0.0, 'Totale': 0.0}
                        if ricevente in entrate_tipo_periodo_raw[tipo]: entrate_tipo_periodo_raw[tipo][ricevente] += totale
                        entrate_tipo_periodo_raw[tipo]['Totale'] += totale
                    for tipo_key in sorted(entrate_tipo_periodo_raw.keys(), key=lambda x: x.lower()):
                        data_tipo = entrate_tipo_periodo_raw[tipo_key]
                        dati_stat['dettaglio_entrate_tipo'].append({'tipo': tipo_key,'entrata_giacomo': data_tipo['Giacomo'],'entrata_erica': data_tipo['Erica'],'entrata_totale': data_tipo['Totale']})
                    total_sum_entrate_giacomo_periodo, total_sum_entrate_erica_periodo = 0, 0
                    current_date_iter = start_date
                    while current_date_iter < end_date_exclusive:
                        anno_iter, mese_iter = current_date_iter.year, current_date_iter.month
                        sommari_mese = calcola_sommari_mese_numerici(db, anno_iter, mese_iter)
                        entrate_g, entrate_e = sommari_mese.get('entrate_giacomo', 0.0), sommari_mese.get('entrate_erica', 0.0)
                        dati_stat["chart_entrate_labels"].append(f"{MESI_ITALIANI.get(mese_iter, '')[:3]} {anno_iter}")
                        dati_stat["chart_entrate_data_giacomo"].append(entrate_g)
                        dati_stat["chart_entrate_data_erica"].append(entrate_e)
                        dati_stat["chart_entrate_data_totale"].append(entrate_g + entrate_e)
                        total_sum_entrate_giacomo_periodo += entrate_g
                        total_sum_entrate_erica_periodo += entrate_e
                        if current_date_iter.month == 12: current_date_iter = datetime(current_date_iter.year + 1, 1, 1)
                        else: current_date_iter = datetime(current_date_iter.year, current_date_iter.month + 1, 1)
                    avg_g = (total_sum_entrate_giacomo_periodo / num_mesi_periodo) if num_mesi_periodo > 0 else 0.0
                    avg_e = (total_sum_entrate_erica_periodo / num_mesi_periodo) if num_mesi_periodo > 0 else 0.0
                    dati_stat['medie_entrate'] = {'giacomo': avg_g, 'erica': avg_e, 'totale': avg_g + avg_e}
                    if not dati_stat['dettaglio_entrate_tipo'] and not dati_stat["chart_entrate_labels"]:
                         dati_stat["messaggio_placeholder"] = "Nessuna entrata trovata per il periodo selezionato."

                elif selected_report_type == 'rapporto_entrate_spese':
                    date_from_sql = start_date.strftime('%Y-%m-%d')
                    date_to_sql = end_date_exclusive.strftime('%Y-%m-%d')

                    def get_forecast_data(persona_filter=None):
                        params_e = [date_from_sql, date_to_sql]
                        params_s = [date_from_sql, date_to_sql]
                        query_filter_entrate = ""
                        query_filter_spese = ""
                        if persona_filter:
                            query_filter_entrate = f" AND ricevuto_da = ?"
                            query_filter_spese = f" AND pagato_da = ?"
                            params_e.append(persona_filter)
                            params_s.append(persona_filter)

                        totale_entrate = db.execute(f'SELECT SUM(importo) as totale FROM entrate WHERE data >= ? AND data < ?{query_filter_entrate}', params_e).fetchone()['totale'] or 0.0
                        totale_spese = db.execute(f'SELECT SUM(importo) as totale FROM spese WHERE data >= ? AND data < ?{query_filter_spese}', params_s).fetchone()['totale'] or 0.0

                        media_e = totale_entrate / num_mesi_periodo
                        media_s = totale_spese / num_mesi_periodo
                        forecast_e = media_e * 12
                        forecast_s = media_s * 12

                        return {
                            'media_entrate': media_e, 'media_spese': media_s, 'media_risparmio': media_e - media_s,
                            'forecast_entrate': forecast_e, 'forecast_spese': forecast_s, 'forecast_risparmio': forecast_e - forecast_s,
                            'rapporto_percentuale': (forecast_s / forecast_e * 100) if forecast_e > 0 else 0
                        }

                    dati_stat['forecast_report'] = {
                        'periodo_mesi': num_mesi_periodo,
                        'totale': get_forecast_data(),
                        'giacomo': get_forecast_data('Giacomo'),
                        'erica': get_forecast_data('Erica')
                    }

                    if dati_stat['forecast_report']['totale']['media_entrate'] == 0 and dati_stat['forecast_report']['totale']['media_spese'] == 0:
                        dati_stat["messaggio_placeholder"] = "Nessun dato di entrata o spesa trovato per il periodo per generare il report."
                        dati_stat['forecast_report'] = None
                
                # _# MODIFICA_: Logica per il nuovo report "Top Spender"
                elif selected_report_type == 'top_spender':
                    date_from_sql = start_date.strftime('%Y-%m-%d')
                    date_to_sql = end_date_exclusive.strftime('%Y-%m-%d')

                    totale_entrate_periodo = db.execute('SELECT SUM(importo) as totale FROM entrate WHERE data >= ? AND data < ?', (date_from_sql, date_to_sql)).fetchone()['totale'] or 0.0
                    totale_spese_periodo = db.execute('SELECT SUM(importo) as totale FROM spese WHERE data >= ? AND data < ?', (date_from_sql, date_to_sql)).fetchone()['totale'] or 0.0

                    dati_stat['totale_entrate_periodo_str'] = format_decimali_italiano(totale_entrate_periodo)
                    dati_stat['totale_spese_periodo_str'] = format_decimali_italiano(totale_spese_periodo)

                    def processa_lista_spese(lista_spese_raw):
                        lista_elaborata = []
                        for spesa_row in lista_spese_raw:
                            spesa_dict = dict(spesa_row)
                            importo = spesa_dict['importo']
                            spesa_dict['perc_su_entrate'] = (importo / totale_entrate_periodo * 100) if totale_entrate_periodo > 0 else 0
                            spesa_dict['perc_su_spese'] = (importo / totale_spese_periodo * 100) if totale_spese_periodo > 0 else 0
                            lista_elaborata.append(spesa_dict)
                        return lista_elaborata

                    query_base = "SELECT data, categoria, descrizione, importo, pagato_da FROM spese WHERE data >= ? AND data < ? {extra_where} ORDER BY importo DESC LIMIT 10"
                    
                    cursor_totali = db.execute(query_base.format(extra_where=""), (date_from_sql, date_to_sql))
                    dati_stat['top_spese_totali'] = processa_lista_spese(cursor_totali.fetchall())

                    cursor_giacomo = db.execute(query_base.format(extra_where="AND pagato_da = ?"), (date_from_sql, date_to_sql, 'Giacomo'))
                    dati_stat['top_spese_giacomo'] = processa_lista_spese(cursor_giacomo.fetchall())

                    cursor_erica = db.execute(query_base.format(extra_where="AND pagato_da = ?"), (date_from_sql, date_to_sql, 'Erica'))
                    dati_stat['top_spese_erica'] = processa_lista_spese(cursor_erica.fetchall())
                    
                    if not dati_stat['top_spese_totali']:
                        dati_stat["messaggio_placeholder"] = "Nessuna spesa trovata nel periodo selezionato per generare il report 'Top Spender'."


        except Exception as e_stat:
            print(f"ERRORE GRAVE nel calcolo delle statistiche: {e_stat}")
            import traceback
            traceback.print_exc()
            flash(f"Errore imprevisto durante il calcolo delle statistiche. Controlla i log del server.", "danger")
            dati_stat.update({
                "forecast_report": None,
                "messaggio_placeholder": "Si è verificato un errore nel calcolo delle statistiche."
            })
        finally:
            if db: db.close()

    return render_template('statistiche.html',
                           titolo_pagina="Statistiche e Report",
                           anni_disponibili=anni_disponibili,
                           mesi_italiani=MESI_ITALIANI,
                           tipi_report_disponibili=TIPI_REPORT_STATISTICHE,
                           dati_stat=dati_stat,
                           current_selected_anno_da=selected_anno_da,
                           current_selected_mese_da=selected_mese_da,
                           current_selected_anno_a=selected_anno_a,
                           current_selected_mese_a=selected_mese_a,
                           current_selected_report_type=selected_report_type,
                           form_submitted=form_submitted,
                           datetime=datetime)

# --- Rotte CRUD Spese ---
@app.route('/dettagli_spese/<int:anno>/<int:mese>/<path:nome_categoria>')
def dettagli_categoria_mese(anno, mese, nome_categoria):
    transazioni_dettaglio = []; nome_mese_format = f"{MESI_ITALIANI.get(mese, '')} {anno}"; totale_categoria = 0.0; db = None
    try:
        db = get_db()
        anno_mese_str = f"{anno:04d}-{mese:02d}"
        cursore = db.execute('SELECT id, data, descrizione, importo, pagato_da FROM spese WHERE strftime("%Y-%m", data) = ? AND categoria = ? ORDER BY data DESC, id DESC', (anno_mese_str, nome_categoria))
        transazioni_dettaglio = cursore.fetchall()
        for transazione in transazioni_dettaglio: totale_categoria += transazione['importo']
    except sqlite3.Error as e: flash(f"Errore caricamento dettagli per '{nome_categoria}': {e}", "danger"); return redirect(url_for('index', anno=anno, mese=mese))
    finally:
        if db: db.close()
    return render_template('dettagli_categoria_mese.html', titolo_pagina=f"Dettaglio Spese: {nome_categoria}", nome_categoria=nome_categoria, nome_mese=nome_mese_format, transazioni=transazioni_dettaglio, totale_categoria_mese=totale_categoria, current_anno=anno, current_mese=mese, datetime=datetime)

@app.route('/modifica_spesa/<int:spesa_id>', methods=['GET'])
def modifica_spesa_form(spesa_id):
    spesa = None; db = None
    try:
        db = get_db()
        spesa = db.execute('SELECT id, data, descrizione, categoria, importo, pagato_da FROM spese WHERE id = ?', (spesa_id,)).fetchone()
    except sqlite3.Error as e: flash("Errore caricamento spesa.", "danger"); return redirect(url_for('index'))
    finally:
        if db: db.close()
    if spesa is None: flash(f"Spesa ID {spesa_id} non trovata.", "danger"); return redirect(url_for('index'))
    return render_template('modifica_spesa.html', spesa=spesa, titolo_pagina="Modifica Spesa", categorie_spesa_disponibili=CATEGORIE_SPESA, datetime=datetime)

@app.route('/modifica_spesa/<int:spesa_id>/salva', methods=['POST'])
def processa_modifica_spesa(spesa_id):
    anno_redirect, mese_redirect = datetime.today().year, datetime.today().month; db_temp = None
    try:
        db_temp = get_db()
        data_record_orig = db_temp.execute('SELECT data FROM spese WHERE id = ?', (spesa_id,)).fetchone()
        if data_record_orig: dt_orig = datetime.strptime(data_record_orig['data'], '%Y-%m-%d'); anno_redirect, mese_redirect = dt_orig.year, dt_orig.month
    finally:
        if db_temp: db_temp.close()
    if request.method == 'POST':
        data_nuova, categoria, descrizione, importo_str, pagato_da = request.form.get('data'), request.form.get('categoria_spesa_select'), request.form.get('descrizione_spesa'), request.form.get('importo'), request.form.get('pagato_da')
        if not all([data_nuova, categoria, importo_str, pagato_da]): flash("Errore: Campi obbligatori mancanti!", "danger"); return redirect(url_for('modifica_spesa_form', spesa_id=spesa_id))
        try:
            importo = float(importo_str)
            if importo <=0: raise ValueError("Importo non positivo")
            dt_nuova = datetime.strptime(data_nuova, '%Y-%m-%d'); anno_redirect, mese_redirect = dt_nuova.year, dt_nuova.month
        except ValueError: flash("Errore: importo o data non validi.", "danger"); return redirect(url_for('modifica_spesa_form', spesa_id=spesa_id))
        db = None
        try:
            db = get_db()
            db.execute('UPDATE spese SET data = ?, descrizione = ?, categoria = ?, importo = ?, pagato_da = ? WHERE id = ?', (data_nuova, descrizione if descrizione else "", categoria, importo, pagato_da, spesa_id))
            db.commit(); flash(f"Spesa '{categoria}{' - ' + descrizione if descrizione else ''}' aggiornata!", "success")
        except sqlite3.Error as e: flash(f"Errore aggiornamento spesa: {e}", "danger")
        finally:
            if db: db.close()
        return redirect(url_for('index', anno=anno_redirect, mese=mese_redirect))
    return redirect(url_for('index', anno=anno_redirect, mese=mese_redirect))

@app.route('/elimina_spesa/<int:spesa_id>', methods=['POST'])
def elimina_spesa(spesa_id):
    anno_redirect, mese_redirect = datetime.today().year, datetime.today().month; db = None
    try:
        db = get_db()
        spesa_info = db.execute('SELECT data, descrizione, categoria FROM spese WHERE id = ?', (spesa_id,)).fetchone()
        if spesa_info:
            dt_spesa = datetime.strptime(spesa_info['data'], '%Y-%m-%d'); anno_redirect, mese_redirect = dt_spesa.year, dt_spesa.month
            desc_spesa_eliminata = f"{spesa_info['categoria']}{' - ' + spesa_info['descrizione'] if spesa_info['descrizione'] else ''}"
        else: flash(f"Spesa ID {spesa_id} non trovata.", "warning"); return redirect(url_for('index'))
        db.execute('DELETE FROM spese WHERE id = ?', (spesa_id,)); db.commit()
        flash(f"Spesa '{desc_spesa_eliminata}' eliminata!", "success")
    except sqlite3.Error as e: flash(f"Errore eliminazione spesa: {e}", "danger")
    finally:
        if db: db.close()
    return redirect(url_for('index', anno=anno_redirect, mese=mese_redirect))

# --- Rotte CRUD Entrate ---
@app.route('/dettagli_entrate/<int:anno>/<int:mese>/<path:nome_tipo_entrata>')
def dettagli_tipo_entrata_mese(anno, mese, nome_tipo_entrata):
    transazioni_dettaglio = []; nome_mese_format = f"{MESI_ITALIANI.get(mese, '')} {anno}"; totale_tipo_entrata = 0.0; db = None
    try:
        db = get_db()
        anno_mese_str = f"{anno:04d}-{mese:02d}"
        cursore = db.execute('SELECT id, data, tipo_entrata, descrizione, importo, ricevuto_da FROM entrate WHERE strftime("%Y-%m", data) = ? AND tipo_entrata = ? ORDER BY data DESC, id DESC', (anno_mese_str, nome_tipo_entrata))
        transazioni_dettaglio = cursore.fetchall()
        for transazione in transazioni_dettaglio: totale_tipo_entrata += transazione['importo']
    except sqlite3.Error as e: flash(f"Errore caricamento dettagli per '{nome_tipo_entrata}': {e}", "danger"); return redirect(url_for('index', anno=anno, mese=mese))
    finally:
        if db: db.close()
    return render_template('dettagli_tipo_entrata_mese.html', titolo_pagina=f"Dettaglio Entrate: {nome_tipo_entrata}", nome_tipo_entrata=nome_tipo_entrata, nome_mese=nome_mese_format, transazioni=transazioni_dettaglio, totale_tipo_entrata_mese=totale_tipo_entrata, current_anno=anno, current_mese=mese, datetime=datetime)

@app.route('/modifica_entrata/<int:entrata_id>', methods=['GET'])
def modifica_entrata_form(entrata_id):
    entrata = None; db = None
    try:
        db = get_db()
        entrata = db.execute('SELECT id, data, tipo_entrata, descrizione, importo, ricevuto_da FROM entrate WHERE id = ?', (entrata_id,)).fetchone()
    except sqlite3.Error as e: flash("Errore caricamento entrata.", "danger"); return redirect(url_for('index'))
    finally:
        if db: db.close()
    if entrata is None: flash(f"Entrata ID {entrata_id} non trovata.", "danger"); return redirect(url_for('index'))
    tipi_entrata_disponibili = ["Stipendio", "Bonus", "Regalo", "Vendita", "Extra", "Altro"]
    return render_template('modifica_entrata.html', entrata=entrata, tipi_entrata=tipi_entrata_disponibili, titolo_pagina="Modifica Entrata", datetime=datetime)

@app.route('/modifica_entrata/<int:entrata_id>/salva', methods=['POST'])
def processa_modifica_entrata(entrata_id):
    anno_redirect, mese_redirect = datetime.today().year, datetime.today().month; db_temp = None
    try:
        db_temp = get_db()
        data_record_orig = db_temp.execute('SELECT data FROM entrate WHERE id = ?', (entrata_id,)).fetchone()
        if data_record_orig: dt_orig = datetime.strptime(data_record_orig['data'], '%Y-%m-%d'); anno_redirect, mese_redirect = dt_orig.year, dt_orig.month
    finally:
        if db_temp: db_temp.close()
    if request.method == 'POST':
        data_nuova, tipo_entrata, descrizione, importo_str, ricevuto_da = request.form.get('data'), request.form.get('tipo_entrata_val'), request.form.get('descrizione_entrata'), request.form.get('importo'), request.form.get('ricevuto_da')
        if not all([data_nuova, tipo_entrata, importo_str, ricevuto_da]): flash("Errore: Campi obbligatori mancanti!", "danger"); return redirect(url_for('modifica_entrata_form', entrata_id=entrata_id))
        try:
            importo = float(importo_str)
            if importo <= 0: raise ValueError("Importo non positivo")
            dt_nuova = datetime.strptime(data_nuova, '%Y-%m-%d'); anno_redirect, mese_redirect = dt_nuova.year, dt_nuova.month
        except ValueError: flash("Errore: Importo o Data non validi.", "danger"); return redirect(url_for('modifica_entrata_form', entrata_id=entrata_id))
        db = None
        try:
            db = get_db()
            db.execute('UPDATE entrate SET data = ?, tipo_entrata = ?, descrizione = ?, importo = ?, ricevuto_da = ? WHERE id = ?', (data_nuova, tipo_entrata, descrizione if descrizione else "", importo, ricevuto_da, entrata_id))
            db.commit(); flash(f"Entrata '{tipo_entrata}{' - ' + descrizione if descrizione else ''}' aggiornata!", "success")
        except sqlite3.Error as e: flash(f"Errore aggiornamento entrata: {e}", "danger")
        finally:
            if db: db.close()
        return redirect(url_for('index', anno=anno_redirect, mese=mese_redirect))
    return redirect(url_for('index', anno=anno_redirect, mese=mese_redirect))

@app.route('/elimina_entrata/<int:entrata_id>', methods=['POST'])
def elimina_entrata(entrata_id):
    anno_redirect, mese_redirect = datetime.today().year, datetime.today().month; db = None
    try:
        db = get_db()
        entrata_info = db.execute('SELECT data, tipo_entrata, descrizione FROM entrate WHERE id = ?', (entrata_id,)).fetchone()
        if entrata_info:
            dt_entrata = datetime.strptime(entrata_info['data'], '%Y-%m-%d'); anno_redirect, mese_redirect = dt_entrata.year, dt_entrata.month
            desc_entrata_eliminata = f"{entrata_info['tipo_entrata']}{' - ' + entrata_info['descrizione'] if entrata_info['descrizione'] else ''}"
        else: flash(f"Entrata ID {entrata_id} non trovata.", "warning"); return redirect(url_for('index'))
        db.execute('DELETE FROM entrate WHERE id = ?', (entrata_id,)); db.commit()
        flash(f"Entrata '{desc_entrata_eliminata}' eliminata!", "success")
    except sqlite3.Error as e: flash(f"Errore eliminazione entrata: {e}", "danger")
    finally:
        if db: db.close()
    return redirect(url_for('index', anno=anno_redirect, mese=mese_redirect))
@app.route('/registro/<int:anno>/<int:mese>')
def registro_mese(anno, mese):
    db = get_db()
    
    try:
        data_corrente_dt = datetime(anno, mese, 1)
    except ValueError:
        flash("Data non valida, mostro il mese corrente.", "warning")
        oggi = datetime.today()
        anno, mese = oggi.year, oggi.month
        data_corrente_dt = datetime(anno, mese, 1)

    nome_mese_corrente = f"{MESI_ITALIANI.get(data_corrente_dt.month, '')} {data_corrente_dt.year}"
    mese_precedente_dt = data_corrente_dt - timedelta(days=1)
    anno_prec, mese_prec = mese_precedente_dt.year, mese_precedente_dt.month
    if data_corrente_dt.month == 12:
        primo_giorno_mese_successivo_dt = datetime(data_corrente_dt.year + 1, 1, 1)
    else:
        primo_giorno_mese_successivo_dt = datetime(data_corrente_dt.year, data_corrente_dt.month + 1, 1)
    anno_succ, mese_succ = primo_giorno_mese_successivo_dt.year, primo_giorno_mese_successivo_dt.month

    anno_mese_str = f"{anno:04d}-{mese:02d}"
    
    spese_giacomo = db.execute(
        'SELECT data, categoria, descrizione, importo FROM spese WHERE strftime("%Y-%m", data) = ? AND pagato_da = ? ORDER BY data DESC, id DESC',
        (anno_mese_str, 'Giacomo')
    ).fetchall()
    
    spese_erica = db.execute(
        'SELECT data, categoria, descrizione, importo FROM spese WHERE strftime("%Y-%m", data) = ? AND pagato_da = ? ORDER BY data DESC, id DESC',
        (anno_mese_str, 'Erica')
    ).fetchall()
    
    db.close()
    
    return render_template('registro_mese.html',
                           titolo_pagina=f"Registro Spese - {nome_mese_corrente}",
                           nome_mese_corrente=nome_mese_corrente,
                           spese_giacomo=spese_giacomo,
                           spese_erica=spese_erica,
                           anno_prec=anno_prec, mese_prec=mese_prec,
                           anno_succ=anno_succ, mese_succ=mese_succ,
                           # --- CORREZIONE QUI ---
                           current_anno=anno,
                           current_mese=mese)

@app.route('/delta')
@app.route('/delta/<int:anno>')
def delta_annuale(anno=None):
    oggi = datetime.today()
    if anno is None:
        anno = oggi.year
    
    # --- 1. Gestione della Modalità (Reale vs Forecast) ---
    mode = request.args.get('mode', 'reale') # Default è 'reale'
    is_forecast_view = (mode == 'forecast')

    # --- 2. Preparazione delle Date e Titoli in base alla modalità ---
    anno_corrente = anno
    anno_precedente = anno - 1
    
    periodo_str = ""
    num_mesi_calcolo = 12

    if is_forecast_view:
        # Per il forecast, usiamo sempre i 12 mesi completi per l'anno precedente
        start_date_prev = f"{anno_precedente:04d}-01-01"
        end_date_prev = f"{anno_precedente:04d}-12-31"
        # E i dati fino a oggi per l'anno corrente, per calcolare la media
        start_date_curr = f"{anno_corrente:04d}-01-01"
        end_date_curr = oggi.strftime('%Y-%m-%d')
        num_mesi_calcolo = oggi.month if anno_corrente == oggi.year else 12
        periodo_str = f"Forecast {anno_corrente} (su media di {num_mesi_calcolo} mesi) vs Reale {anno_precedente}"
    else:
        # Per la vista reale, confrontiamo periodi identici
        giorno_fine, mese_fine = (31, 12)
        if anno_corrente == oggi.year:
            giorno_fine, mese_fine = oggi.day, oggi.month
        
        start_date_curr = f"{anno_corrente:04d}-01-01"
        end_date_curr = f"{anno_corrente:04d}-{mese_fine:02d}-{giorno_fine:02d}"
        start_date_prev = f"{anno_precedente:04d}-01-01"
        end_date_prev = f"{anno_precedente:04d}-{mese_fine:02d}-{giorno_fine:02d}"
        periodo_str = f"fino al {giorno_fine} {MESI_ITALIANI[mese_fine]}"

    db = get_db()

    # --- 3. Logica di Calcolo ---
    def calculate_delta(current, previous):
        delta_abs = current - previous
        delta_perc = (delta_abs / previous * 100) if previous != 0 else 0
        return {'abs': delta_abs, 'perc': delta_perc}

    # Funzione per i dati aggregati per Categoria/Tipo
    def get_summary_data(tabella, colonna_cat, colonna_persona):
        query = f"""
            SELECT strftime('%Y', data) as anno, {colonna_cat} as categoria, {colonna_persona} as persona, SUM(importo) as totale
            FROM {tabella} WHERE (data BETWEEN ? AND ?) OR (data BETWEEN ? AND ?) GROUP BY anno, categoria, persona """
        cursor = db.execute(query, (start_date_curr, end_date_curr, start_date_prev, end_date_prev))
        
        data_dict = {}
        for row in cursor.fetchall():
            anno_r, cat, persona, totale = int(row['anno']), row['categoria'], row['persona'], row['totale'] or 0.0
            periodo = 'current' if anno_r == anno_corrente else 'previous'
            
            if cat not in data_dict:
                data_dict[cat] = {'previous': {'Giacomo': 0.0, 'Erica': 0.0, 'Totale': 0.0}, 'current': {'Giacomo': 0.0, 'Erica': 0.0, 'Totale': 0.0}}
            
            data_dict[cat][periodo][persona] += totale
            data_dict[cat][periodo]['Totale'] += totale

        if is_forecast_view and num_mesi_calcolo > 0:
            for cat in data_dict:
                for p in ['Giacomo', 'Erica', 'Totale']:
                    media_mensile = data_dict[cat]['current'][p] / num_mesi_calcolo
                    data_dict[cat]['current'][p] = media_mensile * 12

        for cat, data in data_dict.items():
            data['delta'] = {}
            for p in ['Giacomo', 'Erica', 'Totale']:
                data['delta'][p] = calculate_delta(data['current'][p], data['previous'][p])
        
        return data_dict

    spese_per_categoria = get_summary_data('spese', 'categoria', 'pagato_da')
    entrate_per_tipo = get_summary_data('entrate', 'tipo_entrata', 'ricevuto_da')

    # Riepilogo per i box in alto
    riepilogo = {p: {'entrate': {}, 'spese': {}, 'risparmio': {}} for p in ['Giacomo', 'Erica', 'Totale']}
    for p in ['Giacomo', 'Erica', 'Totale']:
        entrate_curr = sum(d['current'][p] for d in entrate_per_tipo.values())
        entrate_prev = sum(d['previous'][p] for d in entrate_per_tipo.values())
        spese_curr = sum(d['current'][p] for d in spese_per_categoria.values())
        spese_prev = sum(d['previous'][p] for d in spese_per_categoria.values())
        
        riepilogo[p]['entrate'] = {'current': entrate_curr, 'delta': calculate_delta(entrate_curr, entrate_prev)}
        riepilogo[p]['spese'] = {'current': spese_curr, 'delta': calculate_delta(spese_curr, spese_prev)}
        riepilogo[p]['risparmio'] = {'current': entrate_curr - spese_curr, 'delta': calculate_delta(entrate_curr - spese_curr, entrate_prev - spese_prev)}

    # Dati mensili (vengono calcolati e mostrati solo in modalità 'reale')
    dettaglio_mensile_lista = []
    medie_spese = {}
    medie_entrate = {}
    if not is_forecast_view:
        def get_monthly_breakdown(tabella, colonna_persona):
            query = f"""
                SELECT strftime('%Y', data) as anno, strftime('%m', data) as mese, {colonna_persona} as persona, SUM(importo) as totale
                FROM {tabella} WHERE (data BETWEEN ? AND ?) OR (data BETWEEN ? AND ?) GROUP BY anno, mese, persona """
            cursor = db.execute(query, (start_date_curr, end_date_curr, start_date_prev, end_date_prev))
            dati_mensili = {i: {'mese_nome': MESI_ITALIANI[i], 'previous': {'Giacomo': 0.0, 'Erica': 0.0, 'Totale': 0.0}, 'current': {'Giacomo': 0.0, 'Erica': 0.0, 'Totale': 0.0}} for i in range(1, 13)}
            
            for row in cursor.fetchall():
                anno_r, mese_num, persona, totale = int(row['anno']), int(row['mese']), row['persona'], row['totale'] or 0.0
                periodo = 'current' if anno_r == anno_corrente else 'previous'
                dati_mensili[mese_num][periodo][persona] = totale
                dati_mensili[mese_num][periodo]['Totale'] += totale
            
            lista_finale = []
            for i in range(1, (datetime.strptime(end_date_curr, '%Y-%m-%d').month) + 1):
                mese_data = dati_mensili[i]
                mese_data['delta'] = {}
                for p in ['Giacomo', 'Erica', 'Totale']:
                    mese_data['delta'][p] = calculate_delta(mese_data['current'][p], mese_data['previous'][p])
                lista_finale.append(mese_data)

            medie = {'previous': {}, 'current': {}, 'delta': {}}
            num_mesi_periodo = len(lista_finale)
            if num_mesi_periodo > 0:
                for p in ['Giacomo', 'Erica', 'Totale']:
                    medie['previous'][p] = sum(m['previous'][p] for m in lista_finale) / num_mesi_periodo
                    medie['current'][p] = sum(m['current'][p] for m in lista_finale) / num_mesi_periodo
                    medie['delta'][p] = calculate_delta(medie['current'][p], medie['previous'][p])
            return lista_finale, medie

        spese_mensili, medie_spese = get_monthly_breakdown('spese', 'pagato_da')
        entrate_mensili, medie_entrate = get_monthly_breakdown('entrate', 'ricevuto_da')

    cursor_anni = db.execute("SELECT DISTINCT STRFTIME('%Y', data) as anno FROM spese UNION SELECT DISTINCT STRFTIME('%Y', data) as anno FROM entrate ORDER BY anno DESC")
    anni_disponibili = [row['anno'] for row in cursor_anni.fetchall()]
    db.close()
    
    return render_template('delta_annuale.html',
                           titolo_pagina=f"Confronto Annuale {anno_corrente}",
                           riepilogo=riepilogo,
                           spese_per_categoria=spese_per_categoria,
                           entrate_per_tipo=entrate_per_tipo,
                           spese_mensili=spese_mensili,
                           entrate_mensili=entrate_mensili,
                           medie_spese=medie_spese,
                           medie_entrate=medie_entrate,
                           anno_corrente=anno_corrente,
                           anno_precedente=anno_precedente,
                           anni_disponibili=anni_disponibili,
                           periodo_str=periodo_str,
                           is_forecast_view=is_forecast_view,
                           mode=mode)
if __name__ == '__main__':
    print("Avvio applicazione...")
    # init_db()
    app.run(debug=True)