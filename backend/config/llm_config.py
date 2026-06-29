import logging
import urllib.request
import json
import socket
from urllib.parse import urlparse, urljoin
from django.conf import settings

logger = logging.getLogger(__name__)

def is_port_open(url):
    try:
        parsed = urlparse(url)
        host = parsed.hostname or 'localhost'
        port = parsed.port
        if port is None:
            port = 80 if parsed.scheme == 'http' else 443
        
        # Test socket connection with 1.0s timeout
        with socket.create_connection((host, port), timeout=1.0) as _:
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

def get_llm(application=None):
    """
    Returns the LLM instance based on configuration, prioritizing local LLM models.
    Checks port connectivity before initializing local options to prevent runtime ConnectionErrors.
    """
    # 1. Try local Ollama first
    try:
        ollama_api_url = getattr(settings, 'OLLAMA_API_URL', 'http://localhost:11434/api/generate')
        base_url = ollama_api_url.split('/api')[0]
        
        if is_port_open(base_url):
            from langchain_ollama import ChatOllama
            model_name = getattr(settings, 'OLLAMA_MODEL', 'qwen2.5:7b')
            
            available_models = get_available_ollama_models(base_url)
            if available_models:
                clean_model = model_name.split(':')[0]
                model_exists = any(clean_model in m for m in available_models)
                if not model_exists:
                    logger.warning(f"Target model '{model_name}' not found locally in Ollama. Available: {available_models}")
                    if any('qwen' in m for m in available_models):
                        model_name = 'qwen:7b'
                    else:
                        model_name = available_models[0]
                
                logger.info(f"Instantiating ChatOllama: URL={base_url}, Model={model_name}")
                return ChatOllama(
                    model=model_name,
                    host=base_url,
                    timeout=120.0,
                    ollama_options={
                        'temperature': 0.2,
                        'num_predict': 4096,
                        'num_ctx': 16000,
                    }
                )
        else:
            logger.warning(f"Ollama port is closed at {base_url}. Skipping Ollama.")
    except Exception as e:
        logger.warning(f"Ollama check/initialization failed: {e}. Trying other local/cloud gateways...")

    # 2. Try generic local OpenAI gateway (LM Studio / vLLM / llama.cpp)
    try:
        local_openai_url = getattr(settings, 'LOCAL_LLM_API_URL', 'http://localhost:1234/v1')
        if is_port_open(local_openai_url):
            from langchain_openai import ChatOpenAI
            logger.info(f"Trying Local OpenAI gateway at {local_openai_url}...")
            return ChatOpenAI(
                base_url=local_openai_url,
                api_key=getattr(settings, 'LOCAL_LLM_API_KEY', 'lm-studio'),
                model=getattr(settings, 'LOCAL_LLM_MODEL', 'qwen2.5-7b-instruct'),
                temperature=0.2,
                timeout=120.0
            )
        else:
            logger.warning(f"Local OpenAI gateway port is closed at {local_openai_url}. Skipping Local OpenAI.")
    except Exception as e:
        logger.warning(f"Local OpenAI gateway check/initialization failed: {e}. Trying cloud fallback...")

    # 3. Fallback to Cloud OpenAI
    try:
        cloud_api_key = getattr(settings, 'OPENAI_API_KEY', None)
        if cloud_api_key:
            from langchain_openai import ChatOpenAI
            logger.info("Instantiating Cloud OpenAI as a resilient fallback.")
            return ChatOpenAI(
                api_key=cloud_api_key,
                model="gpt-4o-mini",
                temperature=0.2,
                timeout=120.0
            )
        else:
            logger.warning("Cloud OpenAI API key not found in environment/settings.")
    except Exception as e:
        logger.error(f"Cloud OpenAI fallback initialization failed: {e}")

    # 4. Ultimate fallback
    logger.error("No LLM gateway could be initialized. Please check your config.")
    raise RuntimeError("No LLM gateway could be initialized. Please ensure Ollama, LM Studio, or OpenAI API key is configured.")

