# app.py (fixed)
import streamlit as st
import pandas as pd
import json
import os
import hashlib
import time
from datetime import datetime
from io import BytesIO
import shutil

# ---------- Paths & Configuration ----------
# Base directory of this file (read-only on Streamlit Cloud)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Read-only bundled data dir (inside the repo)
READONLY_DATA_DIR = os.path.join(BASE_DIR, "data")

# Use the specified writable directory for data storage
WRITE_DATA_DIR = "/data"

# App resources (read-only assets live next to the script)
USERS_FILE = os.path.join(BASE_DIR, "users.json")            # contains users -> password_hash, file, school_code, school_name
ADDRESSES_FILE = os.path.join(BASE_DIR, "addresses.xlsx")    # shared (same as your desktop app)
SCHOOLS_FILE = os.path.join(BASE_DIR, "schools.xlsx")        # optional, used for display
# -------------------------------------------

st.set_page_config(page_title="Student Registration (Web)", layout="wide")

# ----------------- Utilities -----------------
def hash_password(plain: str) -> str:
    """Return sha256 hex digest of password (simple)."""
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()

def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def verify_user(username, password):
    users = load_users()
    user = users.get(username)
    if not user:
        return False
    return user.get("password_hash") == hash_password(password)

def get_user_info(username):
    users = load_users()
    return users.get(username)

def student_file_for(username):
    info = get_user_info(username)
    filename = info.get("file", f"students_{username}.json") if info else f"students_{username}.json"

    # Ensure writable directory exists (prefer /tmp/data on Streamlit Cloud)
    target_dir = WRITE_DATA_DIR
    try:
        os.makedirs(target_dir, exist_ok=True)
    except Exception:
        # Fallback to read-only repo data folder (reading only)
        target_dir = READONLY_DATA_DIR

    target_path = os.path.join(target_dir, filename)

    # If target file does not exist yet but a bundled copy exists, copy it once
    bundled_path = os.path.join(READONLY_DATA_DIR, filename)
    try:
        if not os.path.exists(target_path) and os.path.exists(bundled_path):
            os.makedirs(os.path.dirname(target_path) or ".", exist_ok=True)
            shutil.copyfile(bundled_path, target_path)
    except Exception:
        # Ignore copy issues; reading will still try target_path
        pass

    return target_path

def read_records(filepath):
    records = []
    if not os.path.exists(filepath):
        return records
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except Exception:
                        continue
    except Exception:
        return []
    return records

