"""Facebook Graph API wrapper (adapted from VersusBot reference)."""

from __future__ import annotations

import facebook

from versusworld.config import Settings


class FaceAPI:
    def __init__(self, token: str | None = None) -> None:
        settings = Settings()
        self.token = token or settings.PAGE_ACCESS_TOKEN
        self.app_id = settings.FB_APP_ID
        self.page_id = settings.FB_PAGE_ID
        self.graph = facebook.GraphAPI(access_token=self.token, version="2.12")

    def get_me(self):
        return self.graph.get_object(id="me", fields="id,name,link")

    def post(self, message: str, image: str) -> str:
        with open(image, "rb") as f:
            response = self.graph.put_photo(image=f, message=message)
        return response["post_id"]

    def latest_posts(self):
        return self.graph.get_object(id="me/posts")["data"]

    def post_reaction_count(self, post_id: str, reaction: str) -> int:
        field = f"reactions.type({str(reaction).upper()}).summary(total_count)"
        reactions = self.graph.get_object(id=post_id, fields=field)
        return reactions["reactions"]["summary"]["total_count"]

    def comment_post(self, post_id: str, message: str) -> None:
        self.graph.put_object(
            parent_object=post_id, connection_name="comments", message=message
        )

    def comment_post_photo(self, post_id: str, image: str, message: str) -> None:
        with open(image, "rb") as f:
            response = self.graph.put_photo(image=f, no_story=True, published=False)
        self.graph.put_object(
            parent_object=post_id,
            connection_name="comments",
            message=message,
            attachment_id=response["id"],
        )
