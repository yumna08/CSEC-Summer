"""Conversation memory with a database-backed store and safe offline fallback."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import delete, select

from app.core.config import CHAT_HISTORY_TURNS, CHAT_RETENTION_DAYS
from app.db.database import Base, SessionLocal, get_engine, get_session_factory
from app.db.models import ChatMessage, ChatSession, utc_now

logger = logging.getLogger(__name__)


class ChatMemoryStore:
    """Persist chat turns without making chat unavailable when the DB is down."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._memory_sessions: Dict[str, Dict[str, Any]] = {}
        self._database_unavailable = False

    def _mark_database_unavailable(self, error: Exception) -> None:
        if not self._database_unavailable:
            logger.warning(
                "Conversation database unavailable; using in-memory chat memory fallback (%s)",
                error.__class__.__name__,
            )
        self._database_unavailable = True

    def _database_session(self):
        if self._database_unavailable:
            return None
        try:
            # This is additive and checkfirst=True, so it also initializes the
            # conversation tables for deployments without a migration runner.
            Base.metadata.create_all(bind=get_engine(), checkfirst=True)
            return get_session_factory()()
        except Exception as error:
            self._mark_database_unavailable(error)
            return None

    @staticmethod
    def _new_session_id() -> str:
        return str(uuid4())

    def _ensure_memory_session(self, session_id: str) -> Dict[str, Any]:
        with self._lock:
            return self._memory_sessions.setdefault(
                session_id,
                {"created_at": datetime.now(timezone.utc), "messages": []},
            )

    def get_or_create_session(self, requested_id: Optional[str] = None) -> str:
        """Return an existing session or a fresh UUID for an unknown id."""
        db = self._database_session()
        if db is not None:
            try:
                with db:
                    if requested_id:
                        existing = db.execute(
                            select(ChatSession).where(ChatSession.id == requested_id)
                        ).scalar_one_or_none()
                        if existing is not None:
                            return existing.id

                    session_id = self._new_session_id()
                    db.add(ChatSession(id=session_id))
                    db.commit()
                    return session_id
            except Exception as error:
                self._mark_database_unavailable(error)

        with self._lock:
            if requested_id and requested_id in self._memory_sessions:
                return requested_id
            session_id = self._new_session_id()
            self._memory_sessions[session_id] = {
                "created_at": datetime.now(timezone.utc),
                "messages": [],
            }
            return session_id

    def get_recent_history(
        self,
        session_id: str,
        turns: int = CHAT_HISTORY_TURNS,
    ) -> List[Dict[str, Any]]:
        """Return at most ``turns`` user/assistant turns, oldest first."""
        max_messages = max(0, turns) * 2
        if max_messages == 0:
            return []

        db = self._database_session()
        if db is not None:
            try:
                with db:
                    rows = list(
                        db.execute(
                            select(ChatMessage)
                            .where(ChatMessage.session_id == session_id)
                            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
                            .limit(max_messages)
                        ).scalars()
                    )
                    return [self._message_dict(row) for row in reversed(rows)]
            except Exception as error:
                self._mark_database_unavailable(error)

        with self._lock:
            messages = self._memory_sessions.get(session_id, {}).get("messages", [])
            return [dict(message) for message in messages[-max_messages:]]

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        cited_source_ids: Optional[List[str]] = None,
    ) -> None:
        source_ids = list(cited_source_ids or []) if role == "assistant" else None
        db = self._database_session()
        if db is not None:
            try:
                with db:
                    existing = db.execute(
                        select(ChatSession).where(ChatSession.id == session_id)
                    ).scalar_one_or_none()
                    if existing is None:
                        # This can happen if a client deletes a session between
                        # request steps. Recreate only the exact server id.
                        db.add(ChatSession(id=session_id))
                    else:
                        existing.updated_at = utc_now()
                    db.add(
                        ChatMessage(
                            session_id=session_id,
                            role=role,
                            content=content,
                            cited_source_ids=source_ids,
                        )
                    )
                    db.commit()
                    return
            except Exception as error:
                self._mark_database_unavailable(error)

        with self._lock:
            session = self._ensure_memory_session(session_id)
            session["messages"].append(
                {
                    "role": role,
                    "content": content,
                    "cited_source_ids": source_ids or [],
                }
            )

    def delete_session(self, session_id: str) -> bool:
        db = self._database_session()
        if db is not None:
            try:
                with db:
                    result = db.execute(
                        delete(ChatSession).where(ChatSession.id == session_id)
                    )
                    db.commit()
                    deleted = bool(result.rowcount)
                    with self._lock:
                        self._memory_sessions.pop(session_id, None)
                    return deleted
            except Exception as error:
                self._mark_database_unavailable(error)

        with self._lock:
            return self._memory_sessions.pop(session_id, None) is not None

    def purge_expired(self, retention_days: int = CHAT_RETENTION_DAYS) -> int:
        if retention_days <= 0:
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        db = self._database_session()
        if db is not None:
            try:
                with db:
                    result = db.execute(
                        delete(ChatSession).where(ChatSession.updated_at < cutoff)
                    )
                    db.commit()
                    deleted = int(result.rowcount or 0)
                    with self._lock:
                        expired = [
                            sid
                            for sid, value in self._memory_sessions.items()
                            if value["created_at"] < cutoff
                        ]
                        for sid in expired:
                            self._memory_sessions.pop(sid, None)
                    return deleted + len(expired)
            except Exception as error:
                self._mark_database_unavailable(error)

        with self._lock:
            expired = [
                sid
                for sid, value in self._memory_sessions.items()
                if value["created_at"] < cutoff
            ]
            for sid in expired:
                self._memory_sessions.pop(sid, None)
            return len(expired)

    def reset_for_testing(self) -> None:
        with self._lock:
            self._memory_sessions.clear()
            self._database_unavailable = False

    @staticmethod
    def _message_dict(message: ChatMessage) -> Dict[str, Any]:
        return {
            "role": message.role,
            "content": message.content,
            "cited_source_ids": list(message.cited_source_ids or []),
        }


chat_memory = ChatMemoryStore()
