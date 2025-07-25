"""
LLM Client for QualGent Multi-Agent QA System
FIXED VERSION - Forces real LLM usage, prevents fallback to mock
"""

import asyncio
import logging
import os
from typing import Dict, List, Optional, Any
import openai
import anthropic
import google.generativeai as genai

class LLMClient:
    """
    Client for interacting with various LLM providers
    FIXED to prevent fallback to mock responses
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.provider = config.get("provider", "openai").lower()
        self.model = config.get("model", "gpt-4")
        
        # Setup logging
        self.logger = logging.getLogger("LLMClient")
        self.logger.setLevel(logging.INFO)
        
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - LLMClient - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        
        # Initialize clients
        self._initialize_clients()
        
        self.logger.info(f"Initialized LLM client: {self.provider} - {self.model}")
    
    def _initialize_clients(self):
        """Initialize LLM provider clients"""
        try:
            if self.provider == "openai":
                self.openai_api_key = os.getenv("OPENAI_API_KEY") or self.config.get("api_key")
                if not self.openai_api_key:
                    self.logger.warning("OpenAI API key not found")
                
            elif self.provider == "anthropic":
                self.anthropic_client = anthropic.Anthropic(
                    api_key=os.getenv("ANTHROPIC_API_KEY") or self.config.get("api_key")
                )
                
            elif self.provider == "google":
                api_key = os.getenv("GOOGLE_API_KEY") or self.config.get("api_key")
                if api_key:
                    genai.configure(api_key=api_key)
                    self.logger.info(" Google Gemini configured successfully")
                else:
                    self.logger.warning("Google API key not found")
                    
        except Exception as e:
            self.logger.error(f"Failed to initialize LLM client: {e}")
    
    async def generate_response(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None
    ) -> str:
        """Generate response from LLM - FIXED to use real LLM only"""
        
        self.logger.info(f" Generating {self.provider} response for: {prompt[:50]}...")
        
        try:
            if self.provider == "openai":
                return await self._generate_openai_response(
                    prompt, max_tokens, temperature, system_prompt
                )
            elif self.provider == "anthropic":
                return await self._generate_anthropic_response(
                    prompt, max_tokens, temperature, system_prompt
                )
            elif self.provider == "google":
                return await self._generate_google_response(
                    prompt, max_tokens, temperature, system_prompt
                )
            elif self.provider == "mock":
                # ONLY use mock if explicitly requested
                return await self._generate_mock_response(prompt)
            else:
                raise ValueError(f"Unknown LLM provider: {self.provider}")
                
        except Exception as e:
            self.logger.error(f" LLM generation failed: {e}")
            
            # CRITICAL FIX: Don't use fallback for real providers
            if self.provider in ["openai", "anthropic", "google"]:
                self.logger.error(" Real LLM failed - not using fallback mock")
                raise Exception(f"Real {self.provider} LLM failed: {e}")
            else:
                # Only use fallback for mock provider
                return await self._generate_fallback_response(prompt)
    
    async def _generate_openai_response(
        self,
        prompt: str,
        max_tokens: Optional[int],
        temperature: float,
        system_prompt: Optional[str]
    ) -> str:
        """Generate response using OpenAI (updated for openai>=1.0.0)"""
        try:
            from openai import AsyncOpenAI
            
            client = AsyncOpenAI(api_key=self.openai_api_key)
            
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            self.logger.info(" Calling OpenAI API...")
            response = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens or 2000,
                temperature=temperature
            )
            
            result = response.choices[0].message.content.strip()
            self.logger.info(f" OpenAI response: {len(result)} characters")
            return result
            
        except Exception as e:
            self.logger.error(f"OpenAI API error: {e}")
            raise
    
    async def _generate_anthropic_response(
        self,
        prompt: str,
        max_tokens: Optional[int],
        temperature: float,
        system_prompt: Optional[str]
    ) -> str:
        """Generate response using Anthropic Claude"""
        try:
            full_prompt = prompt
            if system_prompt:
                full_prompt = f"{system_prompt}\n\nHuman: {prompt}\n\nAssistant:"
            else:
                full_prompt = f"Human: {prompt}\n\nAssistant:"
            
            self.logger.info(" Calling Anthropic API...")
            response = await self.anthropic_client.completions.create(
                model=self.model,
                prompt=full_prompt,
                max_tokens_to_sample=max_tokens or 2000,
                temperature=temperature
            )
            
            result = response.completion.strip()
            self.logger.info(f" Anthropic response: {len(result)} characters")
            return result
            
        except Exception as e:
            self.logger.error(f"Anthropic API error: {e}")
            raise
    
    async def _generate_google_response(
        self,
        prompt: str,
        max_tokens: Optional[int],
        temperature: float,
        system_prompt: Optional[str]
    ) -> str:
        """Generate response using Google Gemini - FIXED with better error handling"""
        try:
            model = genai.GenerativeModel(self.model)
            
            full_prompt = prompt
            if system_prompt:
                full_prompt = f"{system_prompt}\n\n{prompt}"
            
            self.logger.info(" Calling Google Gemini API...")
            response = await model.generate_content_async(
                full_prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=max_tokens or 2000,
                    temperature=temperature
                )
            )
            
            result = response.text.strip()
            self.logger.info(f" Gemini response: {len(result)} characters")
            return result
            
        except Exception as e:
            self.logger.error(f"Google Gemini API error: {e}")
            raise
    
    async def _generate_mock_response(self, prompt: str) -> str:
        """Generate mock response - ONLY when explicitly using mock provider"""
        self.logger.info(" Using mock LLM response (provider=mock)")
        
        prompt_lower = prompt.lower()
        
        # Task prompt generation for android_in_the_wild
        if "task" in prompt_lower and ("user" in prompt_lower or "session" in prompt_lower):
            if "settings" in prompt_lower or "wifi" in prompt_lower:
                return "Turn WiFi on and off to test connectivity"
            elif "clock" in prompt_lower or "alarm" in prompt_lower:
                return "Create a new alarm for 8:00 AM"
            elif "gmail" in prompt_lower or "email" in prompt_lower:
                return "Search for emails from a specific sender"
            elif "notification" in prompt_lower:
                return "Check and clear recent notifications"
            elif "playstore" in prompt_lower or "install" in prompt_lower:
                return "Install a new app from Play Store"
            else:
                return "Complete a basic Android interaction task"
        
        # Planning prompts - return realistic mock plans
        elif ("plan" in prompt_lower or "steps" in prompt_lower) and "wifi" in prompt_lower:
            return '''[
  {
    "step_id": "step_001",
    "description": "Navigate to Settings app",
    "action_type": "navigate",
    "target_element": "settings_app",
    "expected_state": "settings_opened",
    "parameters": {}
  },
  {
    "step_id": "step_002",
    "description": "Find Wi-Fi settings option",
    "action_type": "navigate",
    "target_element": "wifi_settings",
    "expected_state": "wifi_menu_opened",
    "parameters": {}
  },
  {
    "step_id": "step_003",
    "description": "Toggle Wi-Fi switch",
    "action_type": "interact",
    "target_element": "wifi_toggle",
    "expected_state": "wifi_state_changed",
    "parameters": {}
  }
]'''
        
        elif ("plan" in prompt_lower or "steps" in prompt_lower) and "alarm" in prompt_lower:
            return '''[
  {
    "step_id": "step_001",
    "description": "Open Clock application",
    "action_type": "navigate",
    "target_element": "clock_app",
    "expected_state": "clock_opened",
    "parameters": {}
  },
  {
    "step_id": "step_002",
    "description": "Navigate to Alarms section",
    "action_type": "navigate", 
    "target_element": "alarm_tab",
    "expected_state": "alarms_visible",
    "parameters": {}
  },
  {
    "step_id": "step_003",
    "description": "Add new alarm",
    "action_type": "interact",
    "target_element": "add_alarm",
    "expected_state": "alarm_creation",
    "parameters": {}
  }
]'''
        
        # Verification responses
        elif "verification" in prompt_lower or "verify" in prompt_lower:
            return '''{
    "result": "pass",
    "confidence": 0.8,
    "reasoning": "Mock verification indicates expected state achieved",
    "issues_found": [],
    "suggestions": "Continue with next step"
}'''
        
        # Default fallback - but this should rarely be used
        else:
            return '''[
  {
    "step_id": "step_001",
    "description": "Execute basic test action",
    "action_type": "interact",
    "target_element": "screen",
    "expected_state": "action_completed",
    "parameters": {}
  }
]'''
    
    async def _generate_fallback_response(self, prompt: str) -> str:
        """Generate fallback response - ONLY for mock provider"""
        self.logger.warning("⚠️ Using fallback LLM response")
        
        return '''[
  {
    "step_id": "step_001",
    "description": "Fallback test action",
    "action_type": "interact",
    "target_element": "screen",
    "expected_state": "action_completed",
    "parameters": {}
  }
]'''
    
    async def generate_batch_responses(
        self,
        prompts: List[str],
        max_tokens: Optional[int] = None,
        temperature: float = 0.7
    ) -> List[str]:
        """Generate multiple responses in batch"""
        tasks = [
            self.generate_response(prompt, max_tokens, temperature)
            for prompt in prompts
        ]
        
        return await asyncio.gather(*tasks)
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the current model"""
        return {
            "provider": self.provider,
            "model": self.model,
            "config": self.config
        }