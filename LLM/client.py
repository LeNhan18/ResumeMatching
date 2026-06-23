import os
import json
import logging
from typing import Type, TypeVar, Optional, List, Dict, Union, get_origin, get_args
from pydantic import BaseModel
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load local environment variables
load_dotenv()

T = TypeVar('T', bound=BaseModel)

class LLMClient:
    def __init__(self):
        # Check LLM provider setting
        llm_provider = os.getenv("LLM_PROVIDER", "").lower()
        
        # Load API keys based on provider
        if llm_provider == "openrouter":
            self.api_key = os.getenv("API_KEY_OPENROUTER") or os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
            self.base_url = os.getenv("LLM_BASE_URL") or "https://openrouter.ai/api/v1"
            self.model_name = os.getenv("OPENAI_MODEL") or os.getenv("LLM_MODEL_NAME") or "google/gemini-2.5-flash"
        else:
            self.api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY_OPENROUTER")
            self.base_url = os.getenv("LLM_BASE_URL") or None
            self.model_name = os.getenv("LLM_MODEL_NAME") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
        
        self.client = None
        if self.api_key:
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
                logger.info(f"Initialized LLMClient with model: {self.model_name}")
            except ImportError:
                logger.error("Failed to import 'openai' package. Make sure it is installed.")
        else:
            logger.warning("No LLM_API_KEY, API_KEY_OPENROUTER or OPENAI_API_KEY found in environment. LLM functions will run in MOCK mode.")

    def is_configured(self) -> bool:
        """Returns True if the LLM client is successfully configured, False if running in mock mode."""
        return self.client is not None

    def generate_text(self, prompt: str, system_prompt: str = "", temperature: float = 0.2) -> str:
        """Generates standard text response from the LLM."""
        if not self.is_configured():
            logger.info("LLM not configured. Returning mock text response.")
            return "[MOCK_RESPONSE] LLM is not configured. Please set LLM_API_KEY in your environment."
            
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=temperature
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Error generating text from LLM: {e}")
            raise e

    def generate_structured(self, prompt: str, response_model: Type[T], system_prompt: str = "", temperature: float = 0.1) -> T:
        """
        Generates structured output matching a Pydantic model.
        Uses OpenAI's native beta.chat.completions.parse API first,
        and falls back to JSON mode + manual validation if not supported.
        """
        if not self.is_configured():
            logger.info(f"LLM not configured. Returning default mock instance of {response_model.__name__}.")
            # Return a default-constructed model (using default fields or empty string/lists)
            # This allows testing the pipeline without API keys
            return self._generate_mock_instance(response_model)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        else:
            messages.append({
                "role": "system", 
                "content": f"You are an expert parsing assistant. You MUST extract information according to the requested JSON schema for {response_model.__name__}."
            })
        messages.append({"role": "user", "content": prompt})

        # Try native Structured Outputs parsing (.parse)
        try:
            logger.debug(f"Attempting structured output parse for model {response_model.__name__} using {self.model_name}")
            completion = self.client.beta.chat.completions.parse(
                model=self.model_name,
                messages=messages,
                response_format=response_model,
                temperature=temperature
            )
            parsed_result = completion.choices[0].message.parsed
            if parsed_result:
                return parsed_result
        except Exception as e:
            logger.warning(f"Native .parse failed or is unsupported by endpoint/model ({e}). Falling back to JSON mode...")

        # Fallback to standard JSON Mode
        try:
            # Inject JSON schema instructions into the prompt just in case
            schema_json = json.dumps(response_model.model_json_schema(), indent=2)
            fallback_prompt = (
                f"{prompt}\n\n"
                f"IMPORTANT: You must return the output STRICTLY matching the following JSON schema:\n"
                f"```json\n{schema_json}\n```\n"
                f"Return ONLY the raw JSON block without markdown formatting."
            )
            
            messages[-1]["content"] = fallback_prompt
            
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=temperature
            )
            
            content = response.choices[0].message.content.strip()
            # In case LLM returns Markdown fences despite instructions, strip them
            if content.startswith("```"):
                lines = content.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines[-1].strip() == "```":
                    lines = lines[:-1]
                content = "\n".join(lines).strip()
                
            return response_model.model_validate_json(content)
        except Exception as ex:
            logger.error(f"Structured extraction fallback to JSON mode failed: {ex}")
            raise ex

    def _generate_mock_instance(self, model_class: Type[T]) -> T:
        """Generates simple mocked Pydantic models for local sandbox testing."""
        # Simple heuristics for constructing an empty or placeholder model instance
        import datetime
        
        # Create dictionary of arguments
        args = {}
        for name, field in model_class.model_fields.items():
            field_type = field.annotation
            origin = get_origin(field_type) or field_type
            args_type = get_args(field_type)
            
            # Simple fallback default values
            if field_type == str or str in args_type or origin == str:
                args[name] = f"Mock {name}"
            elif field_type == float or float in args_type or origin == float:
                args[name] = 0.0
            elif field_type == int or int in args_type or origin == int:
                args[name] = 0
            elif origin == list or origin == List:
                args[name] = []
            elif origin == dict or origin == Dict:
                args[name] = {}
            else:
                args[name] = None
                
        # Fix specific fields to make mock look meaningful
        if model_class.__name__ == "CVSchema":
            args["name"] = "Nguyen Van A"
            args["email"] = "a.nguyen@example.com"
            args["skills"] = ["Python", "Docker", "SQL", "Git"]
            args["industry"] = "IT"
            # Add a mock work experience
            try:
                from RAG.schemas import WorkExperience
                args["experience"] = [
                    WorkExperience(
                        company="Fintech Corp",
                        position="Backend Developer",
                        start_date="2021-01",
                        end_date="2023-12",
                        skills_used=["Python", "SQL"],
                        seniority_level="Mid",
                        description="Developed transaction APIs."
                    )
                ]
            except Exception:
                pass
        elif model_class.__name__ == "JDSchema":
            args["position"] = "Backend Engineer"
            args["required_skills"] = ["Python", "SQL", "Kubernetes"]
            args["nice_to_have"] = ["Docker", "Go"]
            args["min_exp_years"] = 2.0
            args["domain"] = "Backend"
            args["industry"] = "IT"
        elif model_class.__name__ == "ScoringResult":
            args["match_score"] = 50.0
            try:
                from RAG.schemas import ScoringBreakdown
                args["breakdown"] = ScoringBreakdown(skills=50, experience=50, education=50, culture_fit=50)
            except Exception:
                pass
            args["missing_skills"] = ["Kubernetes"]
            args["strengths"] = ["Strong Python skills"]
            args["reasoning"] = "Running in mockup mode. Please configure LLM_API_KEY for real evaluation."
            
        return model_class.model_validate(args)
