import logging
import urllib.request
import json
import socket
from urllib.parse import urlparse
from django.conf import settings

logger = logging.getLogger(__name__)


def is_port_open(url, timeout=0.5):
    """
    Check if a TCP port is open. Uses 0.5s timeout (was 1.0s) to minimise
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


def get_available_ollama_models(base_url):
    try:
        url = f"{base_url}/api/tags"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=2.0) as response:
            data = json.loads(response.read().decode())
            return [model['name'] for model in data.get('models', [])]
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
    Real keys start with 'sk-' and are at least 40 characters long.
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


def get_llm(application=None):
    """
    Returns an LLM instance in priority order:
      1. Local Ollama
      2. Local OpenAI-compatible gateway (LM Studio / vLLM)
      3. Cloud OpenAI — ONLY if OPENAI_API_KEY is present and valid

    FIXES vs original:
      - FIX 1: base_url= not host= for ChatOllama (host= was silently ignored)
      - FIX 2: temperature/num_predict as top-level kwargs, not ollama_options={}
      - FIX 3: max_retries=1 on ChatOpenAI — was unlimited, caused infinite hang
      - FIX 4: timeout=30s not 120s — logs showed 2-minute hang per attempt
      - FIX 5: _is_valid_openai_key() guard — skips Cloud OpenAI when key is
               None/blank so task falls through to deterministic fallback instantly
      - FIX 6: is_port_open timeout reduced 1.0s → 0.5s per gateway to halve
               the dead-gateway penalty (1s × 2 gateways → 0.5s × 2 = saved
               ~1 minute across 140 tests when nothing is running)
    """
    # ---- 1. Local Ollama ----
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
                base_url=base_url,      # FIX 1: was host=
                timeout=60,
                temperature=0.2,        # FIX 2: was inside ollama_options={}
                num_predict=4096,
                num_ctx=16000,
            )
        else:
            logger.warning(f"Ollama port not open at {base_url}. Skipping.")
    except Exception as e:
        logger.warning(f"Ollama init failed: {e}. Trying next gateway...")

    # ---- 2. Local OpenAI-compatible gateway ----
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
                max_retries=1,          # FIX 3
            )
        else:
            logger.warning(f"Local OpenAI gateway port closed at {local_url}. Skipping.")
    except Exception as e:
        logger.warning(f"Local OpenAI gateway init failed: {e}. Trying cloud...")

    # ---- 3. Cloud OpenAI — only when key is valid ----
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
            timeout=30.0,       # FIX 4: was 120s
            max_retries=1,      # FIX 3: was unlimited
        )
    except Exception as e:
        logger.error(f"Cloud OpenAI init failed: {e}")
        raise RuntimeError(f"All LLM gateways failed: {e}")


def execute_llm_prompt(prompt):
    """
    Executes a prompt with sequential gateway failover.
    Same fixes as get_llm().
    """
    # ---- 1. Ollama ----
    try:
        ollama_api_url = getattr(settings, 'OLLAMA_API_URL', 'http://localhost:11434/api/generate')
        base_url = ollama_api_url.split('/api')[0]

        if is_port_open(base_url, timeout=0.5):
            from langchain_ollama import ChatOllama

            model_name = getattr(settings, 'OLLAMA_MODEL', 'qwen2.5:7b')
            available_models = get_available_ollama_models(base_url)
            model_name = _resolve_ollama_model(model_name, available_models)

            logger.info(f"Invoking Ollama model '{model_name}'...")
            llm = ChatOllama(
                model=model_name,
                base_url=base_url,
                timeout=60,
                temperature=0.2,
                num_predict=4096,
            )
            response = llm.invoke(prompt)
            return response.content.strip() if hasattr(response, "content") else str(response).strip()
    except Exception as e:
        logger.warning(f"Ollama prompt failed: {e}. Trying local OpenAI...")

    # ---- 2. Local OpenAI gateway ----
    try:
        local_url = getattr(settings, 'LOCAL_LLM_API_URL', 'http://localhost:1234/v1')
        if is_port_open(local_url, timeout=0.5):
            from langchain_openai import ChatOpenAI

            logger.info(f"Invoking local OpenAI at {local_url}...")
            llm = ChatOpenAI(
                base_url=local_url,
                api_key=getattr(settings, 'LOCAL_LLM_API_KEY', 'lm-studio'),
                model=getattr(settings, 'LOCAL_LLM_MODEL', 'qwen2.5-7b-instruct'),
                temperature=0.2,
                timeout=60.0,
                max_retries=1,
            )
            response = llm.invoke(prompt)
            return response.content.strip() if hasattr(response, "content") else str(response).strip()
    except Exception as e:
        logger.warning(f"Local OpenAI prompt failed: {e}. Trying cloud...")

    # ---- 3. Cloud OpenAI ----
    cloud_api_key = getattr(settings, 'OPENAI_API_KEY', None)

    if not _is_valid_openai_key(cloud_api_key):
        logger.warning("No valid OPENAI_API_KEY — skipping cloud. Using deterministic fallback.")
        raise RuntimeError("No LLM available. Using deterministic fallback.")

    try:
        from langchain_openai import ChatOpenAI

        logger.info("Invoking Cloud OpenAI (gpt-4o-mini)...")
        llm = ChatOpenAI(
            api_key=cloud_api_key,
            model="gpt-4o-mini",
            temperature=0.2,
            timeout=30.0,
            max_retries=1,
        )
        response = llm.invoke(prompt)
        return response.content.strip() if hasattr(response, "content") else str(response).strip()
    except Exception as e:
        logger.error(f"Cloud OpenAI prompt failed: {e}")
        raise RuntimeError(f"All LLM gateways failed: {e}")


def llm_predict(llm, prompt):
    """Wrapper used by LLMService — delegates to the failover executor."""
    return execute_llm_prompt(prompt)


def estimate_tokens(text):
    """Rough token estimate: 1 token ≈ 4 characters."""
    return len(str(text)) // 4 if text else 0