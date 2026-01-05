import json
import os
from functools import lru_cache
from typing import Any, Dict

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")


@lru_cache(maxsize=1)
def _load_config() -> Dict[str, Any]:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as config_file:
        return json.load(config_file)


def get_openai_api_url() -> str:
    return _load_config().get("openai_api_url", "https://api.openai.com/v1/chat/completions")


def get_agent_config(agent_name: str) -> Dict[str, Any]:
    agents = _load_config().get("agents", {})
    agent_config = agents.get(agent_name)
    if agent_config is None:
        raise KeyError(f"Missing configuration for agent '{agent_name}'")
    return agent_config


def get_prompt_path(module_file: str, prompt_file: str) -> str:
    prompt_path = os.path.abspath(os.path.join(os.path.dirname(module_file), "prompts", prompt_file))
    if not os.path.isfile(prompt_path):
        raise FileNotFoundError(f"Prompt file '{prompt_file}' not found for module '{module_file}'")
    return prompt_path


def load_prompt_text(module_file: str, prompt_file: str) -> str:
    prompt_path = get_prompt_path(module_file, prompt_file)
    with open(prompt_path, "r", encoding="utf-8") as prompt_handle:
        return prompt_handle.read()
