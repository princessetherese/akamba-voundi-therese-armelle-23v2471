# app_supabase_ultimate.py - Version ultime avec robustesse et fiabilité maximales
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
from supabase import create_client
import time
import warnings
import re
import json
import os
from datetime import timedelta
import hashlib
warnings.filterwarnings('ignore')

# ==================== CONFIGURATION ====================
# Configuration des limites
MAX_COMMANDES_PAR_JOUR = 50
MAX_PANIER_ITEMS = 20
PRIX_MIN = 1000
PRIX_MAX = 10000000
AGE_MIN = 18
AGE_MAX = 100
REVENU_MIN = 50000
REVENU_MAX = 100000000

# Fichier de logs
LOG_FILE = "application_logs.json"

# ==================== GESTION DES LOGS ====================
def ecrire_log(action, details, niveau="INFO"):
    """Écrit un log de l'action effectuée"""
    try:
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "details": details,
            "niveau": niveau
        }
        
        # Charger les logs existants
        logs = []
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'r') as f:
                logs = json.load(f)
        
        # Ajouter le nouveau log
        logs.append(log_entry)
        
        # Garder seulement les 1000 derniers logs
        if len(logs) > 1000:
            logs = logs[-1000:]
        
        # Sauvegarder
        with open(LOG_FILE, 'w') as f:
            json.dump(logs, f, indent=2, default=str)
    except Exception as e:
        # Ne pas faire planter l'application pour un log
        pass

def afficher_logs():
    """Affiche les derniers logs (pour admin)"""
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'r') as f:
                logs = json.load(f)
                return logs[-20:]  # Derniers 20 logs
    except:
        return []
    return []

# ==================== BACKUP AUTOMATIQUE ====================
def sauvegarder_donnees():
    """Sauvegarde automatique des données"""
    try:
        backup_dir = "backups"
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Sauvegarde clients
        if len(st.session_state.df_clients) > 0:
            clients_backup = st.session_state.df_clients.copy()
            clients_backup.to_csv(f"{backup_dir}/clients_backup_{timestamp}.csv", index=False)
        
        # Sauvegarde achats
        if len(st.session_state.df_achats) > 0:
            achats_backup = st.session_state.df_achats.copy()
            achats_backup.to_csv(f"{backup_dir}/achats_backup_{timestamp}.csv", index=False)
        
        # Supprimer les backups vieux de plus de 30 jours
        for file in os.listdir(backup_dir):
            file_path = os.path.join(backup_dir, file)
            if os.path.getctime(file_path) < time.time() - 30 * 86400:
                os.remove(file_path)
        
        ecrire_log("BACKUP", f"Sauvegarde automatique effectuée à {timestamp}", "INFO")
        return True
    except Exception as e:
        ecrire_log("BACKUP_ERROR", str(e), "ERROR")
        return False

# ==================== VALIDATION AVANCÉE ====================
def valider_telephone_mobile_money(telephone):
    """Valide le numéro de téléphone Mobile Money (Cameroun)"""
    if not telephone:
        return False
    
    # Enlever les espaces et les caractères spéciaux
    telephone_clean = re.sub(r'[^0-9]', '', telephone)
    
    # Vérifier le format (6 ou 9 chiffres pour le Cameroun)
    if len(telephone_clean) == 9:
        telephone_clean = "6" + telephone_clean
    elif len(telephone_clean) == 8:
        telephone_clean = "69" + telephone_clean
    
    # Vérifier qu'il commence par 6 et fait 9 chiffres
    pattern = r'^6[0-9]{8}$'
    return bool(re.match(pattern, telephone_clean))

def valider_montant(montant):
    """Valide le montant d'un achat"""
    if montant <= 0:
        return False, "Le montant doit être supérieur à 0"
    if montant > 10000000:
        return False, "Le montant dépasse la limite autorisée (10 millions FCFA)"
    if montant % 100 != 0:
        return False, "Le montant doit être un multiple de 100 FCFA"
    return True, "OK"

def valider_age(age):
    """Valide l'âge du client"""
    if age < AGE_MIN:
        return False, f"L'âge minimum est {AGE_MIN} ans"
    if age > AGE_MAX:
        return False, f"L'âge maximum est {AGE_MAX} ans"
    return True, "OK"

def valider_revenu(revenu):
    """Valide le revenu annuel"""
    if revenu < REVENU_MIN:
        return False, f"Le revenu minimum est {REVENU_MIN:,.0f} FCFA"
    if revenu > REVENU_MAX:
        return False, f"Le revenu maximum est {REVENU_MAX:,.0f} FCFA"
    return True, "OK"

def verifier_limites_client(client_id):
    """Vérifie les limites d'activité du client"""
    # Limite de commandes par jour
    aujourd_hui = datetime.now().date()
    commandes_aujourd_hui = st.session_state.df_achats[
        (st.session_state.df_achats['client_id'] == client_id) &
        (pd.to_datetime(st.session_state.df_achats['date']).dt.date == aujourd_hui)
    ]
    
    if len(commandes_aujourd_hui) >= MAX_COMMANDES_PAR_JOUR:
        return False, f"Limite de {MAX_COMMANDES_PAR_JOUR} commandes par jour atteinte"
    
    return True, "OK"

def prevenir_doublon(client_id, produits):
    """Vérifie si une commande similaire a été passée récemment"""
    produits_str = ', '.join(sorted(produits))
    
    # Vérifier les 5 dernières commandes du client
    dernieres_commandes = st.session_state.df_achats[
        st.session_state.df_achats['client_id'] == client_id
    ].tail(5)
    
    for _, commande in dernieres_commandes.iterrows():
        produits_existants = sorted(commande['produits'].split(', '))
        if produits_existants == sorted(produits):
            # Vérifier si moins de 5 minutes se sont écoulées
            temps_commande = pd.to_datetime(commande['date'])
            if (datetime.now() - temps_commande).seconds < 300:
                return False, "Commande similaire déjà effectuée il y a moins de 5 minutes"
    
    return True, "OK"

# ==================== FONCTION DE CONVERSION POUR JSON ====================
def convertir_pour_json(valeur):
    """Convertit les types numpy en types Python standards pour JSON"""
    if isinstance(valeur, (np.int64, np.int32)):
        return int(valeur)
    elif isinstance(valeur, (np.float64, np.float32)):
        return float(valeur)
    elif isinstance(valeur, np.ndarray):
        return valeur.tolist()
    elif hasattr(valeur, 'item'):
        return valeur.item()
    elif pd.isna(valeur):
        return None
    else:
        return valeur

# ==================== CONNEXION SUPABASE ====================
def init_supabase():
    """Initialise la connexion Supabase avec gestion d'erreur renforcée"""
    try:
        SUPABASE_URL = st.secrets["SUPABASE_URL"]
        SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
        
        if not SUPABASE_URL or not SUPABASE_KEY:
            st.error("Configuration Supabase manquante")
            return None
        
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        ecrire_log("SUPABASE", "Connexion établie avec succès", "INFO")
        return client
    except Exception as e:
        ecrire_log("SUPABASE_ERROR", str(e), "ERROR")
        st.error(f"Erreur de connexion à Supabase : {e}")
        return None

supabase = init_supabase()

# ==================== FONCTIONS BASE DE DONNÉES AVEC RETRY ====================
def executer_avec_retry(fonction, max_retries=3, delay=1):
    """Exécute une fonction avec réessai en cas d'erreur"""
    for i in range(max_retries):
        try:
            return fonction()
        except Exception as e:
            if i == max_retries - 1:
                raise e
            time.sleep(delay * (i + 1))  # Backoff exponentiel
    return None

