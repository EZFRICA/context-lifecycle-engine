"""
llm_provider.py — LLM Abstraction Layer
========================================
Routes between:
  - CLOUD  : Gemini via Google API (default — provider principal)
  - LOCAL  : Gemma via Ollama  (fallback si ressources insuffisantes)

Usage:
    from llm_provider import get_main_llm, get_extractor_llm
"""

import logging
import os
from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from langchain_google_genai import ChatGoogleGenerativeAI

# Load .env file if it exists
load_dotenv()

# Fallback values for configuration
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma:2b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GEMMA_MODEL = os.getenv("GEMMA_MODEL", "gemma-2-27b-it")
# Real model by default — the CLE runs on a live substrate locally. Override
# with GEMINI_MODEL in .env if your key targets a different one.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
# Temperature for conversational solicitations (cle run).
# In production this is typically 0.7–1.0 for varied, creative responses.
# The FINGERPRINTER always runs at 0 regardless — see get_fingerprint_llm().
MAIN_TEMPERATURE = float(os.getenv("MAIN_TEMPERATURE", "1"))

logger = logging.getLogger(__name__)

_GEMINI_KEY_VALID = bool(GEMINI_API_KEY)


def get_main_llm():
    """Returns the main conversational LLM for agent solicitations (cle run).

    Temperature is MAIN_TEMPERATURE (default 0.7, configurable via .env).
    In real conditions a variable temperature produces more natural, varied
    responses — this is intentional and correct for conversational use.

    DO NOT use this for fingerprinting; use get_fingerprint_llm() instead.
    """
    if LLM_PROVIDER == "ollama":
        logger.info("LLM Provider: Ollama — model=%s, temperature=%s", OLLAMA_MODEL, MAIN_TEMPERATURE)
        return ChatOllama(
            model=OLLAMA_MODEL,
            base_url=OLLAMA_BASE_URL,
            temperature=MAIN_TEMPERATURE,
            num_predict=2048,
        )
    elif LLM_PROVIDER == "gemini":
        logger.info("LLM Provider: Gemini — model=%s, temperature=%s", GEMINI_MODEL, MAIN_TEMPERATURE)
        return ChatGoogleGenerativeAI(
            model=GEMINI_MODEL,
            temperature=MAIN_TEMPERATURE,
            google_api_key=GEMINI_API_KEY,
        )
    else:
        logger.info("LLM Provider: Gemma — model=%s, temperature=%s", GEMMA_MODEL, MAIN_TEMPERATURE)
        return ChatGoogleGenerativeAI(
            model=GEMMA_MODEL,
            temperature=MAIN_TEMPERATURE,
            google_api_key=GEMINI_API_KEY,
        )


def get_fingerprint_llm(model_override: str | None = None):
    """Strictly deterministic (temperature=0) model for substrate probes.

    TEMPERATURE IS ALWAYS 0 HERE — NOT CONFIGURABLE. This is not a
    conservative default; it is an architectural requirement (invariant 6):
    the fingerprint must measure the MODEL, never the sampler. A delta at
    revalidation time means the served model drifted — if temperature were
    non-zero, each revalidation would produce a different fingerprint on the
    same model, triggering spurious auto-demotes to trial.

    Experiment proof (temperature_experiment.py):
      T=0.0 → 3/3 runs identical fingerprint  ✓
      T=0.7 → 3/3 runs all different          ✗ (false drift)

    `model_override` lets the re-validator probe a DIFFERENT real model to
    enact genuine drift (e.g. gemini-3.1-flash-lite → gemini-flash-latest).
    """
    model = model_override or GEMINI_MODEL
    if LLM_PROVIDER == "ollama":
        return ChatOllama(
            model=model_override or OLLAMA_MODEL,
            base_url=OLLAMA_BASE_URL,
            temperature=0,  # MUST NOT be changed — see docstring
            num_predict=512,
        )
    return ChatGoogleGenerativeAI(
        model=model,
        temperature=0,  # MUST NOT be changed — see docstring
        google_api_key=GEMINI_API_KEY,
    )


def get_extractor_llm():
    """
    Returns the deterministic memory-extraction LLM.
    Uses Gemini/Gemma via Google API or falls back to Ollama.
    """
    if LLM_PROVIDER == "gemini":
        logger.debug("Extractor LLM: Gemini — model=%s (deterministic)", GEMINI_MODEL)
        return ChatGoogleGenerativeAI(
            model=GEMINI_MODEL,
            temperature=0.7,
            google_api_key=GEMINI_API_KEY,
        )
    elif LLM_PROVIDER == "ollama":
        logger.info("Extractor LLM: Ollama (local fallback) — model=%s", OLLAMA_MODEL)
        return ChatOllama(
            model=OLLAMA_MODEL,
            base_url=OLLAMA_BASE_URL,
            temperature=0.7,
            num_predict=1024,
            format="json",
        )
    else:
        logger.info("Extractor LLM: Gemma — model=%s", GEMMA_MODEL)
        return ChatGoogleGenerativeAI(
            model=GEMMA_MODEL,
            temperature=0.7,
            google_api_key=GEMINI_API_KEY,
        )

