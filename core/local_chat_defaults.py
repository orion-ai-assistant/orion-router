"""Defaults shared by local chat model seeding and request routing."""

from core.model_catalog import bundled_model


LOCAL_CHAT_MODEL = bundled_model("local", "chat")
LOCAL_CHAT_MODEL_NAME = LOCAL_CHAT_MODEL["name"]
LOCAL_SAMPLING_DEFAULTS = LOCAL_CHAT_MODEL["settings"]["local_sampling"]
LOCAL_TEMPERATURE_DEFAULT = LOCAL_CHAT_MODEL["temperature"]