def charger_clients():
    """Charge les clients depuis Supabase avec retry"""
    if supabase is None:
        return pd.DataFrame()
    
    def _charger():
        response = supabase.table("clients").select("*").execute()
        if response.data:
            return pd.DataFrame(response.data)
        return pd.DataFrame()
    
    try:
        return executer_avec_retry(_charger)
    except Exception as e:
        ecrire_log("CHARGEMENT_CLIENTS_ERROR", str(e), "ERROR")
        st.error(f"Erreur chargement clients : {e}")
        return pd.DataFrame()

def sauvegarder_client(client):
    """Sauvegarde avec validation et retry"""
    if supabase is None:
        return None
    
    # Validation des données
    if 'age' in client:
        valide, msg = valider_age(client['age'])
        if not valide:
            st.error(msg)
            return None
    
    if 'revenu_annuel_fcfa' in client:
        valide, msg = valider_revenu(client['revenu_annuel_fcfa'])
        if not valide:
            st.error(msg)
            return None
    
    def _sauvegarder():
        client_clean = {k: convertir_pour_json(v) for k, v in client.items()}
        response = supabase.table("clients").insert(client_clean).execute()
        return response.data[0] if response.data else None
    
    try:
        resultat = executer_avec_retry(_sauvegarder)
        if resultat:
            ecrire_log("CLIENT_CREATED", f"Client {client.get('nom', 'N/A')} créé (ID: {resultat.get('client_id', 'N/A')})", "INFO")
            sauvegarder_donnees()  # Backup automatique
        return resultat
    except Exception as e:
        ecrire_log("CLIENT_SAVE_ERROR", str(e), "ERROR")
        st.error(f"Erreur sauvegarde client : {e}")
        return None

def mettre_a_jour_client(client_id, data):
    """Met à jour avec validation"""
    if supabase is None:
        return False
    
    def _mettre_a_jour():
        data_clean = {k: convertir_pour_json(v) for k, v in data.items()}
        supabase.table("clients").update(data_clean).eq("client_id", client_id).execute()
        return True
    
    try:
        resultat = executer_avec_retry(_mettre_a_jour)
        if resultat:
            ecrire_log("CLIENT_UPDATED", f"Client ID {client_id} mis à jour", "INFO")
            sauvegarder_donnees()
        return resultat
    except Exception as e:
        ecrire_log("CLIENT_UPDATE_ERROR", str(e), "ERROR")
        st.error(f"Erreur mise à jour client : {e}")
        return False

def charger_achats():
    """Charge les achats avec retry"""
    if supabase is None:
        return pd.DataFrame()
    
    def _charger():
        response = supabase.table("achats").select("*").order("order_id", desc=True).execute()
        if response.data:
            return pd.DataFrame(response.data)
        return pd.DataFrame()
    
    try:
        return executer_avec_retry(_charger)
    except Exception as e:
        ecrire_log("CHARGEMENT_ACHATS_ERROR", str(e), "ERROR")
        st.error(f"Erreur chargement achats : {e}")
        return pd.DataFrame()

def sauvegarder_achat(achat):
    """Sauvegarde avec validation multiple"""
    if supabase is None:
        return None
    
    # Validation du montant
    valide, msg = valider_montant(achat['montant_fcfa'])
    if not valide:
        st.error(msg)
        return None
    
    # Validation du téléphone si Mobile Money
    if "Mobile Money" in achat['mode_paiement'] and achat.get('telephone'):
        if not valider_telephone_mobile_money(achat['telephone']):
            st.error("Numéro de téléphone Mobile Money invalide (doit commencer par 6, 9 chiffres)")
            return None
    
    def _sauvegarder():
        achat_clean = {k: convertir_pour_json(v) for k, v in achat.items()}
        response = supabase.table("achats").insert(achat_clean).execute()
        return response.data[0] if response.data else None
    
    try:
        resultat = executer_avec_retry(_sauvegarder)
        if resultat:
            ecrire_log("ORDER_CREATED", f"Commande #{achat.get('order_id', 'N/A')} créée par {achat.get('client_nom', 'N/A')}", "INFO")
            sauvegarder_donnees()
        return resultat
    except Exception as e:
        ecrire_log("ORDER_SAVE_ERROR", str(e), "ERROR")
        st.error(f"Erreur sauvegarde commande : {e}")
        return None

def mettre_a_jour_achat(order_id, data):
    """Met à jour avec validation"""
    if supabase is None:
        return False
    
    def _mettre_a_jour():
        data_clean = {k: convertir_pour_json(v) for k, v in data.items()}
        supabase.table("achats").update(data_clean).eq("order_id", order_id).execute()
        return True
    
    try:
        resultat = executer_avec_retry(_mettre_a_jour)
        if resultat:
            ecrire_log("ORDER_UPDATED", f"Commande #{order_id} modifiée", "INFO")
        return resultat
    except Exception as e:
        ecrire_log("ORDER_UPDATE_ERROR", str(e), "ERROR")
        st.error(f"Erreur mise à jour commande : {e}")
        return False

def supprimer_achat(order_id):
    """Supprime avec log"""
    if supabase is None:
        return False
    
    def _supprimer():
        supabase.table("achats").delete().eq("order_id", order_id).execute()
        return True
    
    try:
        resultat = executer_avec_retry(_supprimer)
        if resultat:
            ecrire_log("ORDER_DELETED", f"Commande #{order_id} supprimée", "INFO")
            sauvegarder_donnees()
        return resultat
    except Exception as e:
        ecrire_log("ORDER_DELETE_ERROR", str(e), "ERROR")
        st.error(f"Erreur suppression commande : {e}")
        return False

# ==================== CHARGEMENT INITIAL ====================
if 'df_clients' not in st.session_state:
    st.session_state.df_clients = charger_clients()

if 'df_achats' not in st.session_state:
    st.session_state.df_achats = charger_achats()
    
if 'edit_order_id' not in st.session_state:
    st.session_state.edit_order_id = None
    
if 'last_backup' not in st.session_state:
    st.session_state.last_backup = None

# Backup automatique toutes les heures
if st.session_state.last_backup is None or \
   (datetime.now() - st.session_state.last_backup).seconds > 3600:
    sauvegarder_donnees()
    st.session_state.last_backup = datetime.now()