def execute_llm_prompt(prompt):
    """
    Executes a prompt against LLM gateways sequentially with real-time failover at runtime.
    Prioritizes Ollama -> Local OpenAI -> Cloud OpenAI fallback.
    """
    # 1. Try local Ollama first
    try:
        ollama_api_url = getattr(settings, 'OLLAMA_API_URL', 'http://localhost:11434/api/generate')
        base_url = ollama_api_url.split('/api')[0]
        if is_port_open(base_url):
            from langchain_ollama import ChatOllama
            model_name = getattr(settings, 'OLLAMA_MODEL', 'qwen2.5:7b')
            available_models = get_available_ollama_models(base_url)
            if available_models:
                clean_model = model_name.split(':')[0]
                model_exists = any(clean_model in m for m in available_models)
                if not model_exists:
                    if any('qwen' in m for m in available_models):
                        model_name = 'qwen:7b'
                    else:
                        model_name = available_models[0]
            
            logger.info(f"Invoking Ollama model '{model_name}'...")
            llm = ChatOllama(
                model=model_name,
                host=base_url,
                timeout=10.0,
                ollama_options={'temperature': 0.2, 'num_predict': 2048}
            )
            response = llm.invoke(prompt)
            if hasattr(response, "content"):
                return response.content.strip()
            return str(response).strip()
    except Exception as ollama_err:
        logger.warning(f"Ollama prompt execution failed: {ollama_err}. Transitioning to Local OpenAI...")

    # 2. Try Generic Local OpenAI gateway (LM Studio / vLLM / llama.cpp)
    try:
        local_openai_url = getattr(settings, 'LOCAL_LLM_API_URL', 'http://localhost:1234/v1')
        if is_port_open(local_openai_url):
            from langchain_openai import ChatOpenAI
            logger.info(f"Invoking Local OpenAI at {local_openai_url}...")
            llm = ChatOpenAI(
                base_url=local_openai_url,
                api_key=getattr(settings, 'LOCAL_LLM_API_KEY', 'lm-studio'),
                model=getattr(settings, 'LOCAL_LLM_MODEL', 'qwen2.5-7b-instruct'),
                temperature=0.2,
                timeout=10.0
            )
            response = llm.invoke(prompt)
            if hasattr(response, "content"):
                return response.content.strip()
            return str(response).strip()
    except Exception as local_openai_err:
        logger.warning(f"Local OpenAI execution failed: {local_openai_err}. Transitioning to Cloud OpenAI...")

    # 3. Try Cloud OpenAI (using settings.OPENAI_API_KEY)
    try:
        cloud_api_key = getattr(settings, 'OPENAI_API_KEY', None)
        if cloud_api_key:
            from langchain_openai import ChatOpenAI
            logger.info("Invoking Cloud OpenAI...")
            llm = ChatOpenAI(
                api_key=cloud_api_key,
                model="gpt-4o-mini",
                temperature=0.2,
                timeout=25.0
            )
            response = llm.invoke(prompt)
            if hasattr(response, "content"):
                return response.content.strip()
            return str(response).strip()
        else:
            logger.warning("Cloud OpenAI API key not found in settings/env.")
    except Exception as cloud_err:
        logger.error(f"Cloud OpenAI execution failed: {cloud_err}")

    # Ultimate fallback
    logger.error("All LLM prompt execution gateways failed.")
    raise RuntimeError("All LLM prompt execution gateways failed. Please check your Ollama, LM Studio, or OpenAI API key configurations.")

def llm_predict(llm, prompt):
    """
    Invokes the LLM safely using the dynamic runtime failover wrapper.
    """
    return execute_llm_prompt(prompt)

def estimate_tokens(text):
    """
    Utility helper to estimate tokens count from prompt or response text
    when direct stats are unavailable (1 token ~= 4 characters).
    """
    if not text:
        return 0
    return len(str(text)) // 4
