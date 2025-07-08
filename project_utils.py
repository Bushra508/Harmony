import os
import pandas as pd
import bcrypt
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import joblib
import streamlit as st
import requests
from dotenv import load_dotenv
import re
from datetime import datetime
from scipy.special import expit  # sigmoid
import pickle

# --- Load environment variables ---
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# --- Load ML Models ---
model_depression = joblib.load("models/depression_model.pkl")
vectorizer_depression = joblib.load("models/depression_vectorizer.pkl")
model_schizo = joblib.load("models/schizophrenia_model.pkl")
vectorizer_schizo = joblib.load("models/schizophrenia_vectorizer.pkl")

def is_valid_email(email: str) -> bool:
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None

# --- Auth Logic ---
def login_screen():

    login_tab, register_tab = st.tabs(["Log In", "Register"])

    with login_tab:
        st.write("Please enter your login credentials.")
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")

        if st.button("Log In"):
            user = get_user_by_email(email)
            handle_login(user, email, password)

    with register_tab:
        st.write("Create a new account.")
        name = st.text_input("Full Name", key="register_name")
        email = st.text_input("Email", key="register_email")
        password = st.text_input("Password", type="password", key="register_password")
        confirm_password = st.text_input("Confirm Password", type="password", key="register_confirm")

        if st.button("Register"):
            if not name or not email or not password:
                st.warning("Please fill out all fields to register.")
                return
            if password != confirm_password:
                st.warning("The passwords do not match!")
                return

            user = get_user_by_email(email)
            handle_register(user, email, name, password, confirm_password)

# --- Helper Functions ---

def get_user_by_email(email):
    try:
        url = f"{SUPABASE_URL}/rest/v1/Users?email=eq.{email}&select=*"
        res = requests.get(url, headers=HEADERS)
        data = res.json()
        return data[0] if data else None
    except Exception as e:
        st.error(f"Failed to get user: {e}")
        return None

def handle_login(user, email, password):
    if not is_valid_email(email):
        st.warning("Please enter a valid email address.")
        return
    if not user:
        st.error("No account found with this email.")
        return
    if bcrypt.checkpw(password.encode(), user["password"].encode()):
        st.session_state["email"] = user["email"]
        st.session_state["name"] = user["name"]
        st.session_state["user_id"] = user["id"]
        st.rerun()
    else:
        st.error("Incorrect password. Please try again.")

def handle_register(user, email, name, password, confirm_password):
    if not is_valid_email(email):
        st.warning("Please enter a valid email address.")
        return
    if not email or not password:
        st.warning("Please enter both email and password.")
        return
    if user:
        st.warning("An account with this email already exists. Please login instead")
        return
    if password != confirm_password:
        st.warning("Passwords do not match. Try again.")
        return

    hashed_pw = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    new_user = {
        "email": email,
        "name": name,
        "password": hashed_pw
    }

    try:
        res = requests.post(f"{SUPABASE_URL}/rest/v1/Users", json=new_user, headers=HEADERS)
        if res.status_code == 201:
            st.success("Account created successfully! You can now log in.")
        else:
            st.error(f"Registration failed: {res.text}")
    except Exception as e:
        st.error(f"Failed to register: {str(e)}")

def predict_label_depression(text):
    if text.strip() == "":
        return 0.0, "Unknown"
    vec = vectorizer_depression.transform([text])
    pred = model_depression.predict(vec)[0]
    probs = model_depression.predict_proba(vec)[0]
    confidence_score = str(round(np.max(probs)*100,2))
    prob_depressed = round(float(probs[1])*100,2)
    to_be_printed_dep = (f"{confidence_score} % confident Depressed" if pred == 1 else f"{confidence_score} % confident Not Depressed")
    return prob_depressed, to_be_printed_dep

def predict_label_schizo(text):
    if text.strip() == "":
        return 0.0, "Unknown"
    vec = vectorizer_schizo.transform([text])
    pred = model_schizo.predict(vec)[0]
    probs = model_schizo.predict_proba(vec)[0]
    confidence_score = str(round(np.max(probs)*100,2))
    prob_schizo = round(float(probs[1])*100,2)
    to_be_printed_schizo = (f"{confidence_score} % confident Schizophrenic" if pred == 1 else f"{confidence_score} % confident Not Schizophrenic")
    return prob_schizo, to_be_printed_schizo