def write_records(filepath, records):
    tmp = filepath + ".tmp"
    os.makedirs(os.path.dirname(os.path.abspath(filepath)) or ".", exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        for r in records:
            json.dump(r, f, ensure_ascii=False)
            f.write("\n")
    os.replace(tmp, filepath)

def export_to_excel_bytes(records):
    df = pd.DataFrame(records)
    with BytesIO() as b:
        with pd.ExcelWriter(b, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Students")
        return b.getvalue()

def load_addresses():
    if not os.path.exists(ADDRESSES_FILE):
        return pd.DataFrame(columns=["Τ.Κ.", "ΟΔΟΣ", "ΠΟΛΗ"])
    df = pd.read_excel(ADDRESSES_FILE, dtype=str, engine="openpyxl")
    for col in df.columns:
        df[col] = df[col].astype(str).fillna("").str.strip()
    return df

# -------------- Session helpers --------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = None
if "editing_record_id" not in st.session_state:
    st.session_state.editing_record_id = None
if "prefill" not in st.session_state:
    st.session_state.prefill = {}

def login_action(username, password):
    if verify_user(username, password):
        st.session_state.logged_in = True
        st.session_state.username = username
        st.session_state.editing_record_id = None
        st.success(f"Καλωσήρθες, {username}!")
    else:
        st.error("Λανθασμένος χρήστης ή κωδικός.")

def logout_action():
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.editing_record_id = None
    st.experimental_rerun()

# ------------------ UI ------------------
def show_login():
    st.title("Student Registration — Login")
    st.markdown("Enter your username and password to access your school's students.")
    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
        if submitted:
            login_action(username.strip(), password)

    st.markdown("---")
    st.info("If you don't have an account yet, create an entry in `users.json` (see README).")

def main_app():
    username = st.session_state.username
    user_info = get_user_info(username)
    if not user_info:
        st.error("User info missing. Please contact admin.")
        return

    school_name = user_info.get("school_name", "Unknown School")
    school_code = user_info.get("school_code", "")
    student_file = student_file_for(username)

    # Header
    col1, col2 = st.columns([8, 1])
    with col1:
        st.title(f"Students — {school_name} ({school_code})")
        st.write(f"Logged in as **{username}**")
        # Show where the student data is stored (useful on Streamlit Cloud)
        st.caption(f"Data file: {student_file}")
    with col2:
        if st.button("Logout"):
            logout_action()

    st.markdown("---")

    # Load shared resources
    addresses_df = load_addresses()
    postal_codes = sorted(addresses_df["Τ.Κ."].dropna().unique().tolist())

    # Left: Form; Right: Records list
    left, right = st.columns([4, 6])

    with left:
        st.subheader("Φόρμα Εγγραφής")
        with st.form("entry_form", clear_on_submit=False):
            prefill_rec = st.session_state.prefill
            
            registry_number = st.text_input("Αρ. Μητρώου", value=prefill_rec.get("registry_number", ""), key="registry_number_input")
            last_name = st.text_input("Επώνυμο", value=prefill_rec.get("last_name", ""), key="last_name_input")
            first_name = st.text_input("Όνομα", value=prefill_rec.get("first_name", ""), key="first_name_input")
            father_name = st.text_input("Όνομα Πατέρα", value=prefill_rec.get("father_name", ""), key="father_name_input")
            sibling_school = st.text_input("Σχολείο Συμφοίτησης", value=prefill_rec.get("sibling_school", ""), key="sibling_school_input")
            notes = st.text_area("Παρατηρήσεις", height=120, value=prefill_rec.get("notes", ""), key="notes_input")

            st.markdown("**Διεύθυνση**")

            # Corrected logic for address fields
            postal_code_options = [""] + postal_codes
            postal_code_idx = postal_code_options.index(prefill_rec.get("postal_code", "")) if prefill_rec.get("postal_code") in postal_code_options else 0
            postal_code = st.selectbox("ΤΚ", postal_code_options, index=postal_code_idx, key="postal_code_selectbox")
            
            # --- Dynamically update street and city based on postal code selection ---
            possible_streets = []
            city_value = ""
            if postal_code:
                subset = addresses_df[addresses_df["Τ.Κ."] == postal_code]
                possible_streets = sorted(subset["ΟΔΟΣ"].dropna().unique().tolist())
                cities = subset["ΠΟΛΗ"].dropna().unique()
                if len(cities):
                    city_value = cities[0]

            street_options = [""] + possible_streets
            street_idx = street_options.index(prefill_rec.get("street", "")) if prefill_rec.get("street") in street_options else 0
            street = st.selectbox("Οδός", street_options, index=street_idx, key="street_selectbox")
            
            street_number = st.text_input("Αριθμός Οδού", value=prefill_rec.get("street_number", ""), key="street_number_input")
            city = st.text_input("Πόλη / Περιοχή", value=prefill_rec.get("city", city_value), key="city_input")
            # --- End of dynamic updates ---

            submitted = st.form_submit_button("Αποθήκευση Εγγραφής")

            if submitted:
                # The logic for saving/updating goes here
                required = [registry_number, last_name, first_name, father_name, street, street_number, postal_code, city]
                if not all(str(x).strip() for x in required):
                    st.warning("Παρακαλώ συμπληρώστε όλα τα απαραίτητα πεδία.")
                else:
                    records = read_records(student_file)
                    if st.session_state.editing_record_id:
                        rec_id = st.session_state.editing_record_id
                        updated = False
                        for i, rec in enumerate(records):
                            if str(rec.get("id")) == str(rec_id):
                                records[i] = {
                                    "id": rec_id,
                                    "registry_number": registry_number.strip(),
                                    "last_name": last_name.strip(),
                                    "first_name": first_name.strip(),
                                    "father_name": father_name.strip(),
                                    "sibling_school": sibling_school.strip(),
                                    "notes": notes.strip(),
                                    "school": school_name,
                                    "school_code": school_code,
                                    "street": street.strip(),
                                    "street_number": street_number.strip(),
                                    "postal_code": postal_code.strip(),
                                    "city": city.strip(),
                                    "last_modified": datetime.now().isoformat()
                                }
                                updated = True
                                break
                        if not updated:
                            st.warning("Η εγγραφή προς επεξεργασία δεν βρέθηκε. Θα δημιουργηθεί νέα.")
                            rec_id = str(int(time.time()))
                            records.append({
                                "id": rec_id,
                                "registry_number": registry_number.strip(),
                                "last_name": last_name.strip(),
                                "first_name": first_name.strip(),
                                "father_name": father_name.strip(),
                                "sibling_school": sibling_school.strip(),
                                "notes": notes.strip(),
                                "school": school_name,
                                "school_code": school_code,
                                "street": street.strip(),
                                "street_number": street_number.strip(),
                                "postal_code": postal_code.strip(),
                                "city": city.strip(),
                                "last_modified": datetime.now().isoformat()
                            })
                        st.session_state.editing_record_id = None
                    else:
                        rec_id = str(int(time.time()))
                        records.append({
                            "id": rec_id,
                            "registry_number": registry_number.strip(),
                            "last_name": last_name.strip(),
                            "first_name": first_name.strip(),
                            "father_name": father_name.strip(),
                            "sibling_school": sibling_school.strip(),
                            "notes": notes.strip(),
                            "school": school_name,
                            "school_code": school_code,
                            "street": street.strip(),
                            "street_number": street_number.strip(),
                            "postal_code": postal_code.strip(),
                            "city": city.strip(),
                            "created_at": datetime.now().isoformat()
                        })
                    write_records(student_file, records)
                    st.success("Η εγγραφή αποθηκεύτηκε.")
                    st.session_state.prefill = {}  # Clear prefill data
                    st.experimental_rerun()

        if st.button("Καθαρισμός Φόρμας"):
            st.session_state.editing_record_id = None
            st.session_state.prefill = {}
            st.experimental_rerun()

    with right:
        st.subheader("Αποθηκευμένες Εγγραφές")
        records = read_records(student_file)
        if not records:
            st.info("Δεν υπάρχουν εγγραφές για αυτόν τον χρήστη.")
        else:
            df = pd.DataFrame(records)
            cols_order = ["registry_number", "last_name", "first_name", "street", "street_number", "postal_code", "city", "sibling_school", "notes"]
            present_cols = [c for c in cols_order if c in df.columns] + [c for c in df.columns if c not in cols_order]
            st.dataframe(df[present_cols].rename(columns={
                "registry_number":"Αρ. Μητρώου","last_name":"Επώνυμο","first_name":"Όνομα",
                "street":"Οδός","street_number":"Αριθμός","postal_code":"ΤΚ","city":"Πόλη / Περιοχή",
                "sibling_school":"Σχολείο Συμφοίτησης","notes":"Παρατηρήσεις"
            }), height=400)

            rec_map = {f"{r.get('registry_number','')} — {r.get('last_name','')} {r.get('first_name','')}": r.get('id') for r in records}
            chosen = st.selectbox("Επιλέξτε εγγραφή για Επεξεργασία / Διαγραφή", [""] + list(rec_map.keys()))
            if chosen:
                rec_id = rec_map[chosen]
                rec = next((r for r in records if str(r.get("id")) == str(rec_id)), None)
                if rec:
                    st.markdown("**Επιλογές:**")
                    c1, c2 = st.columns(2)
                    if c1.button("Φόρτωση για Επεξεργασία"):
                        st.session_state.editing_record_id = rec_id
                        st.session_state.prefill = rec
                        st.experimental_rerun()
                    if c2.button("Διαγραφή"):
                        st.session_state.to_delete_id = rec_id

                if "to_delete_id" in st.session_state and st.session_state.to_delete_id == rec_id:
                    st.warning("Είστε βέβαιοι ότι θέλετε να διαγράψετε την εγγραφή;")
                    d1, d2 = st.columns(2)
                    if d1.button("Ναι, Διαγραφή"):
                        records = [r for r in records if str(r.get("id")) != str(rec_id)]
                        write_records(student_file, records)
                        st.success("Η εγγραφή διαγράφηκε.")
                        st.session_state.pop("to_delete_id")
                        st.experimental_rerun()
                    if d2.button("Άκυρο"):
                        st.session_state.pop("to_delete_id")
                        st.info("Η διαγραφή ακυρώθηκε.")

            x1, x2 = st.columns([3, 1])
            with x1:
                if st.button("Εξαγωγή σε Excel"):
                    data = export_to_excel_bytes(records)
                    st.download_button("Κατέβασε Excel", data=data, file_name=f"{school_code}_{username}_students.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    
# ---------- Entry ----------
def app():
    st.sidebar.title("Navigation")
    if st.session_state.logged_in:
        st.sidebar.write(f"User: **{st.session_state.username}**")
        if st.sidebar.button("Logout"):
            logout_action()
        st.sidebar.markdown("---")
        st.sidebar.info("Shared files: addresses.xlsx, schools.xlsx (put them in the app folder).")

        st.sidebar.markdown("---")
        if st.sidebar.button("Help / Οδηγίες"):
            st.sidebar.info("""
            **Οδηγίες Χρήσης**
            - Συμπληρώστε τη φόρμα αριστερά και πατήστε *Αποθήκευση Εγγραφής*.
            - Οι εγγραφές φαίνονται δεξιά.
            - Επιλέξτε εγγραφή για *Επεξεργασία* ή *Διαγραφή*.
            - Χρησιμοποιήστε το *Εξαγωγή σε Excel* για να κατεβάσετε όλα τα δεδομένα.
            """)
        main_app()
    else:
        show_login()

if __name__ == "__main__":
    app()