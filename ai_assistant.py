
import os
import requests
import streamlit as st


# ---------------------------------
# Configuration
# ---------------------------------

API_URL = "https://api.prod.adaptionlabs.ai/api/v1/responses"

def get_secret(name):
    try:
        return st.secrets.get(name, os.getenv(name, ""))
    except Exception:
        return os.getenv(name, "")


def get_api_key():
    return get_secret("ADAPTION_API_KEY")


def get_model_id():
    return get_secret("ADAPTION_MODEL_ID")


def assistant_is_configured():
    return bool(get_api_key() and get_model_id())


# ---------------------------------
# MediScan AI Assistant
# ---------------------------------

def ask_assistant(question):

    api_key = get_api_key()
    model_id = get_model_id()

    if not api_key or not model_id:
        return (
            "AI connection is not configured. "
            "Please check your Streamlit Secrets."
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model_id,
        "instructions": (
            "You are MediScan AI, a medical laboratory report "
            "explanation assistant. Explain HbA1c, lipid profiles, "
            "liver function and other laboratory results in simple "
            "language. Explain abnormal values carefully. "
            "Never diagnose or prescribe treatment. "
            "Encourage users to consult qualified healthcare "
            "professionals."
        ),
        "input": str(question),
        "temperature": 0.3,
        "max_output_tokens": 800
    }

    try:
        response = requests.post(
            API_URL,
            headers=headers,
            json=payload,
            timeout=90
        )

        response.raise_for_status()
        data = response.json()

        # Extract response text
        for item in data.get("output", []):
            if item.get("type") == "message":
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        return content.get("text", "")

        return "The AI returned no readable response."

    except requests.exceptions.Timeout:
        return "AI request timed out. Please try again."

    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response else "Unknown"
        details = (
            e.response.text[:1000]
            if e.response is not None
            else str(e)
        )
        return f"Adaption API Error ({status}): {details}"

    except requests.exceptions.RequestException as e:
        return f"Connection Error: {str(e)}"

    except Exception as e:
        return f"Unexpected Error: {str(e)}"


# ---------------------------------
# Test Adaption API Connection
# ---------------------------------

def test_adaption_connection():

    api_key = get_api_key()

    if not api_key:
        return {"error": "API key is missing."}

    url = "https://api.prod.adaptionlabs.ai/api/v1/models"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=30
        )

        return {
            "status": response.status_code,
            "result": response.text[:3000]
        }

    except requests.exceptions.Timeout:
        return {"error": "API request timed out."}

    except requests.exceptions.RequestException as e:
        return {"error": str(e)}

    except Exception as e:
        return {"error": str(e)}
