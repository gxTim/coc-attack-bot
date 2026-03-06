"""
AI Analyzer - Google Gemini integration for base analysis
"""

import os
import base64
import json
import requests
from typing import Dict, List, Optional
from PIL import Image
import io

class AIAnalyzer:
    """Google Gemini AI analyzer for COC base evaluation"""
    
    _BASE_URL_TEMPLATE = (
        "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    )
    _DEFAULT_MODEL = "gemini-2.5-flash-lite"
    _AVAILABLE_MODELS = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.5-pro"]

    def _log_404_error(self) -> None:
        """Log a helpful message when the API returns a 404 (deprecated model)."""
        available = ", ".join(self._AVAILABLE_MODELS)
        self.logger.error(
            f"❌ Gemini API returned 404. The model '{self.model}' may be deprecated. "
            f"Update 'ai_analyzer.model' in config.json. "
            f"Available models: {available}"
        )

    def __init__(self, api_key: str, logger, model: str = ""):
        self.api_key = api_key
        self.logger = logger
        self.model = model or self._DEFAULT_MODEL
        self.base_url = self._BASE_URL_TEMPLATE.format(model=self.model)
        
        if not self.api_key:
            self.logger.warning(
                "⚠️ AI Analyzer: No API key provided. "
                "Set 'ai_analyzer.google_gemini_api_key' in config.json or disable AI analysis."
            )
    
    def analyze_base(self, screenshot_path: str, min_gold: int = 300000, 
                    min_elixir: int = 300000, min_dark: int = 2000,
                    max_th_level: int = 16) -> Dict:
        """
        Analyze enemy base screenshot using Google Gemini
        
        Args:
            screenshot_path: Path to screenshot file
            min_gold: Minimum gold requirement
            min_elixir: Minimum elixir requirement  
            min_dark: Minimum dark elixir requirement
            max_th_level: Maximum Town Hall level to attack (inclusive)
            
        Returns:
            Dict with analysis results and attack recommendation
        """
        try:
            self.logger.info(f"🤖 Analyzing base with AI: {screenshot_path}")
            
            if not self.api_key:
                return self._create_error_response("No API key configured")
            
            # Encode image to base64
            image_data = self._encode_image(screenshot_path)
            if not image_data:
                return self._create_error_response("Failed to encode image")
            
            # Create analysis prompt with requirements
            prompt = self._create_analysis_prompt(min_gold, min_elixir, min_dark, max_th_level)
            
            # Send request to Gemini
            response = self._send_gemini_request(image_data, prompt)
            
            if response:
                self.logger.info(f"✅ AI Analysis: {response['recommendation']} - {response['reasoning']}")
                return response
            else:
                return self._create_error_response("Failed to get AI response")
                
        except Exception as e:
            self.logger.error(f"AI analysis error: {e}")
            return self._create_error_response(f"Analysis error: {e}")
    
    def _encode_image(self, image_path: str) -> Optional[str]:
        """Encode image to base64 for Gemini API"""
        try:
            with open(image_path, 'rb') as image_file:
                # Resize image if too large (Gemini has size limits)
                img = Image.open(image_file)
                
                # Resize if width > 1024px to reduce API payload
                if img.width > 1024:
                    ratio = 1024 / img.width
                    new_height = int(img.height * ratio)
                    img = img.resize((1024, new_height), Image.Resampling.LANCZOS)
                
                # Convert to bytes
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='PNG')
                img_byte_arr = img_byte_arr.getvalue()
                
                # Encode to base64
                return base64.b64encode(img_byte_arr).decode('utf-8')
                
        except Exception as e:
            self.logger.error(f"Image encoding error: {e}")
            return None
    
    def _create_analysis_prompt(self, min_gold: int, min_elixir: int, min_dark: int, max_th_level: int = 16) -> str:
        """Create analysis prompt with current requirements"""
        too_strong_level = max_th_level + 1
        return f"""
You are an expert Clash of Clans player analyzing enemy bases for attack decisions.

CRITICAL: You must read the EXACT loot numbers displayed in the top-left area of the screen.

Current loot requirements:
- Minimum Gold: {min_gold:,}
- Minimum Elixir: {min_elixir:,}  
- Minimum Dark Elixir: {min_dark:,}

INSTRUCTIONS:
1. Look at the "Available Loot:" section in the top-left corner of the screenshot
2. Read the EXACT numbers next to the gold coin (yellow), elixir drop (pink), and dark elixir drop (black) icons
3. Identify the Town Hall level by looking at the Town Hall building
4. Compare loot numbers to minimum requirements above
5. Make recommendation based on loot AND Town Hall level

LOOT READING RULES:
- Gold is shown next to a yellow coin icon
- Elixir is shown next to a pink/purple drop icon  
- Dark Elixir is shown next to a black drop icon
- Numbers may have spaces (e.g. "123 456" = 123,456)
- Be extremely careful reading the digits

TOWN HALL RULES:
- Town Hall {too_strong_level}+ are TOO STRONG - always SKIP these
- Only attack Town Hall {max_th_level} and below
- Look at the Town Hall building design to identify the level

DECISION CRITERIA:
- ATTACK only if: ALL loot types meet requirements AND Town Hall is level {max_th_level} or below
- SKIP if: ANY loot type is below requirements OR Town Hall is level {too_strong_level}+
- Do NOT consider base difficulty - focus ONLY on loot amounts and Town Hall level

Examples:
- Gold: 19,015 (need 500,000) → SKIP (loot too low)
- Town Hall {too_strong_level} → SKIP (too strong regardless of loot)
- Town Hall {max_th_level} with good loot → ATTACK
- Town Hall {max_th_level - 1} with good loot → ATTACK

Respond in this exact JSON format:
{{
    "loot": {{
        "gold": actual_gold_amount_you_read,
        "elixir": actual_elixir_amount_you_read,
        "dark_elixir": actual_dark_elixir_amount_you_read
    }},
    "townhall_level": town_hall_level_number,
    "difficulty": "Easy/Medium/Hard",
    "recommendation": "ATTACK/SKIP",
    "reasoning": "Specific reason: Gold X vs required Y, Elixir A vs required B, Dark C vs required D, TH level E"
}}
"""
    
    def _send_gemini_request(self, image_data: str, prompt: str) -> Optional[Dict]:
        """Send request to Google Gemini API"""
        try:
            headers = {
                'Content-Type': 'application/json',
            }
            
            payload = {
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": "image/png",
                                "data": image_data
                            }
                        }
                    ]
                }],
                "generationConfig": {
                    "temperature": 0.1,  # Low temperature for consistent analysis
                    "topK": 1,
                    "topP": 1,
                    "maxOutputTokens": 1024,
                }
            }
            
            url = f"{self.base_url}?key={self.api_key}"
            
            self.logger.info("🌐 Sending request to Gemini API...")
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                
                # Extract text from response
                if 'candidates' in result and len(result['candidates']) > 0:
                    content = result['candidates'][0]['content']['parts'][0]['text']
                    
                    # Parse JSON response
                    try:
                        # Clean up response (remove markdown formatting if present)
                        content = content.strip()
                        if content.startswith('```json'):
                            content = content[7:]
                        if content.endswith('```'):
                            content = content[:-3]
                        content = content.strip()
                        
                        analysis = json.loads(content)
                        return analysis
                        
                    except json.JSONDecodeError as e:
                        self.logger.error(f"Failed to parse AI response as JSON: {e}")
                        self.logger.error(f"Raw response: {content}")
                        return None
                else:
                    self.logger.error("No candidates in Gemini response")
                    return None
            elif response.status_code == 404:
                self._log_404_error()
                return None
            else:
                self.logger.error(f"Gemini API error: {response.status_code} - {response.text}")
                return None
                
        except requests.exceptions.Timeout:
            self.logger.error("Gemini API request timeout")
            return None
        except Exception as e:
            self.logger.error(f"Gemini API request error: {e}")
            return None
    
    def _create_error_response(self, error_msg: str) -> Dict:
        """Create error response with SKIP recommendation"""
        return {
            "loot": {"gold": 0, "elixir": 0, "dark_elixir": 0},
            "townhall_level": 0,
            "difficulty": "Unknown",
            "recommendation": "SKIP",
            "reasoning": f"Error: {error_msg}",
            "error": True
        }
    
    def select_strategy(self, screenshot_path: str, strategies: List[Dict]) -> Dict:
        """Use AI to select the best attack strategy for this base.

        Args:
            screenshot_path: Path to the enemy base screenshot.
            strategies: List of strategy dicts, each with keys:
                ``name`` (str), ``description`` (str), and ``session_name`` (str).

        Returns:
            Dict with ``selected_strategy`` (session_name str) and
            ``reasoning`` (str).  On error falls back to the first strategy.
        """
        if not strategies:
            return {"selected_strategy": "", "reasoning": "No strategies available", "error": True}

        if len(strategies) == 1:
            return {
                "selected_strategy": strategies[0].get("session_name", ""),
                "reasoning": "Only one strategy available — selected automatically.",
            }

        try:
            if not self.api_key:
                raise ValueError("No API key configured")

            image_data = self._encode_image(screenshot_path)
            if not image_data:
                raise ValueError("Failed to encode image")

            strategy_list_text = "\n".join(
                f'- "{s["session_name"]}": {s.get("description", s.get("name", s["session_name"]))}'
                for s in strategies
            )
            prompt = f"""You are a Clash of Clans strategy expert.
Given this enemy base screenshot and the available attack strategies, select the BEST strategy.

Available strategies:
{strategy_list_text}

Analyze the base layout and recommend which strategy to use.
Consider:
- Air defense placement and levels (for air attacks)
- Wall layout (for ground attacks)
- Collector/storage placement (for farming raids)
- Base compactness

Respond in JSON only (no markdown):
{{
    "selected_strategy": "<session_name from the list above>",
    "reasoning": "Brief explanation why this strategy fits"
}}"""

            response = self._send_gemini_request(image_data, prompt)
            if response and "selected_strategy" in response:
                # Validate the returned strategy name
                valid_names = {s["session_name"] for s in strategies}
                if response["selected_strategy"] in valid_names:
                    return response
                self.logger.warning(
                    f"⚠️ AI selected unknown strategy '{response['selected_strategy']}'; falling back."
                )

            # Fallback: return first strategy
            return {
                "selected_strategy": strategies[0].get("session_name", ""),
                "reasoning": "Fallback: AI response was invalid.",
            }

        except Exception as e:
            self.logger.error(f"Strategy selection error: {e}")
            return {
                "selected_strategy": strategies[0].get("session_name", "") if strategies else "",
                "reasoning": f"Fallback due to error: {e}",
                "error": True,
            }

    def test_connection(self) -> bool:
        """Test connection to Gemini API"""
        try:
            # Create a simple test request
            headers = {'Content-Type': 'application/json'}
            payload = {
                "contents": [{"parts": [{"text": "Hello, respond with 'OK'"}]}],
                "generationConfig": {"maxOutputTokens": 10}
            }
            
            url = f"{self.base_url}?key={self.api_key}"
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            
            if response.status_code == 200:
                self.logger.info("✅ Gemini API connection successful")
                return True
            elif response.status_code == 404:
                self._log_404_error()
                return False
            else:
                self.logger.error(f"❌ Gemini API test failed: {response.status_code}")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Gemini API test error: {e}")
            return False