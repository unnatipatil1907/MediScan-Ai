import torch
from transformers import AutoProcessor, AutoModelForMultimodalLM
from peft import PeftModel

BASE_MODEL = "Qwen/Qwen3.5-2B"
ADAPTER_PATH = "trained_model"

_model = None
_processor = None

def assistant_is_configured():
    return True

def load_model():
    global _model, _processor

    if _model is None:
        print("Loading MediScan trained AI model...")
        _processor = AutoProcessor.from_pretrained(BASE_MODEL)

        base = AutoModelForMultimodalLM.from_pretrained(
            BASE_MODEL,
            dtype="auto",
            low_cpu_mem_usage=True
        )

        _model = PeftModel.from_pretrained(base, ADAPTER_PATH)
        _model.eval()
        print("MediScan trained AI model loaded!")

    return _model, _processor

def ask_assistant(question):
    try:
        model, processor = load_model()

        messages = [{
            "role": "user",
            "content": [{
                "type": "text",
                "text": (
                    "You are MediScan AI, an assistant that explains medical "
                    "report information in simple language. Explain results "
                    "carefully, do not diagnose or prescribe medicines, and "
                    "recommend discussing concerning results with a qualified "
                    "healthcare professional.\n\n"
                    + str(question)
                )
            }]
        }]

        inputs = processor.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt"
        )

        with torch.no_grad():
            outputs = model.generate(
    **inputs,
    max_new_tokens=100,
    do_sample=False,
    use_cache=True
)

        answer = processor.decode(
            outputs[0][inputs["input_ids"].shape[-1]:],
            skip_special_tokens=True
        )
        return answer.strip()

    except Exception as e:
        return f"AI loading or response error: {e}"