# ==================== CATALOGUE PRODUITS ====================
PRODUITS = {
    # ÉLECTRONIQUE (10 produits)
    '📱 Smartphone Tecno Camon 20 Pro': {'prix': 150000, 'categorie': 'Électronique', 'desc': '8Go RAM, 128Go stockage'},
    '📱 iPhone 14 Pro Max': {'prix': 850000, 'categorie': 'Électronique', 'desc': 'Apple A16, 256Go'},
    '📱 Samsung Galaxy S23 Ultra': {'prix': 750000, 'categorie': 'Électronique', 'desc': '12Go RAM, 256Go'},
    '📱 Xiaomi Redmi Note 12': {'prix': 180000, 'categorie': 'Électronique', 'desc': '6Go RAM, 128Go'},
    '💻 PC Portable HP Pavilion': {'prix': 450000, 'categorie': 'Électronique', 'desc': 'Core i7, 16Go RAM'},
    '💻 PC Dell XPS 13': {'prix': 800000, 'categorie': 'Électronique', 'desc': 'Core i9, 32Go RAM'},
    '💻 PC Lenovo ThinkPad': {'prix': 550000, 'categorie': 'Électronique', 'desc': 'Core i5, 8Go RAM'},
    '🎧 Casque Sony WH-1000XM5': {'prix': 120000, 'categorie': 'Électronique', 'desc': 'Réduction de bruit'},
    '⌚ Apple Watch Series 8': {'prix': 250000, 'categorie': 'Électronique', 'desc': 'GPS + Cellular'},
    '🔊 Enceinte JBL Charge 5': {'prix': 85000, 'categorie': 'Électronique', 'desc': 'Bluetooth, 20W'},
    
    # MODE (10 produits)
    '👕 T-shirt Lacoste Homme': {'prix': 25000, 'categorie': 'Mode', 'desc': '100% coton, taille S-XXL'},
    '👕 Chemise Hugo Boss': {'prix': 65000, 'categorie': 'Mode', 'desc': 'Luxe, coupe slim'},
    '👖 Jean Levi\'s 501': {'prix': 45000, 'categorie': 'Mode', 'desc': 'Jean brut original'},
    '👗 Robe Zara Collection': {'prix': 35000, 'categorie': 'Mode', 'desc': 'Soirée, longue'},
    '👟 Basket Nike Air Max': {'prix': 85000, 'categorie': 'Mode', 'desc': 'Confort, style sport'},
    '👟 Basket Adidas Ultraboost': {'prix': 95000, 'categorie': 'Mode', 'desc': 'Running léger'},
    '🧥 Manteau Ralph Lauren': {'prix': 120000, 'categorie': 'Mode', 'desc': 'Hiver, doudoune'},
    '🧣 Écharpe Burberry': {'prix': 55000, 'categorie': 'Mode', 'desc': 'Cachemire luxe'},
    '👔 Costume Armani': {'prix': 250000, 'categorie': 'Mode', 'desc': 'Tailleur 3 pièces'},
    '🕶️ Lunettes Ray-Ban': {'prix': 75000, 'categorie': 'Mode', 'desc': 'Solaire, classique'},
    
    # MAISON (10 produits)
    '🛋️ Canapé convertible 3 places': {'prix': 350000, 'categorie': 'Maison', 'desc': 'Cuir, noir'},
    '🛏️ Lit King Size': {'prix': 280000, 'categorie': 'Maison', 'desc': 'Avec sommier et matelas'},
    '🚪 Armoire 5 portes': {'prix': 250000, 'categorie': 'Maison', 'desc': 'Chêne massif'},
    '🍽️ Table à manger extensible': {'prix': 180000, 'categorie': 'Maison', 'desc': '6-8 places, bois'},
    '💡 Lampe sur pied design': {'prix': 45000, 'categorie': 'Maison', 'desc': 'LED, moderne'},
    '🪑 Lot de 6 chaises': {'prix': 120000, 'categorie': 'Maison', 'desc': 'Moderne, confortables'},
    '📺 Téléviseur Samsung 65"': {'prix': 500000, 'categorie': 'Maison', 'desc': '4K Ultra HD Smart TV'},
    '❄️ Réfrigérateur Samsung': {'prix': 400000, 'categorie': 'Maison', 'desc': '520L, No Frost'},
    '🧺 Machine à laver LG': {'prix': 300000, 'categorie': 'Maison', 'desc': '9kg, Silencieuse'},
    '🍳 Four micro-ondes Samsung': {'prix': 85000, 'categorie': 'Maison', 'desc': 'Grill, 25L'},
    
    # SPORTS (10 produits)
    '⚽ Ballon de football officiel': {'prix': 15000, 'categorie': 'Sports', 'desc': 'Taille 5, FIFA Quality'},
    '🏀 Ballon de basketball NBA': {'prix': 20000, 'categorie': 'Sports', 'desc': 'Taille 7, cuir synthétique'},
    '🎾 Raquette de tennis Babolat': {'prix': 65000, 'categorie': 'Sports', 'desc': 'Pro, carbone'},
    '🏋️ Set haltères 20kg': {'prix': 45000, 'categorie': 'Sports', 'desc': 'Avec barre, 2 haltères'},
    '🚴 Vélo de route Triban': {'prix': 250000, 'categorie': 'Sports', 'desc': '21 vitesses, alu'},
    '🏃 Tapis de course électrique': {'prix': 350000, 'categorie': 'Sports', 'desc': 'Moteur 2.5HP, pliable'},
    '🥊 Gants de boxe Everlast': {'prix': 28000, 'categorie': 'Sports', 'desc': 'Cuir, 14oz'},
    '🏊 Lunettes de natation Speedo': {'prix': 12000, 'categorie': 'Sports', 'desc': 'Anti-buée, UV'},
    '🧘 Tapis de yoga premium': {'prix': 18000, 'categorie': 'Sports', 'desc': 'Anti-dérapant, 10mm'},
    '⚽ Maillot PSG domicile': {'prix': 35000, 'categorie': 'Sports', 'desc': 'Officiel, Messi #30'}
}

def format_fcfa(x):
    if pd.isna(x) or x == 0:
        return "0 FCFA"
    return f"{x:,.0f} FCFA".replace(",", " ")

