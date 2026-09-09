"""
LLM Job-Match Evaluation
========================
Takes a cleaned Indeed job description plus company-knowledge chunks retrieved
from Azure AI Search (app.knowledge_base.azure_search) and asks an Azure OpenAI
chat deployment to produce a structured match verdict.

The Azure AI Search relevance score is never used as the final match score -
only this LLM's structured judgement sets JobPosting.match_score.
"""

from __future__ import annotations

import json
from typing import Optional

from app.config.settings import get_settings
from app.knowledge_base.models import RetrievedChunk
from app.matching.models import MatchResult
from app.utils.logger import logger

_SYSTEM_PROMPT = (
    "You are a technical capabilities analyst. Your task is to compare JOB REQUIREMENTS against the provided COMPANY CAPABILITIES.\n\n"
    "RULES:\n"
    "1. Read the COMPANY CAPABILITIES carefully. Any technology, tool, methodology, or skill mentioned or demonstrated in the capabilities is a MATCH.\n"
    "2. 'matched_skills': List of specific technical skills/tools from the job that our company possesses based on the capabilities text.\n"
    "3. 'missing_skills': ONLY list skills required by the job that are completely absent from the company capabilities.\n"
    "4. 'match_score': Integer (0-100) representing how well the company meets the required technical stack.\n"
    "5. 'match_reason': 1-2 sentence factual summary of the match.\n"
    "6. Respond strictly with a JSON object:\n"
    '{\n'
    '  "match_score": 85,\n'
    '  "matched_skills": ["Skill1", "Skill2"],\n'
    '  "missing_skills": ["Skill3"],\n'
    '  "match_reason": "Summary of fit."\n'
    '}'
)


