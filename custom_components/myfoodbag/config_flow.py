"""UI setup and reauthentication."""
import asyncio
import hashlib
import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType
from .api import Client, AuthError, ApiError
from .const import DOMAIN

SCHEMA = vol.Schema({vol.Required("email"): TextSelector(TextSelectorConfig(type=TextSelectorType.EMAIL)),
                     vol.Required("password"): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))})


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        return await self._credentials("user", user_input)

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        return await self._credentials("reauth_confirm", user_input)

    async def _credentials(self, step, user_input):
        errors = {}
        if user_input is not None:
            data = {"email": user_input["email"].strip().lower(), "password": user_input["password"]}
            try:
                client = Client(async_get_clientsession(self.hass), **data)
                profile = await client.get("/customer/profile/me")
                unique = hashlib.sha256(str(profile["customerNumber"]).encode()).hexdigest()
            except AuthError:
                errors["base"] = "invalid_auth"
            except (ApiError, aiohttp.ClientError, asyncio.TimeoutError):
                errors["base"] = "cannot_connect"
            except (KeyError, TypeError, ValueError):
                errors["base"] = "invalid_response"
            else:
                await self.async_set_unique_id(unique)
                if step == "reauth_confirm":
                    self._abort_if_unique_id_mismatch()
                    return self.async_update_reload_and_abort(self._get_reauth_entry(), data_updates=data)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="My Food Bag", data=data)
        return self.async_show_form(step_id=step, data_schema=SCHEMA, errors=errors)
