# app.py
import streamlit as st
import pandas as pd
import json
import os
import hashlib
import time
from datetime import datetime
from io import BytesIO

# ---------- Configuration ----------
USERS_FILE = "users.json"            # contains users -> password_hash, file, school_code, school_name
ADDRESSES_FILE = "addresses.xlsm"    # shared (same as your desktop app)
SCHOOLS_FILE = "schools.xlsx"        # optional, used for display
# -----------------------------------

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
    if not info:
        return None
    return info.get("file", f"students_{username}.json")

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

def login_action(username, password):
    """
    Handles the login logic, including validation and state management.
    """
    if verify_user(username, password):
        st.session_state.logged_in = True
        st.session_state.username = username
        st.session_state.editing_record_id = None
        st.success(f"Καλωσήρθες, {username}!")
        time.sleep(1) # Gives the user a moment to see the message
        st.rerun()
    else:
        st.error("Λανθασμένος χρήστης ή κωδικός.")

def logout_action():
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.editing_record_id = None
    st.rerun()

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
    col1, col2 = st.columns([8,1])
    with col1:
        st.title(f"Students — {school_name} ({school_code})")
        st.write(f"Logged in as **{username}**")
    with col2:
        if st.button("Logout"):
            logout_action()

    st.markdown("---")

    # Load shared resources
    addresses_df = load_addresses()
    postal_codes = sorted(addresses_df["Τ.Κ."].dropna().unique().tolist())

    # Left: Form; Right: Records list
    left, right = st.columns([4,6])

    with left:
        st.subheader("Φόρμα Εγγραφής")
        # form inputs - mirror your Tkinter fields
        registry_number = st.text_input("Αρ. Μητρώου")
        last_name = st.text_input("Επώνυμο")
        first_name = st.text_input("Όνομα")
        father_name = st.text_input("Όνομα Πατέρα")
        sibling_school = st.text_input("Σχολείο Συμφοίτησης")
        notes = st.text_area("Παρατηρήσεις", height=120)

        # Address helpers: choose postal code then street (or vice versa)
        st.markdown("**Διεύθυνση**")
        postal_code = st.selectbox("ΤΚ", [""] + postal_codes, index=0)
        possible_streets = []
        if postal_code:
            possible_streets = sorted(addresses_df[addresses_df["Τ.Κ."] == postal_code]["ΟΔΟΣ"].dropna().unique().tolist())
        street = st.selectbox("Οδός", [""] + possible_streets, index=0)
        street_number = st.text_input("Αριθμός Οδού")
        city = ""
        if postal_code:
            city = addresses_df[addresses_df["Τ.Κ."] == postal_code]["ΠΟΛΗ"].dropna().unique()
            city = city[0] if len(city) else ""
        city = st.text_input("Πόλη / Περιοχή", value=city)

        if st.button("Αποθήκευση Εγγραφής"):
            # Basic validation
            required = [registry_number, last_name, first_name, father_name, street, street_number, postal_code, city]
            if not all(str(x).strip() for x in required):
                st.warning("Παρακαλώ συμπληρώστε όλα τα απαραίτητα πεδία.")
            else:
                records = read_records(student_file)
                # if editing existing record, update
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

                # Save
                write_records(student_file, records)
                st.success("Η εγγραφή αποθηκεύτηκε.")
                st.rerun()

        if st.button("Καθαρισμός Φόρμας"):
            st.session_state.editing_record_id = None
            st.rerun()

    with right:
        st.subheader("Αποθηκευμένες Εγγραφές")
        records = read_records(student_file)
        if not records:
            st.info("Δεν υπάρχουν εγγραφές για αυτόν τον χρήστη.")
        else:
            df = pd.DataFrame(records)
            # reorder columns if present
            cols_order = ["registry_number", "last_name", "first_name", "street", "street_number", "postal_code", "city", "sibling_school", "notes"]
            present_cols = [c for c in cols_order if c in df.columns] + [c for c in df.columns if c not in cols_order]
            st.dataframe(df[present_cols].rename(columns={
                "registry_number":"Αρ. Μητρώου","last_name":"Επώνυμο","first_name":"Όνομα",
                "street":"Οδός","street_number":"Αριθμός","postal_code":"ΤΚ","city":"Πόλη / Περιοχή",
                "sibling_school":"Σχολείο Συμφοίτησης","notes":"Παρατηρήσεις"
            }), height=400)

            # Select record for editing or deletion
            rec_map = {f"{r.get('registry_number','')} — {r.get('last_name','')} {r.get('first_name','')}": r.get('id') for r in records}
            chosen = st.selectbox("Επιλέξτε εγγραφή για Επεξεργασία / Διαγραφή", [""] + list(rec_map.keys()))
            if chosen:
                rec_id = rec_map[chosen]
                rec = next((r for r in records if str(r.get("id")) == str(rec_id)), None)
                if rec:
                    st.markdown("**Επιλογές:**")
                    c1, c2 = st.columns(2)
                    if c1.button("Φόρτωση για Επεξεργασία"):
                        # Pre-populate by setting session var and re-rendering (simplest approach: store record to st.session_state)
                        st.session_state.editing_record_id = rec_id
                        # Set up a mechanism to prefill form fields via query params or rerun with temp storage.
                        # Simpler: write temp file or store in session_state
                        st.session_state.prefill = rec
                        st.rerun()
                    if c2.button("Διαγραφή"):
                        if st.confirm("Είστε βέβαιοι ότι θέλετε να διαγράψετε την εγγραφή;"):
                            records = [r for r in records if str(r.get("id")) != str(rec_id)]
                            write_records(student_file, records)
                            st.success("Η εγγραφή διαγράφηκε.")
                            st.rerun()

            # Export button
            x1, x2 = st.columns([3,1])
            with x1:
                if st.button("Εξαγωγή σε Excel"):
                    data = export_to_excel_bytes(records)
                    st.download_button("Κατέβασε Excel", data=data, file_name=f"{school_code}_{username}_students.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # Prefill handling: if user clicked load for edit, populate the left form using st.session_state.prefill
    if st.session_state.get("prefill"):
        rec = st.session_state.pop("prefill")
        # Because Streamlit doesn't allow direct programmatic setting of widget values easily without experimental reruns,
        # we use an info message instructing the user how to fill fields — alternatively in production you'd use forms with key and set values.
        st.info("Η εγγραφή έχει φορτωθεί για επεξεργασία. Αντιγράψτε/επικολλήστε τα πεδία στο αριστερό έντυπο (το UI μπορεί να γίνει πιο προ-γεμισμένο σε επόμενη βελτίωση).")
        st.json(rec)

# ---------- Entry ----------
def app():
    st.sidebar.title("Navigation")
    if st.session_state.logged_in:
        st.sidebar.write(f"User: **{st.session_state.username}**")
        if st.sidebar.button("Logout"):
            logout_action()
        st.sidebar.markdown("---")
        st.sidebar.info("Shared files: addresses.xlsx, schools.xlsx (put them in the app folder).")
        main_app()
    else:
        show_login()

if __name__ == "__main__":
    app()
