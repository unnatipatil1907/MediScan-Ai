
import os
import requests
import streamlit as st


def get_secret(name):
    return st.secrets.get(name, os.getenv(name, ""))


def assistant_is_configured():
    return bool(
        get_secret("ADAPTION_API_KEY")
        and get_secret("ADAPTION_MODEL_ID")
    )


def ask_assistant(question):
    api_key = get_secret("ADAPTION_API_KEY")
    model_id = get_secret("ADAPTION_MODEL_ID")

    if not api_key or not model_id:
        return (
            "AI connection is not configured. "
            "Please configure the Adaption API key and model ID."
        )

    url = "https://api.prod.adaptionlabs.ai/api/v1/responses"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model_id,
        "instructions": (
            "You are MediScan AI, a medical laboratory report "
            "explanation assistant. Explain HbA1c, lipid profile, "
            "liver function and other laboratory results in simple "
            "language. Never diagnose or prescribe treatment. "
            "Encourage users to consult qualified healthcare "
            "professionals."
        ),
        "input": question,
        "temperature": 0.3,
        "max_output_tokens": 800
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=90
        )

        response.raise_for_status()
        data = response.json()

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
        details = e.response.text[:1000] if e.response else str(e)
        return f"Adaption API Error ({status}): {details}"

    except requests.exceptions.RequestException as e:
        return f"Connection Error: {str(e)}"

    except Exception as e:
        return f"Unexpected Error: {str(e)}"


def test_adaption_connection():
    api_key = get_secret("ADAPTION_API_KEY")

    url = "https://api.prod.adaptionlabs.ai/api/v1/models"

    try:
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30
        )

        if response.status_code == 200:
            return response.json()

        return {
            "status": response.status_code,
            "error": response.text[:1000]
        }

    except Exception as e:
        return {"error": str(e)}
