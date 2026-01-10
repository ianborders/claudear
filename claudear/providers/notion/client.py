"""Notion API client for database and page operations."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

NOTION_API_VERSION = "2022-06-28"
NOTION_BASE_URL = "https://api.notion.com/v1"


class NotionAPIError(Exception):
    """Error during Notion API operations."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        body: Optional[dict] = None,
    ):
        self.status_code = status_code
        self.body = body
        super().__init__(message)


@dataclass
class NotionPage:
    """Represents a Notion page/task."""

    id: str
    database_id: str  # Track which database this page belongs to
    title: str
    status: Optional[str] = None
    blocked: bool = False
    current_status: Optional[str] = None
    claudear_id: Optional[str] = None  # Renamed from clotion_id
    branch: Optional[str] = None
    pr_url: Optional[str] = None
    created_time: Optional[datetime] = None
    last_edited_time: Optional[datetime] = None
    url: Optional[str] = None

    @classmethod
    def from_api_response(cls, data: dict, database_id: str = "") -> "NotionPage":
        """Create a NotionPage from API response data.

        Args:
            data: Raw API response for a page
            database_id: Database ID this page belongs to

        Returns:
            NotionPage instance
        """
        properties = data.get("properties", {})

        # Extract database_id from parent if not provided
        if not database_id:
            parent = data.get("parent", {})
            if parent.get("type") == "database_id":
                database_id = parent.get("database_id", "")

        # Extract title from title property (usually called "Name" or "Title")
        title = ""
        for prop_name, prop_data in properties.items():
            if prop_data.get("type") == "title":
                title_content = prop_data.get("title", [])
                if title_content:
                    title = title_content[0].get("plain_text", "")
                break

        # Extract status (supports both 'status' and 'select' types)
        status = None
        status_prop = properties.get("Status", {})
        if status_prop.get("type") == "status":
            status_data = status_prop.get("status")
            if status_data:
                status = status_data.get("name")
        elif status_prop.get("type") == "select":
            select = status_prop.get("select")
            if select:
                status = select.get("name")

        # Extract blocked checkbox
        blocked = False
        blocked_prop = properties.get("Blocked", {})
        if blocked_prop.get("type") == "checkbox":
            blocked = blocked_prop.get("checkbox", False)

        # Extract current status text
        current_status = None
        current_status_prop = properties.get("Current Status", {})
        if current_status_prop.get("type") == "rich_text":
            rich_text = current_status_prop.get("rich_text", [])
            if rich_text:
                current_status = rich_text[0].get("plain_text")

        # Extract Claudear ID (check both Claudear ID and Clotion ID for backward compat)
        claudear_id = None
        for id_prop_name in ["Claudear ID", "Clotion ID"]:
            id_prop = properties.get(id_prop_name, {})
            if id_prop.get("type") == "rich_text":
                rich_text = id_prop.get("rich_text", [])
                if rich_text:
                    claudear_id = rich_text[0].get("plain_text")
                    break

        # Extract branch
        branch = None
        branch_prop = properties.get("Branch", {})
        if branch_prop.get("type") == "rich_text":
            rich_text = branch_prop.get("rich_text", [])
            if rich_text:
                branch = rich_text[0].get("plain_text")

        # Extract PR URL
        pr_url = None
        pr_url_prop = properties.get("PR URL", {})
        if pr_url_prop.get("type") == "url":
            pr_url = pr_url_prop.get("url")

        return cls(
            id=data["id"],
            database_id=database_id,
            title=title,
            status=status,
            blocked=blocked,
            current_status=current_status,
            claudear_id=claudear_id,
            branch=branch,
            pr_url=pr_url,
            created_time=datetime.fromisoformat(
                data["created_time"].replace("Z", "+00:00")
            )
            if data.get("created_time")
            else None,
            last_edited_time=datetime.fromisoformat(
                data["last_edited_time"].replace("Z", "+00:00")
            )
            if data.get("last_edited_time")
            else None,
            url=data.get("url"),
        )


@dataclass
class NotionComment:
    """Represents a Notion comment."""

    id: str
    text: str
    created_time: datetime
    created_by_id: Optional[str] = None