def predict_both(text):
    depression, to_be_printed_dep = predict_label_depression(text)
    schizo, to_be_printed_schizo = predict_label_schizo(text)
    msg = to_be_printed_dep + " and " + to_be_printed_schizo
    return (depression, schizo, msg)

def preview(text, lines=2):
    lines_list = text.splitlines()
    short = "\n".join(lines_list[:lines])
    return short + ("..." if len(lines_list) > lines else "")

def save_note_to_supabase(title, body, pred_depression, pred_schizophrenia, prediction_message):
    new_note = {
        "date_time": datetime.now().isoformat(),
        "title": title,
        "body": body,
        "pred_depression": pred_depression,
        "pred_schizophrenia": pred_schizophrenia,
        "prediction_message": prediction_message,
        "user_id": st.session_state["user_id"]
    }
    try:
        res = requests.post(f"{SUPABASE_URL}/rest/v1/Journals", json=new_note, headers=HEADERS)
    except Exception as e:
        st.error(f"Failed to save note: {e}")

def get_notes_from_supabase():
    try:
        url = f"{SUPABASE_URL}/rest/v1/Journals?user_id=eq.{st.session_state['user_id']}&order=date_time.desc"
        res = requests.get(url, headers=HEADERS)
        if res.status_code == 200:
            return pd.DataFrame(res.json())
        else:
            st.error(f"Failed to fetch notes: {res.text}")
            return pd.DataFrame()
    except Exception as e:
        st.error(f"Error loading notes: {e}")
        return pd.DataFrame()

def delete_note_from_supabase(note_id):
    try:
        url = f"{SUPABASE_URL}/rest/v1/Journals?id=eq.{note_id}"
        res = requests.delete(url, headers=HEADERS)
    except Exception as e:
        st.error(f"Failed to delete note: {e}")

def show_analysis_depression():
    try:
        url = f"{SUPABASE_URL}/rest/v1/Journals?user_id=eq.{st.session_state['user_id']}&select=date_time,pred_depression&order=date_time"
        res = requests.get(url, headers=HEADERS)
        data = res.json()
        if not data:
            st.info("No data available for depression analysis.")
            return
        df = pd.DataFrame(data)
        df['date_time'] = pd.to_datetime(df['date_time'])

        plt.figure(figsize=(9, 4))
        plt.plot(df['date_time'], df['pred_depression'], marker='o', linestyle='-', color='blue')
        plt.xlabel('Date & Time')
        plt.ylabel('Depression Probability')
        plt.title('Depression Analysis Over Time')
        plt.grid(True)
        plt.xticks(rotation=45)
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%d %B %y, %H:%M'))
        plt.tight_layout()
        st.pyplot(plt)

    except Exception as e:
        st.error(f"Error loading depression analysis: {e}")

def show_analysis_schizo():
    try:
        url = f"{SUPABASE_URL}/rest/v1/Journals?user_id=eq.{st.session_state['user_id']}&select=date_time,pred_schizophrenia&order=date_time"
        res = requests.get(url, headers=HEADERS)
        data = res.json()
        if not data:
            st.info("No data available for schizophrenia analysis.")
            return
        df = pd.DataFrame(data)
        df['date_time'] = pd.to_datetime(df['date_time'])

        plt.figure(figsize=(9, 4))
        plt.plot(df['date_time'], df['pred_schizophrenia'], marker='o', linestyle='-', color='blue')
        plt.xlabel('Date & Time')
        plt.ylabel('Schizophrenia Probability')
        plt.title('Schizophrenia Analysis Over Time')
        plt.grid(True)
        plt.xticks(rotation=45)
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%d %B %y, %H:%M'))
        plt.tight_layout()
        st.pyplot(plt)

    except Exception as e:
        st.error(f"Error loading schizophrenia analysis: {e}")
