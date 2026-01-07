"""Linear GraphQL API client."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import httpx

from claudear.linear.models import Comment, Issue, User, WorkflowState

logger = logging.getLogger(__name__)


class LinearAPIError(Exception):
    """Error from Linear API."""

    def __init__(self, message: str, errors: list | None = None):
        super().__init__(message)
        self.errors = errors or []


class LinearClient:
    """Client for Linear GraphQL API."""

    ENDPOINT = "https://api.linear.app/graphql"

    def __init__(self, api_key: str):
        """Initialize the Linear client.

        Args:
            api_key: Linear API key for authentication
        """
        self.api_key = api_key
        self._workflow_states: dict[str, dict[str, str]] = {}  # team_id -> {name: id}
        self._state_names: dict[str, str] = {}  # state_id -> name
        self._bot_user_id: Optional[str] = None

    async def _query(
        self, query: str, variables: dict | None = None
    ) -> dict:
        """Execute a GraphQL query.

        Args:
            query: GraphQL query string
            variables: Query variables

        Returns:
            Response data

        Raises:
            LinearAPIError: If the API returns an error
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.ENDPOINT,
                headers={
                    "Authorization": self.api_key,
                    "Content-Type": "application/json",
                },
                json={"query": query, "variables": variables or {}},
                timeout=30.0,
            )
            response.raise_for_status()
            result = response.json()

            if "errors" in result:
                errors = result["errors"]
                message = errors[0].get("message", "Unknown error") if errors else "Unknown error"
                raise LinearAPIError(message, errors)

            return result.get("data", {})

    async def get_bot_user_id(self) -> str:
        """Get the ID of the authenticated user (bot).

        Returns:
            User ID string
        """
        if self._bot_user_id:
            return self._bot_user_id

        query = """
        query Viewer {
            viewer {
                id
                name
            }
        }
        """
        result = await self._query(query)
        self._bot_user_id = result["viewer"]["id"]
        return self._bot_user_id

    async def get_workflow_states(self, team_id: str) -> dict[str, str]:
        """Get workflow states for a team.

        Args:
            team_id: Linear team ID

        Returns:
            Dict mapping state name to state ID
        """
        if team_id in self._workflow_states:
            return self._workflow_states[team_id]

        query = """
        query WorkflowStates($teamId: String!) {
            team(id: $teamId) {
                states {
                    nodes {
                        id
                        name
                        type
                    }
                }
            }
        }
        """
        result = await self._query(query, {"teamId": team_id})
        states = result["team"]["states"]["nodes"]

        state_map = {}
        for state in states:
            state_map[state["name"]] = state["id"]
            self._state_names[state["id"]] = state["name"]

        self._workflow_states[team_id] = state_map
        return state_map

    async def get_state_name(self, state_id: str) -> Optional[str]:
        """Get the name of a workflow state by ID.

        Args:
            state_id: Workflow state ID

        Returns:
            State name or None if not found
        """
        if state_id in self._state_names:
            return self._state_names[state_id]

        # Query for this specific state
        query = """
        query WorkflowState($id: String!) {
            workflowState(id: $id) {
                id
                name
                type
            }
        }
        """
        try:
            result = await self._query(query, {"id": state_id})
            state = result.get("workflowState")
            if state:
                self._state_names[state["id"]] = state["name"]
                return state["name"]
        except LinearAPIError:
            pass
        return None

    async def get_issue(self, issue_id: str) -> Optional[Issue]:
        """Get an issue by ID.

        Args:
            issue_id: Linear issue ID

        Returns:
            Issue model or None if not found
        """
        query = """
        query Issue($id: String!) {
            issue(id: $id) {
                id
                identifier
                title
                description
                priority
                state {
                    id
                    name
                    type
                }
                assignee {
                    id
                    name
                    email
                }
                team {
                    id
                    name
                    key
                }
                createdAt
                updatedAt
            }
        }
        """
        result = await self._query(query, {"id": issue_id})
        issue_data = result.get("issue")
        if issue_data:
            return Issue(**issue_data)
        return None

    async def update_issue_state(
        self, issue_id: str, state_name: str, team_id: Optional[str] = None
    ) -> bool:
        """Update an issue's workflow state.

        Args:
            issue_id: Linear issue ID
            state_name: Name of the target state (e.g., "In Progress")
            team_id: Team ID to look up states (optional, will fetch issue if not provided)

        Returns:
            True if successful
        """
        # Get team_id from issue if not provided
        if not team_id:
            issue = await self.get_issue(issue_id)
            if not issue or not issue.team:
                raise LinearAPIError(f"Cannot find team for issue {issue_id}")
            team_id = issue.team.id

        # Get state ID
        states = await self.get_workflow_states(team_id)
        state_id = states.get(state_name)
        if not state_id:
            raise LinearAPIError(f"Unknown state: {state_name}")

        mutation = """
        mutation UpdateIssue($id: String!, $stateId: String!) {
            issueUpdate(id: $id, input: { stateId: $stateId }) {
                success
                issue {
                    id
                    state {
                        name
                    }
                }
            }
        }
        """
        result = await self._query(mutation, {"id": issue_id, "stateId": state_id})
        success = result.get("issueUpdate", {}).get("success", False)

        if success:
            logger.info(f"Updated issue {issue_id} to state '{state_name}'")
        else:
            logger.warning(f"Failed to update issue {issue_id} to state '{state_name}'")

        return success

    async def post_comment(self, issue_id: str, body: str) -> Optional[Comment]:
        """Post a comment on an issue.

        Args:
            issue_id: Linear issue ID
            body: Comment body (markdown supported)

        Returns:
            Comment model if successful
        """
        mutation = """
        mutation CreateComment($issueId: String!, $body: String!) {
            commentCreate(input: { issueId: $issueId, body: $body }) {
                success
                comment {
                    id
                    body
                    createdAt
                    user {
                        id
                        name
                    }
                }
            }
        }
        """
        result = await self._query(mutation, {"issueId": issue_id, "body": body})
        comment_result = result.get("commentCreate", {})

        if comment_result.get("success") and comment_result.get("comment"):
            logger.info(f"Posted comment on issue {issue_id}")
            return Comment(**comment_result["comment"])

        logger.warning(f"Failed to post comment on issue {issue_id}")
        return None

    async def get_comments(self, issue_id: str) -> list[Comment]:
        """Get all comments on an issue.

        Args:
            issue_id: Linear issue ID

        Returns:
            List of comments
        """
        query = """
        query IssueComments($id: String!) {
            issue(id: $id) {
                comments {
                    nodes {
                        id
                        body
                        createdAt
                        user {
                            id
                            name
                        }
                    }
                }
            }
        }
        """
        result = await self._query(query, {"id": issue_id})
        comments_data = result.get("issue", {}).get("comments", {}).get("nodes", [])
        return [Comment(**c) for c in comments_data]

    async def get_comments_since(
        self, issue_id: str, since: datetime
    ) -> list[Comment]:
        """Get comments posted after a specific time.

        Args:
            issue_id: Linear issue ID
            since: Only return comments created after this time

        Returns:
            List of comments created after the specified time
        """
        all_comments = await self.get_comments(issue_id)
        return [c for c in all_comments if c.created_at > since]

    async def get_new_human_comments(
        self, issue_id: str, since: datetime
    ) -> list[Comment]:
        """Get new comments from humans (not the bot).

        Args:
            issue_id: Linear issue ID
            since: Only return comments created after this time

        Returns:
            List of human comments created after the specified time
        """
        bot_id = await self.get_bot_user_id()
        comments = await self.get_comments_since(issue_id, since)
        return [c for c in comments if c.user and c.user.id != bot_id]

    async def create_webhook(
        self, url: str, team_id: str, resource_types: list[str] | None = None
    ) -> dict:
        """Create a webhook subscription.

        Args:
            url: Webhook endpoint URL
            team_id: Team ID to receive events for
            resource_types: Types to subscribe to (default: ["Issue"])

        Returns:
            Webhook data including ID and secret
        """
        if resource_types is None:
            resource_types = ["Issue"]

        mutation = """
        mutation CreateWebhook($url: String!, $teamId: String!, $resourceTypes: [String!]!) {
            webhookCreate(input: {
                url: $url
                teamId: $teamId
                resourceTypes: $resourceTypes
            }) {
                success
                webhook {
                    id
                    url
                    secret
                    enabled
                }
            }
        }
        """
        result = await self._query(
            mutation,
            {"url": url, "teamId": team_id, "resourceTypes": resource_types},
        )
        return result.get("webhookCreate", {})
