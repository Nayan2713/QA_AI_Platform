# backend/config/llm_config.py
import logging
import urllib.request
import json
import socket
import time
from urllib.parse import urlparse
from django.conf import settings

logger = logging.getLogger(__name__)


def is_port_open(url, timeout=0.5):
    """
    Check if a TCP port is open. Uses 0.5s timeout to minimise
    the delay when both Ollama and LM Studio are offline.
    """
    try:
        parsed = urlparse(url)
        host = parsed.hostname or 'localhost'
        port = parsed.port
        if port is None:
            port = 80 if parsed.scheme == 'http' else 443
        with socket.create_connection((host, port), timeout=timeout) as _:
            return True
    except Exception:
        return False


_ollama_models_cache = None
_ollama_cache_timestamp = 0
OLLAMA_CACHE_TTL = 60  # Cache available models for 60 seconds


def get_available_ollama_models(base_url):
    global _ollama_models_cache, _ollama_cache_timestamp
    current_time = time.time()
    if _ollama_models_cache is not None and (current_time - _ollama_cache_timestamp) < OLLAMA_CACHE_TTL:
        return _ollama_models_cache

    try:
        url = f"{base_url}/api/tags"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=2.0) as response:
            data = json.loads(response.read().decode())
            models = [model['name'] for model in data.get('models', [])]
            _ollama_models_cache = models
            _ollama_cache_timestamp = current_time
            return models
    except Exception:
        return []


def _resolve_ollama_model(model_name, available_models):
    """Pick the best available Ollama model, falling back gracefully."""
    if not available_models:
        return model_name
    clean_model = model_name.split(':')[0]
    if any(clean_model in m for m in available_models):
        return model_name
    logger.warning(f"Model '{model_name}' not in Ollama. Available: {available_models}")
    for m in available_models:
        if 'qwen' in m:
            return m
    return available_models[0]


def _is_valid_openai_key(key):
    """
    Returns True only if the key looks like a real OpenAI API key.
    Prevents the infinite-retry loop when OPENAI_API_KEY is None/empty.
    """
    if not key:
        return False
    key = str(key).strip()
    if not key:
        return False
    if (key.startswith('sk-') or key.startswith('sk-proj-')) and len(key) >= 40:
        return True
    logger.warning(
        "OPENAI_API_KEY looks invalid (doesn't start with 'sk-' or is too short). "
        "Skipping Cloud OpenAI to avoid hanging retries."
    )
    return False


