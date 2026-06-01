"""OData HTTP client with Basic Auth for 1C/BAS integration."""

import xml.etree.ElementTree as ET
from typing import Any

import httpx
import structlog

log = structlog.get_logger(__name__)

# XML namespace used in OData $metadata responses
_EDMX_NS = "http://schemas.microsoft.com/ado/2007/06/edmx"
_EDM_NS = "http://schemas.microsoft.com/ado/2008/09/edm"


class ODataError(Exception):
    """Raised when 1C OData returns a non-2xx response."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"OData error {status_code}: {message}")


class ODataClient:
    """Async HTTP client for 1C/BAS OData endpoints.

    Wraps httpx.AsyncClient with Basic Auth, JSON headers, and
    structured error handling. One instance is shared for the
    lifetime of the FastAPI application.

    Args:
        base_url: OData service root, e.g.
            ``http://host/Base/odata/standard.odata``.
        user: 1C login.
        password: 1C password.
        timeout: Request timeout in seconds (default 30).
    """

    _EMPTY_DATE = "0001-01-01T00:00:00"
    _SKIP_BOOL_KEYS = frozenset({
        "DeletionMark", "IsFolder", "НеАрхивный", "НедействителенПоНДС",
    })

    def __init__(
        self,
        base_url: str,
        user: str,
        password: str,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            auth=(user, password),
            headers={"Accept": "application/json;odata=verbose"},
            timeout=timeout,
        )

    async def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send GET request to an OData entity path.

        Args:
            path: Relative path, e.g. ``Document_РахунокНаОплату``.
            params: Optional OData query parameters
                (``$filter``, ``$top``, ``$select``, etc.).

        Returns:
            Parsed JSON response body.

        Raises:
            ODataError: On any non-2xx HTTP status.
        """
        url = f"{self._base_url}/{path}"
        log.info("odata_get", url=url, params=params)

        response = await self._client.get(url, params=params)
        return self._handle_response(response)

    async def post(
        self,
        path: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """Send POST request to create an OData entity.

        Args:
            path: Relative path, e.g. ``Document_АктВыполненныхРабот``.
            body: Entity fields to create.

        Returns:
            Parsed JSON response body (created entity).

        Raises:
            ODataError: On any non-2xx HTTP status.
        """
        url = f"{self._base_url}/{path}"
        log.info("odata_post", url=url)

        response = await self._client.post(url, json=body)
        return self._handle_response(response)

    async def fetch_metadata(self) -> list[dict[str, str]]:
        """Fetch and parse OData $metadata XML.

        Requests ``$metadata`` from the service root, parses the EDMX
        XML, and returns a flat list of entity set descriptors.

        Returns:
            List of dicts with keys ``name`` (entity set name) and
            ``entity_type`` (fully-qualified type name), e.g.::

                [
                    {"name": "Document_РахунокНаОплату",
                     "entity_type": "BAS.Document_РахунокНаОплату"},
                    ...
                ]

        Raises:
            ODataError: If the metadata endpoint returns an error.
            ET.ParseError: If the response is not valid XML.
        """
        url = f"{self._base_url}/$metadata"
        log.info("odata_fetch_metadata", url=url)

        response = await self._client.get(
            url,
            headers={"Accept": "application/xml"},
        )
        self._raise_for_status(response)

        entities = self._parse_metadata_xml(response.text)
        log.info("odata_metadata_loaded", entity_count=len(entities))
        return entities

    async def close(self) -> None:
        """Close the underlying httpx client."""
        await self._client.aclose()

    def _handle_response(self, response: httpx.Response) -> dict[str, Any]:
        """Parse JSON body or raise ODataError."""
        self._raise_for_status(response)
        return response.json()

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        """Raise ODataError with a human-readable message on non-2xx."""
        if response.is_success:
            return

        try:
            body = response.json()
            message = (
                body.get("error", {}).get("message", {}).get("value")
                or body.get("error", {}).get("message")
                or response.text
            )
        except Exception:
            message = response.text or response.reason_phrase

        raise ODataError(status_code=response.status_code, message=str(message))

    @staticmethod
    def clean_record(record: dict[str, Any]) -> dict[str, Any]:
        """Remove technical OData fields that have no value for LLM.

        Strips:
        - ``DataVersion`` — internal version hash
        - ``*@navigationLinkUrl`` — OData navigation link annotations
        - ``Predefined``, ``PredefinedDataName`` — service flags
        - ``*_Key`` fields except ``Ref_Key`` — GUID foreign keys without
          human-readable value (LLM cannot use them directly)
        - Empty strings, empty lists, and ``null`` values
        - Date fields equal to the OData epoch default (0001-01-01T00:00:00)
        - Structural boolean fields (DeletionMark, IsFolder, etc.)

        Keeps all meaningful text, numeric, boolean, and date fields.

        Args:
            record: Raw OData entity dict.

        Returns:
            Cleaned dict suitable for LLM consumption.
        """
        result = {}
        for key, value in record.items():
            if key == "DataVersion":
                continue
            if key.endswith("@navigationLinkUrl"):
                continue
            if key in ("Predefined", "PredefinedDataName"):
                continue
            if key.endswith("_Key") and key != "Ref_Key":
                continue
            # Drop empty values — they add noise without information
            if value is None or value == "" or value == []:
                continue
            if value == ODataClient._EMPTY_DATE:
                continue
            if key in ODataClient._SKIP_BOOL_KEYS:
                continue
            result[key] = value
        return result

    @staticmethod
    def _parse_metadata_xml(xml_text: str) -> list[dict[str, str]]:
        """Parse EDMX XML and return entity set list.

        Handles both namespaced and namespace-free EDMX documents so
        the parser works with different 1C/BAS versions.
        """
        root = ET.fromstring(xml_text)

        entity_sets: list[dict[str, str]] = []
        for elem in root.iter():
            local = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if local == "EntitySet":
                name = elem.get("Name", "")
                entity_type = elem.get("EntityType", "")
                if name:
                    entity_sets.append({"name": name, "entity_type": entity_type})

        return entity_sets