class LLMMatcher:
    """Evaluates job-to-company fit using Azure OpenAI, OpenRouter (Gemma-4), or NVIDIA NIM."""

    def __init__(self, client=None, enabled: Optional[bool] = None, deployment: Optional[str] = None) -> None:
        """
        Args:
            client: Optional pre-built AsyncOpenAI / AsyncAzureOpenAI client, for tests.
            enabled: Override for whether evaluation is active (tests only).
            deployment: Override for the chat deployment / model name (tests only).
        """
        settings = get_settings()

        # Check USE_AZURE_MODEL toggle first
        if hasattr(settings, "use_azure_model") and settings.use_azure_model is not None:
            self._provider = "azure" if settings.use_azure_model else "openrouter"
        else:
            self._provider = settings.llm_provider.lower()

        self._deployment = deployment

        if enabled is False:
            self._enabled = False
            self._client = None
            return

        if client is not None:
            self._client = client
            self._enabled = True if enabled is None else enabled
            self._deployment = self._deployment or (settings.azure_openai_chat_deployment if self._provider == "azure" else settings.openrouter_model)
            return

        if self._provider == "openrouter":
            api_key = settings.openrouter_api_key.strip()
            base_url = settings.openrouter_base_url.strip() or "https://openrouter.ai/api/v1"
            model = self._deployment or settings.openrouter_model.strip() or "google/gemma-4-31b-it:free"

            self._enabled = bool(api_key and model)
            self._deployment = model
            self._client = None

            if not self._enabled:
                logger.warning(
                    "OpenRouter LLM is not fully configured (OPENROUTER_API_KEY/OPENROUTER_MODEL) - LLM matching disabled."
                )
                return

            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(
                base_url=base_url,
                api_key=api_key,
                default_headers={
                    "HTTP-Referer": "http://localhost:8000",
                    "X-Title": "Indeed Job Intelligence Scraper",
                },
            )
            logger.info("Initialized LLMMatcher with OpenRouter model '{}' (Free Tier)", self._deployment)

        elif self._provider == "azure":
            self._deployment = self._deployment or settings.azure_openai_chat_deployment
            self._enabled = bool(
                settings.azure_openai_endpoint and settings.azure_openai_api_key and self._deployment
            )
            self._client = None
            if not self._enabled:
                logger.warning(
                    "Azure OpenAI is not fully configured (endpoint/api key/deployment) - LLM matching disabled."
                )
                return

            from openai import AsyncAzureOpenAI
            self._client = AsyncAzureOpenAI(
                azure_endpoint=settings.azure_openai_endpoint,
                api_key=settings.azure_openai_api_key,
                api_version=settings.azure_openai_api_version,
            )
            logger.info("Initialized LLMMatcher with Azure OpenAI deployment '{}'", self._deployment)

        elif self._provider == "nvidia" or self._provider == "openai":
            api_key = settings.nvidia_api_key.strip()
            base_url = settings.nvidia_base_url.strip() or "https://integrate.api.nvidia.com/v1"
            model = self._deployment or settings.nvidia_model.strip()

            self._enabled = bool(api_key and model)
            self._deployment = model
            self._client = None

            if not self._enabled:
                logger.warning(
                    "NVIDIA LLM is not fully configured (NVIDIA_API_KEY/NVIDIA_MODEL) - LLM matching disabled."
                )
                return

            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(
                base_url=base_url,
                api_key=api_key,
            )
            logger.info("Initialized LLMMatcher with NVIDIA NIM model '{}'", self._deployment)

        else:
            self._enabled = False
            self._client = None
            logger.warning("Unknown LLM_PROVIDER '{}' - LLM matching disabled.", self._provider)

    async def evaluate(self, job_description: str, kb_chunks: list[RetrievedChunk]) -> MatchResult:
        """Return a structured match result. Never raises - any failure yields a safe default."""
        if not self._enabled or not self._client:
            return MatchResult(match_score=None, matched_skills=[], missing_skills=[], match_reason="LLM matching not configured")

        # --- Token & Quality Optimization ---
        # 1. Clean job description (first 2,000 chars covers core role and requirements)
        cleaned_jd = job_description.strip()[:2000] if job_description else ""
        
        # 2. Extract rich snippet excerpts from chunks (up to 450 chars) so full technical context is preserved
        compact_chunks = []
        for c in (kb_chunks or []):
            snippet = (c.chunk or "").strip()[:450].replace("\n", " ")
            if snippet:
                compact_chunks.append(f"- {snippet}")
        
        context = "\n".join(compact_chunks) or "No company knowledge retrieved."
        user_prompt = (
            f"You are matching a candidate company against a job posting.\n\n"
            f"COMPANY CAPABILITIES:\n{context}\n\n"
            f"JOB REQUIREMENTS:\n{cleaned_jd}\n\n"
            f"INSTRUCTIONS:\n"
            f"1. Extract the specific technical skills/requirements needed by the job.\n"
            f"2. Put skills that exist in COMPANY CAPABILITIES into 'matched_skills'.\n"
            f"3. Put skills that are absent from COMPANY CAPABILITIES into 'missing_skills'.\n"
            f"4. Calculate 'match_score' (0-100) and write a short 'match_reason'.\n\n"
            f"JSON Output Format:\n"
            f'{{\n  "match_score": 80,\n  "matched_skills": ["Skill1", "Skill2"],\n  "missing_skills": ["Skill3"],\n  "match_reason": "Summary of fit"\n}}'
        )

        try:
            import re
            import asyncio

            kwargs = {
                "model": self._deployment,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.1,
                "max_tokens": 2500 if self._provider == "openrouter" else 800,  # Generous headroom for reasoning models
            }

            # If supported / Azure OpenAI standard gpt models
            if self._provider == "azure" and "phi" not in str(self._deployment).lower():
                kwargs["response_format"] = {"type": "json_object"}

            response = None
            # Retry loop with fast available free models for OpenRouter
            models_to_try = [self._deployment]
            if self._provider == "openrouter":
                extra_models = [
                    "nvidia/nemotron-3-ultra-550b-a55b:free",
                    "nvidia/nemotron-3.5-lightning:free",
                    "google/gemma-4-31b-it:free",
                    "google/gemma-4-26b-a4b-it:free",
                    "cohere/north-mini-code:free",
                ]
                models_to_try = [self._deployment] + [m for m in extra_models if m != self._deployment]

            last_error = None
            for model_cand in models_to_try:
                try:
                    kwargs["model"] = model_cand
                    response = await self._client.chat.completions.create(**kwargs)
                    if response and response.choices:
                        choice = response.choices[0]
                        msg = getattr(choice, "message", None)
                        if msg:
                            c = (getattr(msg, "content", "") or "").strip()
                            r = (getattr(msg, "reasoning", "") or "").strip()
                            if c or r:
                                break
                except Exception as api_err:
                    last_error = api_err
                    # Quietly retry next candidate on rate limit without spamming console
                    if "429" in str(api_err) and self._provider == "openrouter":
                        await asyncio.sleep(0.2)
                        continue
                    else:
                        break

            if not response or not response.choices:
                if last_error:
                    raise last_error

            raw_content = ""
            raw_reasoning = ""
            if response and response.choices:
                raw_msg = response.choices[0].message
                raw_content = (getattr(raw_msg, "content", "") or "").strip()
                raw_reasoning = str(getattr(raw_msg, "reasoning", "") or "").strip()
                logger.info("LLM Raw Content: '{}' | Reasoning Len: {}", raw_content[:150], len(raw_reasoning))

            # Robust JSON extraction from content first, then reasoning if content is empty
            text_to_parse = raw_content if raw_content else raw_reasoning
            json_str = text_to_parse
            code_block_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text_to_parse, re.IGNORECASE)
            if code_block_match:
                json_str = code_block_match.group(1).strip()
            else:
                brace_match = re.search(r"\{[\s\S]*\}", text_to_parse)
                if brace_match:
                    json_str = brace_match.group(0).strip()

            payload = {}
            if json_str:
                try:
                    payload = json.loads(json_str)
                except Exception:
                    try:
                        # Remove trailing commas and fix malformed JSON fragments
                        cleaned = re.sub(r',\s*([\]}])', r'\1', json_str)
                        cleaned = re.sub(r',\s*$', '', cleaned)
                        payload = json.loads(cleaned)
                    except Exception:
                        # Regex extraction fallback if JSON parser fails
                        score_m = re.search(r'"match_score"\s*:\s*(\d+)', text_to_parse)
                        matched_m = re.findall(r'"matched_skills"\s*:\s*\[(.*?)\]', text_to_parse, re.DOTALL)
                        missing_m = re.findall(r'"missing_skills"\s*:\s*\[(.*?)\]', text_to_parse, re.DOTALL)
                        reason_m = re.search(r'"match_reason"\s*:\s*"([^"]*)"', text_to_parse)

                        matched_skills_found = []
                        if matched_m:
                            matched_skills_found = [s.strip(' "\'') for s in matched_m[0].split(',') if s.strip(' "\'')]

                        missing_skills_found = []
                        if missing_m:
                            missing_skills_found = [s.strip(' "\'') for s in missing_m[0].split(',') if s.strip(' "\'')]

                        payload = {
                            "match_score": int(score_m.group(1)) if score_m else None,
                            "matched_skills": matched_skills_found,
                            "missing_skills": missing_skills_found,
                            "match_reason": reason_m.group(1) if reason_m else ""
                        }
            
            matched_list = [str(s) for s in payload.get("matched_skills", [])]
            missing_list = [str(s) for s in payload.get("missing_skills", [])]
            reason = str(payload.get("match_reason", "")).strip()

            # --- Fully Dynamic Semantic & Substring Reconciliation ---
            # Automatically verifies any skill phrase against the retrieved knowledge context.
            # No hardcoded skills: works dynamically for ANY new service added to the knowledge base in the future.
            context_lower = " " + re.sub(r"[^\w\s]", " ", context.lower()) + " "
            cleaned_missing = []
            
            # Common stop words to ignore when checking multi-word phrases
            stopwords = {"experience", "with", "and", "or", "in", "for", "the", "a", "an", "of", "to", "strong", "knowledge", "skills", "using", "hands-on"}

            for skill in missing_list:
                s_clean = skill.strip()
                tokens = [t.lower() for t in re.findall(r"\b[\w\+\#\.\-]+\b", s_clean) if t.lower() not in stopwords and len(t) > 1]
                
                # Check if significant terms appear in retrieved context
                is_present_in_context = False
                if tokens:
                    significant_matches = [t for t in tokens if f" {t} " in context_lower or t in context_lower]
                    if len(significant_matches) >= 1 and (len(significant_matches) / len(tokens) >= 0.5 or len(tokens) == 1):
                        is_present_in_context = True

                if is_present_in_context:
                    if skill not in matched_list:
                        matched_list.append(skill)
                else:
                    cleaned_missing.append(skill)

            # --- Dynamic Knowledge-Base Direct Extraction Fallback ---
            # If the LLM returned empty skills (e.g. rate limit exhaustion or output truncation),
            # extract real technical requirements and frameworks from the job and evaluate against KB context.
            if not matched_list and not cleaned_missing and context != "No company knowledge retrieved.":
                TECH_SKILL_PATTERNS = [
                    # AI, ML, RL, Robotics & Vision concepts
                    (r"\breinforcement\s+learning\b", "Reinforcement Learning"),
                    (r"\bimitation\s+learning\b", "Imitation Learning"),
                    (r"\bdeep\s+learning\b", "Deep Learning"),
                    (r"\bmachine\s+learning\b", "Machine Learning"),
                    (r"\bcomputer\s+vision\b", "Computer Vision"),
                    (r"\bnatural\s+language\s+processing\b", "Natural Language Processing"),
                    (r"\blarge\s+language\s+models?\b", "LLMs"),
                    # Frameworks, simulators & robotics
                    (r"\bIsaacGym\b", "IsaacGym"),
                    (r"\bIsaacLab\b", "IsaacLab"),
                    (r"\bMuJoCo\b", "MuJoCo"),
                    (r"\bPyTorch\b", "PyTorch"),
                    (r"\bTensorFlow\b", "TensorFlow"),
                    (r"\bKeras\b", "Keras"),
                    (r"\bJAX\b", "JAX"),
                    (r"\bScikit-learn\b", "Scikit-learn"),
                    (r"\bPandas\b", "Pandas"),
                    (r"\bNumPy\b", "NumPy"),
                    (r"\bOpenCV\b", "OpenCV"),
                    (r"\bROS\b", "ROS"),
                    (r"\bGymnasium\b", "Gymnasium"),
                    (r"\b(?:robotics|robots)\b", "Robotics"),
                    # Languages, runtimes & system tools
                    (r"\bPython\b", "Python"),
                    (r"\bC\+\+\b", "C++"),
                    (r"\bRust\b", "Rust"),
                    (r"\bJava\b", "Java"),
                    (r"\bGo\b", "Go"),
                    (r"\bSQL\b", "SQL"),
                    (r"\bCUDA\b", "CUDA"),
                    (r"\bLinux\b", "Linux"),
                    (r"\bDocker\b", "Docker"),
                    (r"\bKubernetes\b", "Kubernetes"),
                    (r"\bBash\b", "Bash"),
                    # Cloud, Microsoft & enterprise platforms
                    (r"\bAzure\s+OpenAI\b", "Azure OpenAI"),
                    (r"\bAzure\s+(?:AD|DevOps|Entra\s+ID)?\b", "Azure"),
                    (r"\bAWS\b", "AWS"),
                    (r"\bGCP\b", "GCP"),
                    (r"\bSharePoint\b", "SharePoint"),
                    (r"\bDynamics\s+365\b", "Dynamics 365"),
                    (r"\bPower\s+BI\b", "Power BI"),
                    (r"\bPower\s+(?:Apps|Platform)\b", "Power Platform"),
                    (r"\b(?:M365|Microsoft\s+365)\b", "Microsoft 365"),
                    # Identity & protocols
                    (r"\b(?:SSO|SAML|OAuth|IAM|Entra\s+ID|Active\s+Directory|Okta)\b", "Identity & Access Management"),
                ]

                # Acronym mapping to prevent duplicates (e.g. RL -> Reinforcement Learning, ML -> Machine Learning)
                ACRONYM_MAP = {
                    "RL": "Reinforcement Learning",
                    "ML": "Machine Learning",
                    "DL": "Deep Learning",
                    "CV": "Computer Vision",
                    "NLP": "Natural Language Processing",
                    "LLM": "LLMs",
                    "LLMS": "LLMs",
                    "AI": "AI",
                }

                identified_skills = []
                for pattern, canonical in TECH_SKILL_PATTERNS:
                    if re.search(pattern, cleaned_jd, re.IGNORECASE):
                        if canonical not in identified_skills:
                            identified_skills.append(canonical)

                # Also capture capitalized tech acronyms
                common_stop = {
                    "AN", "OR", "IN", "TO", "WE", "AS", "DO", "IF", "US", "THE", "AND", "WITH", "NOT",
                    "OUR", "WHAT", "THIS", "RUN", "CAN", "GET", "THAT", "FULL", "REAL", "BY", "FOR", "AT", "BE", "JD", "HR"
                }
                for acr in re.findall(r"\b[A-Z]{2,6}\b", cleaned_jd):
                    if acr in common_stop:
                        continue
                    canonical = ACRONYM_MAP.get(acr, acr)
                    if canonical not in identified_skills:
                        identified_skills.append(canonical)

                for skill in identified_skills:
                    s_low = skill.lower()
                    # Check against knowledge base context tokens
                    if f" {s_low} " in context_lower or s_low in context_lower:
                        if skill not in matched_list:
                            matched_list.append(skill)
                    else:
                        if skill not in cleaned_missing:
                            cleaned_missing.append(skill)

            # --- Post-Processing Deduplication & Normalization ---
            # Clean both matched_list and cleaned_missing to remove redundant/generic terms and duplicates
            GENERIC_NOISE = {"hardware", "real systems", "simulators", "robots", "system", "systems", "policies"}
            
            def clean_and_dedup(skill_items):
                result = []
                for item in skill_items:
                    name = str(item).strip()
                    if not name or name.lower() in GENERIC_NOISE:
                        continue
                    # Normalize plural or acronym overlaps
                    if name.lower() in ("rl", "reinforcement learning"):
                        name = "Reinforcement Learning"
                    elif name.lower() in ("ml", "machine learning"):
                        name = "Machine Learning"
                    elif name.lower() in ("robots", "robotics"):
                        name = "Robotics"
                    elif name.lower() in ("llm", "llms", "large language models"):
                        name = "LLMs"
                    
                    if not any(name.lower() == existing.lower() for existing in result):
                        result.append(name)
                return result

            matched_list = clean_and_dedup(matched_list)
            cleaned_missing = clean_and_dedup(cleaned_missing)

            # Ensure an item isn't simultaneously in matched and missing
            cleaned_missing = [s for s in cleaned_missing if not any(s.lower() == m.lower() for m in matched_list)]

            # If company KB has AI/ML capabilities (e.g. Computer Vision, Azure OpenAI, Machine Learning, DeepStream)
            # and job requires AI or Machine Learning, match it accurately.
            kb_has_ai = any(kw in context_lower for kw in (" ai ", "artificial intelligence", "machine learning", "computer vision", "deepstream", "azure openai", "model"))
            if kb_has_ai:
                if "Machine Learning" in cleaned_missing:
                    cleaned_missing.remove("Machine Learning")
                    if "Machine Learning" not in matched_list:
                        matched_list.append("Machine Learning")
                if "AI" in cleaned_missing:
                    cleaned_missing.remove("AI")
                    if "AI" not in matched_list:
                        matched_list.append("AI")
                elif "AI" not in matched_list and any(m in matched_list for m in ("Computer Vision", "Azure OpenAI", "Machine Learning")):
                    matched_list.append("AI")

            raw_score = payload.get("match_score")
            if raw_score is not None:
                score = int(raw_score)
            else:
                total_skills = len(matched_list) + len(cleaned_missing)
                if total_skills > 0:
                    if len(cleaned_missing) == 0 and len(matched_list) > 0:
                        score = 100
                    else:
                        score = int(round((len(matched_list) / total_skills) * 100))
                else:
                    score = 0

            if not reason or reason == "Evaluated by LLM":
                if len(matched_list) > 0 and len(cleaned_missing) == 0:
                    reason = f"Excellent 100% fit with proven company capabilities in {', '.join(matched_list[:3])}."
                elif len(matched_list) > 0:
                    reason = f"Strong alignment in {', '.join(matched_list[:3])}; gaps identified in {', '.join(cleaned_missing[:2])}."
                else:
                    reason = "No direct company capabilities found matching this role requirements."

            return MatchResult(
                match_score=score,
                matched_skills=matched_list,
                missing_skills=cleaned_missing,
                match_reason=reason,
            )
        except Exception as exc:
            logger.error("LLM match evaluation failed: {}", exc)
            return MatchResult(match_score=None, matched_skills=[], missing_skills=[], match_reason=f"Evaluation failed: {exc}")

    async def close(self) -> None:
        if self._client and hasattr(self._client, "close"):
            try:
                await self._client.close()
            except Exception as exc:
                logger.error("Error closing LLM client: {}", exc)