def get_llm(application=None, model_choice=None):
    """
    Returns an LLM instance in priority order, or forced based on model_choice:
      - 'ollama': Local Ollama
      - 'openai': Cloud OpenAI (gpt-4o-mini)
      - 'groq': Groq (llama-3.3-70b-versatile)
      - 'auto' / None: Priority order (Ollama -> Local Gateway -> Cloud OpenAI)
    """
    # ---- Forced Choices ----
    if model_choice in ('ollama', 'ollama_qwen'):
        try:
            ollama_api_url = getattr(settings, 'OLLAMA_API_URL', 'http://localhost:11434/api/generate')
            base_url = ollama_api_url.split('/api')[0]
            if is_port_open(base_url, timeout=0.5):
                from langchain_ollama import ChatOllama
                model_name = getattr(settings, 'OLLAMA_MODEL', 'qwen2.5:7b')
                available_models = get_available_ollama_models(base_url)
                model_name = _resolve_ollama_model(model_name, available_models)
                logger.info(f"Forced Ollama (Qwen model): base_url={base_url}, model={model_name}")
                return ChatOllama(
                    model=model_name,
                    base_url=base_url,
                    timeout=30,
                    temperature=0.2,
                    num_predict=4096,
                    num_ctx=8192,
                )
            else:
                raise RuntimeError(f"Ollama port not open at {base_url}.")
        except Exception as e:
            logger.error(f"Forced Ollama (Qwen) instantiation failed: {e}")
            raise RuntimeError(f"Failed to initialize local Ollama model: {e}")

    elif model_choice == 'ollama_groq':
        try:
            ollama_api_url = getattr(settings, 'OLLAMA_API_URL', 'http://localhost:11434/api/generate')
            base_url = ollama_api_url.split('/api')[0]
            if is_port_open(base_url, timeout=0.5):
                from langchain_ollama import ChatOllama
                logger.info(f"Forced Ollama (Groq model): base_url={base_url}, model=groq")
                return ChatOllama(
                    model="groq",
                    base_url=base_url,
                    timeout=30,
                    temperature=0.2,
                    num_predict=4096,
                    num_ctx=8192,
                )
            else:
                raise RuntimeError(f"Ollama port not open at {base_url}.")
        except Exception as e:
            logger.error(f"Forced Ollama (Groq) instantiation failed: {e}")
            raise RuntimeError(f"Failed to initialize local Ollama model 'groq': {e}")

    elif model_choice == 'openai':
        cloud_api_key = getattr(settings, 'OPENAI_API_KEY', None)
        if not _is_valid_openai_key(cloud_api_key):
            raise RuntimeError("OPENAI_API_KEY is not set or invalid in settings.")
        try:
            from langchain_openai import ChatOpenAI
            logger.info("Forced Cloud OpenAI (gpt-4o-mini).")
            return ChatOpenAI(
                api_key=cloud_api_key,
                model="gpt-4o-mini",
                temperature=0.2,
                timeout=30.0,
                max_retries=1,
            )
        except Exception as e:
            logger.error(f"Forced Cloud OpenAI initialization failed: {e}")
            raise RuntimeError(f"Failed to initialize ChatGPT: {e}")

    # ---- Fallback Sequence (Auto / None) ----
    # 1. Local Ollama
    try:
        ollama_api_url = getattr(settings, 'OLLAMA_API_URL', 'http://localhost:11434/api/generate')
        base_url = ollama_api_url.split('/api')[0]

        if is_port_open(base_url, timeout=0.5):
            from langchain_ollama import ChatOllama

            model_name = getattr(settings, 'OLLAMA_MODEL', 'qwen2.5:7b')
            available_models = get_available_ollama_models(base_url)
            model_name = _resolve_ollama_model(model_name, available_models)

            logger.info(f"Instantiating ChatOllama: base_url={base_url}, model={model_name}")
            return ChatOllama(
                model=model_name,
                base_url=base_url,
                timeout=30,
                temperature=0.2,
                num_predict=4096,
                num_ctx=8192,
            )
        else:
            logger.warning(f"Ollama port not open at {base_url}. Skipping.")
    except Exception as e:
        logger.warning(f"Ollama init failed: {e}. Trying next gateway...")

    # 2. Local OpenAI-compatible gateway
    try:
        local_url = getattr(settings, 'LOCAL_LLM_API_URL', 'http://localhost:1234/v1')
        if is_port_open(local_url, timeout=0.5):
            from langchain_openai import ChatOpenAI

            logger.info(f"Instantiating local OpenAI gateway at {local_url}")
            return ChatOpenAI(
                base_url=local_url,
                api_key=getattr(settings, 'LOCAL_LLM_API_KEY', 'lm-studio'),
                model=getattr(settings, 'LOCAL_LLM_MODEL', 'qwen2.5-7b-instruct'),
                temperature=0.2,
                timeout=60.0,
                max_retries=1,
            )
        else:
            logger.warning(f"Local OpenAI gateway port closed at {local_url}. Skipping.")
    except Exception as e:
        logger.warning(f"Local OpenAI gateway init failed: {e}. Trying cloud...")

    # 3. Cloud OpenAI — only when key is valid
    cloud_api_key = getattr(settings, 'OPENAI_API_KEY', None)

    if not _is_valid_openai_key(cloud_api_key):
        logger.warning(
            "OPENAI_API_KEY is not set or invalid. "
            "Skipping Cloud OpenAI — falling back to deterministic test generation."
        )
        raise RuntimeError("No LLM gateway available. Using deterministic fallback.")

    try:
        from langchain_openai import ChatOpenAI

        logger.info("Instantiating Cloud OpenAI (gpt-4o-mini) as fallback.")
        return ChatOpenAI(
            api_key=cloud_api_key,
            model="gpt-4o-mini",
            temperature=0.2,
            timeout=30.0,
            max_retries=1,
        )
    except Exception as e:
        logger.error(f"Cloud OpenAI init failed: {e}")
        raise RuntimeError(f"All LLM gateways failed: {e}")


def llm_predict(llm, prompt=None, model_choice=None):
    """
    Runs a single prompt through get_llm()'s configured instance and
    returns plain text. Backwards compatible with:
      - llm_predict(prompt)
      - llm_predict(llm, prompt)
      - llm_predict(llm, prompt, model_choice=...)
    """
    if prompt is None:
        actual_prompt = llm
        actual_llm = get_llm()
    else:
        actual_prompt = prompt
        actual_llm = llm if not isinstance(llm, str) else get_llm(model_choice=model_choice)

    response = actual_llm.invoke(actual_prompt)
    return response.content.strip() if hasattr(response, "content") else str(response).strip()


def estimate_tokens(text):
    """Rough token estimate: 1 token ≈ 4 characters."""
    return len(str(text)) // 4 if text else 0
