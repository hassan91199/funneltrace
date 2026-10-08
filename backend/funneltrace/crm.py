import httpx

from funneltrace.interfaces import CrmError, CrmResult

# Lead category -> HubSpot lifecycle stage (locked in the eval set).
LIFECYCLE_STAGE = {
    "hot": "salesqualifiedlead",
    "warm": "marketingqualifiedlead",
    "cold": "lead",
}

BASE_URL = "https://api.hubapi.com"
CONTACTS = "/crm/v3/objects/contacts"


class HubSpotCrm:
    """The single real CRM adapter: HubSpot contacts over the v3 REST API (private-app token)."""

    name = "hubspot"

    def __init__(self, access_token: str, client: httpx.Client | None = None) -> None:
        if not access_token:
            raise CrmError("HUBSPOT_ACCESS_TOKEN is not set")
        self._client = client or httpx.Client(timeout=15)
        self._headers = {"Authorization": f"Bearer {access_token}"}

    def upsert_contact(self, contact: dict) -> CrmResult:
        properties = self._properties(contact)
        contact_id = contact.get("external_id")
        if not contact_id:
            contact_id = self._find(contact)
        if contact_id:
            self._request("PATCH", f"{CONTACTS}/{contact_id}", {"properties": properties})
            return CrmResult(str(contact_id), "update")
        created = self._request("POST", CONTACTS, {"properties": properties})
        return CrmResult(str(created["id"]), "create")

    @staticmethod
    def _properties(contact: dict) -> dict:
        props: dict = {}
        if contact.get("email"):
            props["email"] = contact["email"]
        if contact.get("phone"):
            props["phone"] = "+" + contact["phone"]
        name = (contact.get("name") or "").strip()
        # A WhatsApp lead with no profile name carries its number as the name.
        if name and not name.lstrip("+").isdigit():
            first, _, last = name.partition(" ")
            props["firstname"] = first
            if last.strip():
                props["lastname"] = last.strip()
        props["lifecyclestage"] = contact["lifecycle_stage"]
        return props

    def _find(self, contact: dict) -> str | None:
        """Look the contact up by email, then by phone (stored in the same +digits form)."""
        searches = []
        if contact.get("email"):
            searches.append(("email", contact["email"]))
        if contact.get("phone"):
            searches.append(("phone", "+" + contact["phone"]))
        for prop, value in searches:
            body = {
                "filterGroups": [
                    {"filters": [{"propertyName": prop, "operator": "EQ", "value": value}]}
                ],
                "limit": 1,
            }
            results = self._request("POST", f"{CONTACTS}/search", body)["results"]
            if results:
                return results[0]["id"]
        return None

    def _request(self, method: str, path: str, body: dict) -> dict:
        try:
            response = self._client.request(
                method, BASE_URL + path, json=body, headers=self._headers
            )
        except httpx.HTTPError as exc:
            raise CrmError(f"HubSpot request failed: {exc}") from exc
        if response.status_code >= 400:
            raise CrmError(f"HubSpot {response.status_code}: {response.text[:300]}")
        return response.json()