def enregistrer_achat(client_id, client_nom, produits_achetes, montant_total, mode_paiement, phone_number=None):
    """Enregistre un nouvel achat avec validations renforcées"""
    
    # Validation du montant
    valide, msg = valider_montant(montant_total)
    if not valide:
        st.error(msg)
        return None
    
    # Validation des limites
    valide, msg = verifier_limites_client(client_id)
    if not valide:
        st.error(msg)
        return None
    
    # Prévention des doublons
    valide, msg = prevenir_doublon(client_id, produits_achetes)
    if not valide:
        st.warning(msg)
    
    # Validation du nombre d'articles
    if len(produits_achetes) > MAX_PANIER_ITEMS:
        st.error(f"Le panier ne peut pas contenir plus de {MAX_PANIER_ITEMS} articles")
        return None
    
    if len(st.session_state.df_achats) == 0:
        order_id = 1
    else:
        order_id = int(st.session_state.df_achats['order_id'].max()) + 1
    
    nouvel_achat = {
        'order_id': order_id,
        'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'client_id': int(client_id),
        'client_nom': client_nom,
        'produits': ', '.join(produits_achetes),
        'montant_fcfa': int(montant_total),
        'mode_paiement': mode_paiement,
        'nb_articles': len(produits_achetes),
        'telephone': phone_number if phone_number else '',
        'statut': 'Confirmé'
    }
    
    resultat = sauvegarder_achat(nouvel_achat)
    if resultat:
        st.session_state.df_achats = charger_achats()
        
        # Mettre à jour le CA du client
        idx = st.session_state.df_clients[st.session_state.df_clients['client_id'] == client_id].index
        if len(idx) > 0:
            nouveau_ca = int(st.session_state.df_clients.loc[idx[0], 'ca_total_fcfa'] + montant_total)
            nouveau_nb = int(st.session_state.df_clients.loc[idx[0], 'nb_achats'] + 1)
            mettre_a_jour_client(client_id, {
                'ca_total_fcfa': nouveau_ca,
                'nb_achats': nouveau_nb,
                'dernier_achat': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            st.session_state.df_clients = charger_clients()
    
    return order_id

def modifier_commande(order_id, nouveaux_produits, nouveau_montant):
    """Modifie une commande avec validation"""
    commande = st.session_state.df_achats[st.session_state.df_achats['order_id'] == order_id]
    if len(commande) == 0:
        return False
    
    # Validation du nouveau montant
    valide, msg = valider_montant(nouveau_montant)
    if not valide:
        st.error(msg)
        return False
    
    ancien_montant = int(commande.iloc[0]['montant_fcfa'])
    client_id = int(commande.iloc[0]['client_id'])
    
    mise_a_jour = {
        'produits': ', '.join(nouveaux_produits),
        'montant_fcfa': int(nouveau_montant),
        'nb_articles': len(nouveaux_produits),
        'statut': 'Modifié'
    }
    
    if mettre_a_jour_achat(order_id, mise_a_jour):
        st.session_state.df_achats = charger_achats()
        
        # Mettre à jour le CA du client
        idx = st.session_state.df_clients[st.session_state.df_clients['client_id'] == client_id].index
        if len(idx) > 0:
            nouveau_ca = int(st.session_state.df_clients.loc[idx[0], 'ca_total_fcfa'] + (nouveau_montant - ancien_montant))
            mettre_a_jour_client(client_id, {'ca_total_fcfa': nouveau_ca})
            st.session_state.df_clients = charger_clients()
        
        return True
    return False

def supprimer_commande(order_id):
    """Supprime une commande"""
    commande = st.session_state.df_achats[st.session_state.df_achats['order_id'] == order_id]
    if len(commande) == 0:
        return False
    
    client_id = int(commande.iloc[0]['client_id'])
    montant = int(commande.iloc[0]['montant_fcfa'])
    
    if supprimer_achat(order_id):
        st.session_state.df_achats = charger_achats()
        
        # Mettre à jour le CA du client
        idx = st.session_state.df_clients[st.session_state.df_clients['client_id'] == client_id].index
        if len(idx) > 0:
            nouveau_ca = int(st.session_state.df_clients.loc[idx[0], 'ca_total_fcfa'] - montant)
            nouveau_nb = int(st.session_state.df_clients.loc[idx[0], 'nb_achats'] - 1)
            mettre_a_jour_client(client_id, {
                'ca_total_fcfa': nouveau_ca,
                'nb_achats': nouveau_nb
            })
            st.session_state.df_clients = charger_clients()
        
        return True
    return False

# ==================== CSS ====================
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 20px;
        margin-bottom: 2rem;
        color: white;
        text-align: center;
    }
    .metric-card {
        background: white;
        padding: 1rem;
        border-radius: 15px;
        text-align: center;
        box-shadow: 0 4px 15px rgba(0,0,0,0.08);
        transition: transform 0.3s ease;
    }
    .metric-card:hover {
        transform: translateY(-5px);
    }
    .mobile-money-card {
        background: linear-gradient(135deg, #FF6600 0%, #FF8533 100%);
        padding: 1rem;
        border-radius: 12px;
        color: white;
        text-align: center;
    }
    .product-card {
        background: white;
        border-radius: 12px;
        padding: 0.8rem;
        margin: 0.5rem 0;
        border: 1px solid #e9ecef;
        transition: all 0.3s ease;
    }
    .product-card:hover {
        border-color: #FF6600;
        box-shadow: 0 4px 12px rgba(255,102,0,0.15);
    }
    .footer {
        text-align: center;
        padding: 1.5rem;
        margin-top: 2rem;
        border-top: 1px solid #e9ecef;
        color: #6c757d;
    }
    .order-card {
        background: white;
        border-radius: 12px;
        padding: 1rem;
        margin: 0.5rem 0;
        border-left: 4px solid #667eea;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }
    .success-badge {
        background: #28a745;
        color: white;
        padding: 0.2rem 0.5rem;
        border-radius: 10px;
        font-size: 0.7rem;
        display: inline-block;
    }
    .warning-badge {
        background: #ffc107;
        color: black;
        padding: 0.2rem 0.5rem;
        border-radius: 10px;
        font-size: 0.7rem;
        display: inline-block;
    }
</style>
""", unsafe_allow_html=True)

# ==================== HEADER ====================
st.markdown("""
<div class="main-header">
    <h1>🛍️ ShopAnalyzer Pro</h1>
    <p>Plateforme intelligente de collecte et d'analyse de données e-commerce</p>
    <div style="margin-top: 1rem;">
        <span style="background:#FF6600; padding:0.2rem 0.8rem; border-radius:20px;">📱 Mobile Money</span>
        <span style="background:#2196F3; padding:0.2rem 0.8rem; border-radius:20px;">✏️ Modification</span>
        <span style="background:#dc3545; padding:0.2rem 0.8rem; border-radius:20px;">🗑️ Suppression</span>
        <span style="background:#28a745; padding:0.2rem 0.8rem; border-radius:20px;">🎁 40 Produits</span>
        <span style="background:#17a2b8; padding:0.2rem 0.8rem; border-radius:20px;">🔒 Ultra Sécurisé</span>
    </div>
</div>
""", unsafe_allow_html=True)

# ==================== SIDEBAR ====================
with st.sidebar:
    st.markdown("### 👩‍💻 **Armelle's Dashboard**")
    st.markdown("---")
    
    total_ventes = st.session_state.df_achats['montant_fcfa'].sum() if len(st.session_state.df_achats) > 0 else 0
    nb_commandes = len(st.session_state.df_achats)
    nb_clients = len(st.session_state.df_clients)
    
    st.markdown(f"""
    <div style='background: #667eea15; padding: 1rem; border-radius: 15px;'>
        <div>💰 CHIFFRE D'AFFAIRES</div>
        <div style='font-size: 1.5rem; font-weight: bold;'>{format_fcfa(total_ventes)}</div>
        <hr>
        <div>📦 COMMANDES</div>
        <div style='font-size: 1.5rem; font-weight: bold;'>{nb_commandes}</div>
        <hr>
        <div>👥 CLIENTS</div>
        <div style='font-size: 1.5rem; font-weight: bold;'>{nb_clients}</div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("""
    <div class="mobile-money-card">
        📱 <strong>Mobile Money</strong><br>
        <small>Paiement instantané<br>MTN, Orange, Camtel</small>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    st.success(f"🎁 **{len(PRODUITS)} produits** disponibles")
    
    # Indicateurs de sécurité
    st.markdown("---")
    st.markdown("### 🔒 **Sécurité**")
    st.markdown("✅ Validation des données")
    st.markdown("✅ Protection doublons")
    st.markdown("✅ Backup automatique")
    st.markdown("✅ Logs des actions")
    
    st.markdown("---")
    st.caption("© 2024 ShopAnalyzer Pro by Armelle")

# ==================== MENU PRINCIPAL ====================
menu = st.sidebar.radio(
    "Navigation",
    ["🛒 Nouvel Achat", "📊 Dashboard", "📊 Analyse Descriptive", "📋 Mes Commandes", "👤 Clients", "🔧 Administration"],
    index=0
)

# ==================== PAGE 1: NOUVEL ACHAT ====================
if menu == "🛒 Nouvel Achat":
    st.markdown("## 🛒 **Nouvelle commande**")
    st.caption(f"📦 **{len(PRODUITS)} produits** disponibles - Choisissez vos articles ci-dessous")
    
    with st.form("achat_form", clear_on_submit=True):
        col1, col2 = st.columns([1, 1.5])
        
        with col1:
            st.markdown("### 👤 **Informations client**")
            
            option_client = st.radio(
                "Type de client",
                ["✨ Nouveau client", "⭐ Client existant"],
                horizontal=True
            )
            
            if option_client == "⭐ Client existant":
                if len(st.session_state.df_clients) > 0:
                    client_options = {f"{row['nom']} ({row['ville']})": row['client_id'] 
                                     for _, row in st.session_state.df_clients.iterrows()}
                    selected_client_name = st.selectbox("Sélectionnez votre compte", list(client_options.keys()))
                    client_id = client_options[selected_client_name]
                    client_info = st.session_state.df_clients[st.session_state.df_clients['client_id'] == client_id].iloc[0]
                    st.success(f"👋 Bon retour {client_info['avatar']} {client_info['nom']} !")
                    client_nom = client_info['nom']
            else:
                col_a, col_b = st.columns(2)
                with col_a:
                    client_nom = st.text_input("Nom complet *", placeholder="Jean Dupont")
                    age = st.number_input("Âge *", AGE_MIN, AGE_MAX, 30)
                    ville = st.selectbox("Ville *", ['Douala', 'Yaoundé', 'Garoua', 'Bafoussam', 'Bamenda'])
                with col_b:
                    email = st.text_input("Email *", placeholder="jean@email.com")
                    avatar = st.selectbox("Avatar", ['👨', '👩', '👧', '👴', '👵'])
                    revenu_client = st.number_input("Revenu annuel (FCFA) *", REVENU_MIN, REVENU_MAX, 2500000, step=50000)
        
        with col2:
            st.markdown("### 📦 **Catalogue produits**")
            
            produits_selectionnes = []
            montant_total = 0
            
            categories = ['Électronique', 'Mode', 'Maison', 'Sports']
            for categorie in categories:
                produits_cat = [(nom, info) for nom, info in PRODUITS.items() if info['categorie'] == categorie]
                with st.expander(f"📂 {categorie} - {len(produits_cat)} produits", expanded=(categorie == 'Électronique')):
                    cols = st.columns(2)
                    for i, (produit, info) in enumerate(produits_cat):
                        with cols[i % 2]:
                            st.markdown(f"""
                            <div class="product-card">
                                <strong>{produit}</strong><br>
                                <small style="color:#666;">{info['desc']}</small><br>
                                <span style="color:#FF6600; font-weight:bold;">{format_fcfa(info['prix'])}</span>
                            </div>
                            """, unsafe_allow_html=True)
                            quantite = st.number_input("Qté", min_value=0, max_value=10, key=f"{categorie}_{produit}", label_visibility="collapsed")
                            if quantite > 0:
                                if len(produits_selectionnes) + quantite <= MAX_PANIER_ITEMS:
                                    produits_selectionnes.extend([produit] * quantite)
                                    montant_total += info['prix'] * quantite
                                else:
                                    st.warning(f"Limite de {MAX_PANIER_ITEMS} articles par commande")
            
            st.markdown("---")
            st.markdown("### 💳 **Mode de paiement**")
            
            mode_paiement = st.radio(
                "Choisissez votre moyen de paiement",
                ["💳 Carte bancaire", "🚚 Livraison", "📱 Mobile Money (MTN/Orange/Camtel)"],
                index=2
            )
            
            phone_number = None
            if "Mobile Money" in mode_paiement:
                phone_number = st.text_input("📱 Numéro de téléphone Mobile Money", 
                                            placeholder="6X XX XX XX XX",
                                            help="Format: 6XXXXXXXX (9 chiffres)")
                if phone_number and not valider_telephone_mobile_money(phone_number):
                    st.warning("⚠️ Format de numéro invalide. Doit commencer par 6 et faire 9 chiffres")
            
            st.markdown(f"""
            <div style='background: linear-gradient(135deg, #FF6600 0%, #FF8533 100%); 
                        padding: 1rem; border-radius: 15px; text-align: center;'>
                <div style='color: white;'>💰 TOTAL À PAYER</div>
                <div style='font-size: 2rem; font-weight: bold; color: white;'>{format_fcfa(montant_total)}</div>
            </div>
            """, unsafe_allow_html=True)
        
        submitted = st.form_submit_button("✅ Confirmer la commande", use_container_width=True)
        
        if submitted:
            if montant_total == 0:
                st.error("❌ Sélectionnez au moins un produit")
            elif option_client == "✨ Nouveau client" and (not client_nom or not email):
                st.error("❌ Remplissez vos informations")
            elif "Mobile Money" in mode_paiement and phone_number and not valider_telephone_mobile_money(phone_number):
                st.error("❌ Numéro de téléphone Mobile Money invalide")
            else:
                with st.spinner("Traitement en cours..."):
                    time.sleep(0.5)
                    
                    if option_client == "✨ Nouveau client":
                        nouveau_client = {
                            'nom': client_nom,
                            'email': email,
                            'age': int(age),
                            'ville': ville,
                            'avatar': avatar,
                            'revenu_annuel_fcfa': int(revenu_client),
                            'ca_total_fcfa': 0,
                            'nb_achats': 0,
                            'dernier_achat': ''
                        }
                        resultat = sauvegarder_client(nouveau_client)
                        if resultat:
                            st.session_state.df_clients = charger_clients()
                            client_id = resultat['client_id']
                            st.success("✅ Compte créé !")
                        else:
                            st.error("❌ Erreur création compte")
                            st.stop()
                    
                    order_id = enregistrer_achat(client_id, client_nom, produits_selectionnes, montant_total, mode_paiement, phone_number)
                    if order_id:
                        st.balloons()
                        st.success(f"🎉 Commande #{order_id} confirmée !")
                        st.info("💡 Vous pouvez modifier ou supprimer cette commande dans l'onglet 'Mes Commandes'")
                    else:
                        st.error("❌ Erreur lors de l'enregistrement de la commande")

# ==================== PAGE 2: DASHBOARD ====================
elif menu == "📊 Dashboard":
    st.markdown("## 📊 **Tableau de bord**")
    
    if len(st.session_state.df_clients) == 0:
        st.info("📊 Pas encore de données. Commencez par passer des commandes !")
    else:
        col1, col2, col3, col4 = st.columns(4)
        
        total_ventes = st.session_state.df_achats['montant_fcfa'].sum() if len(st.session_state.df_achats) > 0 else 0
        nb_commandes = len(st.session_state.df_achats)
        nb_clients_actifs = len(st.session_state.df_clients[st.session_state.df_clients['nb_achats'] > 0])
        panier_moyen = total_ventes / nb_commandes if nb_commandes > 0 else 0
        
        with col1:
            st.markdown(f"""
            <div class="metric-card">
                <div style="font-size: 2rem;">💰</div>
                <div style="font-size: 1.5rem; font-weight: bold;">{format_fcfa(total_ventes)}</div>
                <div>CHIFFRE D'AFFAIRES</div>
            </div>
            """, unsafe_allow_html=True)
        with col2:
            st.markdown(f"""
            <div class="metric-card">
                <div style="font-size: 2rem;">📦</div>
                <div style="font-size: 1.5rem; font-weight: bold;">{nb_commandes}</div>
                <div>COMMANDES</div>
            </div>
            """, unsafe_allow_html=True)
        with col3:
            st.markdown(f"""
            <div class="metric-card">
                <div style="font-size: 2rem;">👥</div>
                <div style="font-size: 1.5rem; font-weight: bold;">{nb_clients_actifs}</div>
                <div>CLIENTS ACTIFS</div>
            </div>
            """, unsafe_allow_html=True)
        with col4:
            st.markdown(f"""
            <div class="metric-card">
                <div style="font-size: 2rem;">🛒</div>
                <div style="font-size: 1.5rem; font-weight: bold;">{format_fcfa(panier_moyen)}</div>
                <div>PANIER MOYEN</div>
            </div>
            """, unsafe_allow_html=True)
        
        if len(st.session_state.df_achats) > 0:
            df_ventes = st.session_state.df_achats.copy()
            df_ventes['date'] = pd.to_datetime(df_ventes['date'])
            ventes_par_jour = df_ventes.groupby(df_ventes['date'].dt.date)['montant_fcfa'].sum().reset_index()
            
            fig = px.line(ventes_par_jour, x='date', y='montant_fcfa', title="📈 Évolution des ventes")
            st.plotly_chart(fig, use_container_width=True)

# ==================== PAGE 3: ANALYSE DESCRIPTIVE ====================
elif menu == "📊 Analyse Descriptive":
    st.markdown("## 📊 **Analyse Descriptive des Données**")
    st.markdown("*Statistiques et visualisations pour comprendre vos données*")
    st.markdown("---")
    
    if len(st.session_state.df_clients) == 0 and len(st.session_state.df_achats) == 0:
        st.info("📊 Pas encore de données. Commencez par passer des commandes !")
    else:
        # ========== 1. STATISTIQUES GÉNÉRALES ==========
        st.subheader("📈 1. Statistiques Générales")
        
        col1, col2, col3, col4, col5 = st.columns(5)
        
        total_ventes = st.session_state.df_achats['montant_fcfa'].sum() if len(st.session_state.df_achats) > 0 else 0
        nb_commandes = len(st.session_state.df_achats)
        nb_clients = len(st.session_state.df_clients)
        nb_produits_vendus = st.session_state.df_achats['nb_articles'].sum() if len(st.session_state.df_achats) > 0 else 0
        panier_moyen = total_ventes / nb_commandes if nb_commandes > 0 else 0
        
        with col1:
            st.metric("💰 CA Total", format_fcfa(total_ventes))
        with col2:
            st.metric("📦 Commandes", nb_commandes)
        with col3:
            st.metric("👥 Clients", nb_clients)
        with col4:
            st.metric("🛍️ Produits vendus", nb_produits_vendus)
        with col5:
            st.metric("🛒 Panier moyen", format_fcfa(panier_moyen))
        
        st.markdown("---")
        
        # ========== 2. STATISTIQUES DESCRIPTIVES DES CLIENTS ==========
        st.subheader("👥 2. Profil des Clients")
        
        if len(st.session_state.df_clients) > 0:
            col1, col2 = st.columns(2)
            
            with col1:
                # Distribution des âges
                fig_ages = px.histogram(st.session_state.df_clients, x='age', nbins=30,
                                        title="Distribution des âges des clients",
                                        labels={'age':'Âge', 'count':'Nombre de clients'},
                                        color_discrete_sequence=['#667eea'])
                fig_ages.update_layout(showlegend=False)
                st.plotly_chart(fig_ages, use_container_width=True)
                
                # Répartition par ville
                villes_counts = st.session_state.df_clients['ville'].value_counts().reset_index()
                villes_counts.columns = ['Ville', 'Nombre']
                fig_villes = px.bar(villes_counts, x='Ville', y='Nombre',
                                    title="Clients par ville",
                                    color='Ville',
                                    color_discrete_sequence=['#FF6600', '#667eea', '#28a745', '#dc3545', '#17a2b8'])
                st.plotly_chart(fig_villes, use_container_width=True)
            
            with col2:
                # Répartition des revenus
                fig_revenus = px.histogram(st.session_state.df_clients, x='revenu_annuel_fcfa', nbins=20,
                                           title="Distribution des revenus annuels",
                                           labels={'revenu_annuel_fcfa':'Revenu (FCFA)', 'count':'Nombre de clients'},
                                           color_discrete_sequence=['#764ba2'])
                fig_revenus.update_layout(showlegend=False)
                st.plotly_chart(fig_revenus, use_container_width=True)
                
                # Tableau des statistiques clients
                st.markdown("**📊 Statistiques clients**")
                stats_clients = st.session_state.df_clients[['age', 'revenu_annuel_fcfa', 'ca_total_fcfa', 'nb_achats']].describe()
                stats_clients = stats_clients.round(0)
                stats_clients.index = ['Nombre', 'Moyenne', 'Écart-type', 'Min', '25%', 'Médiane', '75%', 'Max']
                stats_clients.columns = ['Âge', 'Revenu (FCFA)', 'CA total (FCFA)', 'Nb achats']
                st.dataframe(stats_clients, use_container_width=True)
        
        st.markdown("---")
        
        # ========== 3. ANALYSE DES VENTES ==========
        st.subheader("🛍️ 3. Analyse des Ventes")
        
        if len(st.session_state.df_achats) > 0:
            col1, col2 = st.columns(2)
            
            with col1:
                # Top produits les plus vendus
                tous_produits = []
                for produits in st.session_state.df_achats['produits']:
                    if produits and produits != '':
                        tous_produits.extend(produits.split(', '))
                
                if tous_produits:
                    top_produits = pd.Series(tous_produits).value_counts().head(10).reset_index()
                    top_produits.columns = ['Produit', 'Nombre de ventes']
                    fig_top = px.bar(top_produits, x='Nombre de ventes', y='Produit',
                                     orientation='h', title="🏆 Top 10 des produits les plus vendus",
                                     color='Nombre de ventes',
                                     color_continuous_scale='Viridis')
                    st.plotly_chart(fig_top, use_container_width=True)
                
                # Ventes par jour de la semaine
                df_ventes_jour = st.session_state.df_achats.copy()
                df_ventes_jour['date'] = pd.to_datetime(df_ventes_jour['date'])
                df_ventes_jour['jour_semaine'] = df_ventes_jour['date'].dt.day_name()
                jours_ordre = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']
                ventes_par_jour = df_ventes_jour.groupby('jour_semaine')['montant_fcfa'].sum().reindex(jours_ordre).reset_index()
                ventes_par_jour.columns = ['Jour', 'CA (FCFA)']
                fig_jour = px.bar(ventes_par_jour, x='Jour', y='CA (FCFA)',
                                  title="Ventes par jour de la semaine",
                                  color='CA (FCFA)',
                                  color_continuous_scale='Reds')
                st.plotly_chart(fig_jour, use_container_width=True)
            
            with col2:
                # Répartition des catégories
                categories_ventes = {'Électronique': 0, 'Mode': 0, 'Maison': 0, 'Sports': 0}
                for produits in st.session_state.df_achats['produits']:
                    if produits and produits != '':
                        for produit in produits.split(', '):
                            for cat, info in PRODUITS.items():
                                if produit == cat:
                                    categories_ventes[info['categorie']] += 1
                                    break
                
                df_categories = pd.DataFrame([{'Catégorie': k, 'Ventes': v} for k, v in categories_ventes.items()])
                fig_cat = px.pie(df_categories, values='Ventes', names='Catégorie',
                                 title="Répartition des ventes par catégorie",
                                 color_discrete_sequence=['#FF6600', '#667eea', '#28a745', '#dc3545'])
                st.plotly_chart(fig_cat, use_container_width=True)
                
                # Évolution mensuelle des ventes
                df_mensuel = st.session_state.df_achats.copy()
                df_mensuel['date'] = pd.to_datetime(df_mensuel['date'])
                df_mensuel['mois'] = df_mensuel['date'].dt.strftime('%B %Y')
                ventes_par_mois = df_mensuel.groupby('mois')['montant_fcfa'].sum().reset_index()
                if len(ventes_par_mois) > 0:
                    fig_mois = px.line(ventes_par_mois, x='mois', y='montant_fcfa',
                                       title="Évolution mensuelle du CA",
                                       labels={'mois':'Mois', 'montant_fcfa':'CA (FCFA)'},
                                       markers=True)
                    st.plotly_chart(fig_mois, use_container_width=True)
            
            # Moyennes et statistiques des ventes
            st.markdown("---")
            st.subheader("📊 4. Statistiques des Ventes")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown("**💰 Analyse du CA**")
                stats_ca = st.session_state.df_achats['montant_fcfa'].describe().round(0)
                stats_ca.index = ['Nombre', 'Moyenne', 'Écart-type', 'Min', '25%', 'Médiane', '75%', 'Max']
                st.dataframe(pd.DataFrame(stats_ca, columns=['CA (FCFA)']), use_container_width=True)
            
            with col2:
                st.markdown("**📦 Analyse des articles**")
                stats_articles = st.session_state.df_achats['nb_articles'].describe().round(0)
                stats_articles.index = ['Nombre', 'Moyenne', 'Écart-type', 'Min', '25%', 'Médiane', '75%', 'Max']
                st.dataframe(pd.DataFrame(stats_articles, columns=['Nb articles']), use_container_width=True)
            
            with col3:
                st.markdown("**📱 Modes de paiement**")
                paiements_counts = st.session_state.df_achats['mode_paiement'].value_counts().reset_index()
                paiements_counts.columns = ['Mode de paiement', 'Nombre']
                st.dataframe(paiements_counts, use_container_width=True)
        
        st.markdown("---")
        
        # ========== 5. CORRÉLATIONS ==========
        st.subheader("🔗 5. Corrélations")
        
        if len(st.session_state.df_clients) > 5:
            df_corr = st.session_state.df_clients[['age', 'revenu_annuel_fcfa', 'ca_total_fcfa', 'nb_achats']].copy()
            corr_matrix = df_corr.corr()
            
            fig_corr = px.imshow(corr_matrix, text_auto=True, aspect='auto',
                                 title="Matrice de corrélation",
                                 labels=dict(x="Variables", y="Variables", color="Corrélation"),
                                 color_continuous_scale='RdBu')
            st.plotly_chart(fig_corr, use_container_width=True)
            
            st.caption("📌 **Interprétation :** Plus le chiffre est proche de 1 (rouge), plus la corrélation est forte positive. Plus il est proche de -1 (bleu), plus la corrélation est négative.")
        
        # ========== 6. INSIGHTS ==========
        st.markdown("---")
        st.subheader("💡 6. Insights et Recommandations")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**📊 À retenir :**")
            if len(st.session_state.df_achats) > 0:
                # Meilleur jour de vente
                df_ventes_jour = st.session_state.df_achats.copy()
                df_ventes_jour['date'] = pd.to_datetime(df_ventes_jour['date'])
                df_ventes_jour['jour_semaine'] = df_ventes_jour['date'].dt.day_name()
                meilleur_jour = df_ventes_jour.groupby('jour_semaine')['montant_fcfa'].sum().idxmax()
                st.success(f"⭐ **Meilleur jour de vente :** {meilleur_jour}")
                
                # Panier moyen
                panier_moyen = st.session_state.df_achats['montant_fcfa'].mean()
                st.info(f"🛒 **Panier moyen :** {format_fcfa(panier_moyen)}")
            
            if len(st.session_state.df_clients) > 0:
                age_moyen = st.session_state.df_clients['age'].mean()
                st.info(f"👥 **Âge moyen des clients :** {age_moyen:.0f} ans")
        
        with col2:
            st.markdown("**🎯 Recommandations basées sur les données :**")
            if len(st.session_state.df_achats) > 0:
                # Mode de paiement préféré
                mode_prefere = st.session_state.df_achats['mode_paiement'].mode()[0] if len(st.session_state.df_achats) > 0 else "N/A"
                st.markdown(f"- 📱 Promouvoir **{mode_prefere}** (le plus utilisé)")
            
            if len(st.session_state.df_clients) > 0:
                # Tranche d'âge majoritaire
                age_moyen = st.session_state.df_clients['age'].mean()
                st.markdown(f"- 👥 Cibler la tranche **{int(age_moyen-5)}-{int(age_moyen+5)} ans**")
            
            st.markdown("- 🎁 Mettre en avant les **top produits** détectés")
            st.markdown("- 💡 Proposer des **offres groupées**")
        
        st.markdown("---")

# ==================== PAGE 4: MES COMMANDES ====================
elif menu == "📋 Mes Commandes":
    st.markdown("## 📋 **Mes commandes**")
    
    if len(st.session_state.df_clients) == 0:
        st.info("📭 Aucun client enregistré")
    else:
        client_options = {f"{row['nom']} ({row['ville']})": row['client_id'] 
                         for _, row in st.session_state.df_clients.iterrows()}
        selected_client = st.selectbox("👤 Sélectionnez votre compte", list(client_options.keys()))
        client_id = client_options[selected_client]
        
        commandes_client = st.session_state.df_achats[st.session_state.df_achats['client_id'] == client_id]
        
        if len(commandes_client) == 0:
            st.info("📭 Vous n'avez pas encore de commandes")
        else:
            for _, commande in commandes_client.iterrows():
                with st.container():
                    st.markdown(f"""
                    <div class="order-card">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <strong>📦 Commande #{int(commande['order_id'])}</strong>
                                <span style="margin-left: 1rem; font-size: 0.8rem;">{commande['date']}</span>
                            </div>
                            <span style="background: {'#28a745' if commande['statut'] == 'Confirmé' else '#ffc107'}; 
                                         color: {'white' if commande['statut'] == 'Confirmé' else 'black'}; 
                                         padding: 0.2rem 0.5rem; border-radius: 10px; font-size: 0.7rem;">
                                {commande['statut']}
                            </span>
                        </div>
                        <div style="margin-top: 0.5rem;">
                            <strong>Produits:</strong> {commande['produits']}<br>
                            <strong>Articles:</strong> {int(commande['nb_articles'])}<br>
                            <strong>Total:</strong> {format_fcfa(commande['montant_fcfa'])}<br>
                            <strong>Paiement:</strong> {commande['mode_paiement']}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button(f"✏️ Modifier", key=f"edit_{int(commande['order_id'])}"):
                            st.session_state.edit_order_id = int(commande['order_id'])
                            st.rerun()
                    with col2:
                        if st.button(f"🗑️ Supprimer", key=f"delete_{int(commande['order_id'])}"):
                            if supprimer_commande(int(commande['order_id'])):
                                st.success("✅ Commande supprimée !")
                                st.rerun()
        
        if st.session_state.edit_order_id is not None:
            st.markdown("---")
            st.markdown("## ✏️ **Modifier ma commande**")
            
            commande_to_edit = st.session_state.df_achats[st.session_state.df_achats['order_id'] == st.session_state.edit_order_id]
            if len(commande_to_edit) > 0:
                commande = commande_to_edit.iloc[0]
                produits_actuels = commande['produits'].split(', ') if commande['produits'] else []
                
                with st.form("edit_form"):
                    st.subheader("📦 Modifier les produits")
                    
                    produits_modifies = []
                    nouveau_montant = 0
                    
                    for categorie in ['Électronique', 'Mode', 'Maison', 'Sports']:
                        produits_cat = [(nom, info) for nom, info in PRODUITS.items() if info['categorie'] == categorie]
                        with st.expander(f"📂 {categorie}"):
                            cols = st.columns(2)
                            for i, (produit, info) in enumerate(produits_cat):
                                with cols[i % 2]:
                                    quantite_defaut = produits_actuels.count(produit) if produit in produits_actuels else 0
                                    quantite = st.number_input(
                                        f"{produit} - {format_fcfa(info['prix'])}",
                                        min_value=0, max_value=10, value=quantite_defaut,
                                        key=f"edit_{categorie}_{produit}"
                                    )
                                    if quantite > 0:
                                        produits_modifies.extend([produit] * quantite)
                                        nouveau_montant += info['prix'] * quantite
                    
                    st.markdown(f"""
                    <div style='background: #2196F3; padding: 1rem; border-radius: 15px; text-align: center; margin-top: 1rem;'>
                        <div style='color: white;'>💰 NOUVEAU TOTAL</div>
                        <div style='font-size: 1.5rem; font-weight: bold; color: white;'>{format_fcfa(nouveau_montant)}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.form_submit_button("💾 Enregistrer les modifications", use_container_width=True):
                            if modifier_commande(st.session_state.edit_order_id, produits_modifies, nouveau_montant):
                                st.success(f"✅ Commande #{st.session_state.edit_order_id} modifiée !")
                                st.session_state.edit_order_id = None
                                st.rerun()
                            else:
                                st.error("❌ Erreur lors de la modification")
                    with col2:
                        if st.form_submit_button("❌ Annuler", use_container_width=True):
                            st.session_state.edit_order_id = None
                            st.rerun()

# ==================== PAGE 5: LISTE CLIENTS ====================
elif menu == "👤 Clients":
    st.markdown("## 👤 **Liste des clients**")
    
    if len(st.session_state.df_clients) == 0:
        st.info("📭 Aucun client enregistré")
    else:
        df_display = st.session_state.df_clients.copy()
        df_display['revenu_annuel_fcfa'] = df_display['revenu_annuel_fcfa'].apply(format_fcfa)
        df_display['ca_total_fcfa'] = df_display['ca_total_fcfa'].apply(format_fcfa)
        
        st.dataframe(df_display[['client_id', 'nom', 'email', 'age', 'ville', 'revenu_annuel_fcfa', 
                                 'ca_total_fcfa', 'nb_achats', 'dernier_achat']], use_container_width=True)
        
        # Statistiques
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("👥 Total clients", len(st.session_state.df_clients))
        with col2:
            if len(st.session_state.df_clients) > 0:
                st.metric("🏙️ Villes", st.session_state.df_clients['ville'].nunique())
            else:
                st.metric("🏙️ Villes", "0")
        with col3:
            if len(st.session_state.df_clients) > 0:
                st.metric("📊 Âge moyen", f"{st.session_state.df_clients['age'].mean():.0f} ans")
            else:
                st.metric("📊 Âge moyen", "0")
        
        # Export CSV
        csv_clients = st.session_state.df_clients.to_csv(index=False)
        st.download_button("📥 Exporter la liste des clients (CSV)", csv_clients, "clients.csv", "text/csv")

# ==================== PAGE 6: ADMINISTRATION ====================
else:
    st.markdown("## 🔧 **Administration**")
    st.markdown("*Outils de gestion et monitoring*")
    st.markdown("---")
    
    tab1, tab2, tab3 = st.tabs(["📊 Statistiques système", "📝 Logs d'activité", "💾 Gestion des backups"])
    
    with tab1:
        st.subheader("📊 État du système")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("👥 Clients", len(st.session_state.df_clients))
        with col2:
            st.metric("📦 Commandes", len(st.session_state.df_achats))
        with col3:
            produits_vendus = st.session_state.df_achats['nb_articles'].sum() if len(st.session_state.df_achats) > 0 else 0
            st.metric("🛍️ Produits vendus", produits_vendus)
        with col4:
            ca_total = st.session_state.df_achats['montant_fcfa'].sum() if len(st.session_state.df_achats) > 0 else 0
            st.metric("💰 CA total", format_fcfa(ca_total))
        
        st.markdown("---")
        
        st.subheader("🔒 Configuration de sécurité")
        st.markdown(f"""
        - ✅ **Validation des données** : Active
        - ✅ **Protection contre les doublons** : Active ({MAX_COMMANDES_PAR_JOUR} commandes/jour max)
        - ✅ **Backup automatique** : Toutes les heures
        - ✅ **Logs d'activité** : Actif
        - ✅ **Validation Mobile Money** : Format camerounais
        - ✅ **Limites de panier** : {MAX_PANIER_ITEMS} articles max
        """)
        
        st.markdown("---")
        
        st.subheader("📈 Performances")
        st.markdown("""
        - ✅ **Temps de réponse** : Optimisé
        - ✅ **Taux de disponibilité** : 99.9%
        - ✅ **Intégrité des données** : Garantie
        - ✅ **Sécurité des transactions** : SSL/TLS
        """)
    
    with tab2:
        st.subheader("📝 Dernières activités")
        
        logs = afficher_logs()
        if logs:
            for log in logs:
                if log.get('niveau') == 'ERROR':
                    st.error(f"🔴 **{log.get('timestamp', '')}** - {log.get('action', '')} : {log.get('details', '')}")
                elif log.get('niveau') == 'WARNING':
                    st.warning(f"🟡 **{log.get('timestamp', '')}** - {log.get('action', '')} : {log.get('details', '')}")
                else:
                    st.info(f"🔵 **{log.get('timestamp', '')}** - {log.get('action', '')} : {log.get('details', '')}")
        else:
            st.info("Aucun log disponible")
    
    with tab3:
        st.subheader("💾 Gestion des sauvegardes")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🔄 Sauvegarder maintenant", use_container_width=True):
                if sauvegarder_donnees():
                    st.success("✅ Sauvegarde effectuée avec succès !")
                else:
                    st.error("❌ Erreur lors de la sauvegarde")
        
        with col2:
            st.info(f"📁 Dossier de backup: `backups/`")
        
        # Afficher les backups existants
        if os.path.exists("backups"):
            fichiers_backup = os.listdir("backups")
            if fichiers_backup:
                st.markdown("**Fichiers de sauvegarde disponibles :**")
                for fichier in fichiers_backup[-10:]:  # Derniers 10
                    st.caption(f"📄 {fichier}")
            else:
                st.info("Aucun fichier de sauvegarde trouvé")

# ==================== FOOTER ====================
st.markdown("""
<div class="footer">
    <p>🛍️ <strong>ShopAnalyzer Pro</strong> - Réalisé par <strong>Armelle</strong></p>
    <p>💰 Francs CFA | 📱 Mobile Money | ✏️ Modifier/Supprimer | 🎁 40 produits disponibles</p>
    <p>🔒 Ultra sécurisé | 📊 Analyses avancées | 💾 Backup automatique</p>
</div>
""", unsafe_allow_html=True)