class NotionClient:
    """Client for Notion API operations.

    Supports multi-database operations with a single API key.
    """

    def __init__(self, api_key: str):
        """Initialize the Notion client.

        Args:
            api_key: Notion integration API key (starts with secret_)
        """
        self.api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=NOTION_BASE_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Notion-Version": NOTION_API_VERSION,
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
        self._bot_user_id: Optional[str] = None

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        endpoint: str,
        json: Optional[dict] = None,
    ) -> dict:
        """Make an API request.

        Args:
            method: HTTP method
            endpoint: API endpoint (without base URL)
            json: Request body

        Returns:
            Response JSON

        Raises:
            NotionAPIError: If request fails
        """
        try:
            response = await self._client.request(method, endpoint, json=json)

            if response.status_code >= 400:
                try:
                    body = response.json()
                except Exception:
                    body = {"error": response.text}
                raise NotionAPIError(
                    f"Notion API error: {response.status_code} - {body.get('message', body)}",
                    status_code=response.status_code,
                    body=body,
                )

            return response.json()

        except httpx.RequestError as e:
            raise NotionAPIError(f"Request failed: {e}")

    async def get_bot_user_id(self) -> str:
        """Get the bot user ID.

        Returns:
            Bot user ID
        """
        if self._bot_user_id:
            return self._bot_user_id

        data = await self._request("GET", "/users/me")
        self._bot_user_id = data["id"]
        return self._bot_user_id

    # Database operations

    async def get_database(self, database_id: str) -> dict:
        """Get database information.

        Args:
            database_id: Database ID

        Returns:
            Database metadata
        """
        return await self._request("GET", f"/databases/{database_id}")

    async def query_pages(
        self,
        database_id: str,
        filter: Optional[dict] = None,
        sorts: Optional[list] = None,
        page_size: int = 100,
    ) -> list[NotionPage]:
        """Query pages from a database.

        Args:
            database_id: Database ID to query
            filter: Optional filter conditions
            sorts: Optional sort conditions
            page_size: Number of results per page

        Returns:
            List of NotionPage objects
        """
        body: dict[str, Any] = {"page_size": page_size}
        if filter:
            body["filter"] = filter
        if sorts:
            body["sorts"] = sorts

        data = await self._request(
            "POST", f"/databases/{database_id}/query", json=body
        )

        pages = []
        for result in data.get("results", []):
            try:
                pages.append(NotionPage.from_api_response(result, database_id))
            except Exception as e:
                logger.warning(f"Failed to parse page {result.get('id')}: {e}")

        return pages

    async def get_page(self, page_id: str) -> NotionPage:
        """Get a specific page.

        Args:
            page_id: Page ID

        Returns:
            NotionPage object
        """
        data = await self._request("GET", f"/pages/{page_id}")
        return NotionPage.from_api_response(data)

    # Property updates

    async def update_page_properties(
        self, page_id: str, properties: dict
    ) -> NotionPage:
        """Update page properties.

        Args:
            page_id: Page ID
            properties: Properties to update (Notion API format)

        Returns:
            Updated NotionPage
        """
        data = await self._request(
            "PATCH", f"/pages/{page_id}", json={"properties": properties}
        )
        return NotionPage.from_api_response(data)

    async def set_status(self, page_id: str, status: str) -> NotionPage:
        """Set the Status property.

        Args:
            page_id: Page ID
            status: Status value (e.g., "Todo", "In Progress")

        Returns:
            Updated page
        """
        return await self.update_page_properties(
            page_id,
            {"Status": {"status": {"name": status}}},
        )

    async def set_blocked(self, page_id: str, is_blocked: bool) -> NotionPage:
        """Set the Blocked checkbox property.

        Args:
            page_id: Page ID
            is_blocked: Whether task is blocked

        Returns:
            Updated page
        """
        return await self.update_page_properties(
            page_id,
            {"Blocked": {"checkbox": is_blocked}},
        )

    async def set_current_status(
        self, page_id: str, text: Optional[str]
    ) -> NotionPage:
        """Set the Current Status text property.

        Args:
            page_id: Page ID
            text: Status text (e.g., "Reading files...")

        Returns:
            Updated page
        """
        if text:
            content = [{"type": "text", "text": {"content": text}}]
        else:
            content = []

        return await self.update_page_properties(
            page_id,
            {"Current Status": {"rich_text": content}},
        )

    async def set_claudear_id(self, page_id: str, claudear_id: str) -> NotionPage:
        """Set the Claudear ID property.

        Args:
            page_id: Page ID
            claudear_id: Claudear task ID (e.g., "CLO-001")

        Returns:
            Updated page
        """
        return await self.update_page_properties(
            page_id,
            {
                "Claudear ID": {
                    "rich_text": [{"type": "text", "text": {"content": claudear_id}}]
                }
            },
        )

    async def set_branch(self, page_id: str, branch: str) -> NotionPage:
        """Set the Branch property.

        Args:
            page_id: Page ID
            branch: Git branch name

        Returns:
            Updated page
        """
        return await self.update_page_properties(
            page_id,
            {"Branch": {"rich_text": [{"type": "text", "text": {"content": branch}}]}},
        )

    async def set_pr_url(self, page_id: str, url: str) -> NotionPage:
        """Set the PR URL property.

        Args:
            page_id: Page ID
            url: GitHub PR URL

        Returns:
            Updated page
        """
        return await self.update_page_properties(
            page_id,
            {"PR URL": {"url": url}},
        )

    # Comments

    async def add_comment(self, page_id: str, text: str) -> dict:
        """Add a comment to a page.

        Args:
            page_id: Page ID
            text: Comment text

        Returns:
            Comment data
        """
        return await self._request(
            "POST",
            "/comments",
            json={
                "parent": {"page_id": page_id},
                "rich_text": [{"type": "text", "text": {"content": text}}],
            },
        )

    async def get_comments(self, page_id: str) -> list[NotionComment]:
        """Get comments for a page.

        Args:
            page_id: Page ID

        Returns:
            List of comments
        """
        data = await self._request(
            "GET",
            f"/comments?block_id={page_id}",
        )

        comments = []
        for result in data.get("results", []):
            text = ""
            rich_text = result.get("rich_text", [])
            for rt in rich_text:
                text += rt.get("plain_text", "")

            comments.append(
                NotionComment(
                    id=result["id"],
                    text=text,
                    created_time=datetime.fromisoformat(
                        result["created_time"].replace("Z", "+00:00")
                    ),
                    created_by_id=result.get("created_by", {}).get("id"),
                )
            )

        return comments

    async def get_new_human_comments(
        self, page_id: str, since: datetime
    ) -> list[NotionComment]:
        """Get new human (non-bot) comments since a timestamp.

        Args:
            page_id: Page ID
            since: Only return comments after this time

        Returns:
            List of new human comments
        """
        bot_id = await self.get_bot_user_id()
        all_comments = await self.get_comments(page_id)

        return [
            c
            for c in all_comments
            if c.created_time > since and c.created_by_id != bot_id
        ]

    # Database property management

    async def update_database_properties(
        self, database_id: str, properties: dict
    ) -> dict:
        """Update database properties (schema).

        Args:
            database_id: Database ID
            properties: Properties to add/update

        Returns:
            Updated database
        """
        return await self._request(
            "PATCH",
            f"/databases/{database_id}",
            json={"properties": properties},
        )
