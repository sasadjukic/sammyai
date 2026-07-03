"""
Chat Session Manager for LLM integration.
Manages chat sessions, message history, and conversation state.
"""

from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json
import os
import logging
from pathlib import Path
from llm.dbe_system_prompt import get_dbe_system_prompt


logger = logging.getLogger(__name__)


class MessageRole(Enum):
    """Enum for message roles in a conversation."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class Message:
    """Represents a single message in a chat session."""
    role: MessageRole
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary format."""
        return {
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        """Create message from dictionary format."""
        return cls(
            role=MessageRole(data["role"]),
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            metadata=data.get("metadata", {})
        )
    
    def to_llm_format(self) -> Dict[str, str]:
        """Convert to LLM API format (role and content only)."""
        return {
            "role": self.role.value,
            "content": self.content
        }


@dataclass
class ChatSession:
    """Represents a chat session with message history."""
    session_id: str
    messages: List[Message] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_message(self, role: MessageRole, content: str, metadata: Optional[Dict[str, Any]] = None) -> Message:
        """
        Add a message to the session.
        
        Args:
            role: The role of the message sender
            content: The message content
            metadata: Optional metadata for the message
            
        Returns:
            The created Message object
        """
        message = Message(
            role=role,
            content=content,
            metadata=metadata or {}
        )
        self.messages.append(message)
        self.updated_at = datetime.now()
        return message
    
    def get_messages(self, include_system: bool = True) -> List[Message]:
        """
        Get all messages in the session.
        
        Args:
            include_system: Whether to include system messages
            
        Returns:
            List of messages
        """
        if include_system:
            return self.messages.copy()
        return [msg for msg in self.messages if msg.role != MessageRole.SYSTEM]
    
    def get_messages_for_llm(self, include_system: bool = True) -> List[Dict[str, str]]:
        """
        Get messages in LLM API format.
        
        Args:
            include_system: Whether to include system messages
            
        Returns:
            List of message dictionaries in LLM format
        """
        messages = self.get_messages(include_system)
        return [msg.to_llm_format() for msg in messages]
    
    def clear_messages(self, keep_system: bool = True) -> None:
        """
        Clear all messages from the session.
        
        Args:
            keep_system: If True, keep system messages
        """
        if keep_system:
            self.messages = [msg for msg in self.messages if msg.role == MessageRole.SYSTEM]
        else:
            self.messages = []
        self.updated_at = datetime.now()
    
    def get_message_count(self, include_system: bool = True) -> int:
        """
        Get the number of messages in the session.
        
        Args:
            include_system: Whether to include system messages in count
            
        Returns:
            Number of messages
        """
        if include_system:
            return len(self.messages)
        return len([msg for msg in self.messages if msg.role != MessageRole.SYSTEM])
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary format."""
        return {
            "session_id": self.session_id,
            "messages": [msg.to_dict() for msg in self.messages],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChatSession':
        """Create session from dictionary format."""
        return cls(
            session_id=data["session_id"],
            messages=[Message.from_dict(msg) for msg in data["messages"]],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            metadata=data.get("metadata", {})
        )


class ChatManager:
    """Manages multiple chat sessions and provides session persistence."""
    
    def __init__(
        self,
        storage_dir: Optional[str] = None,
        rag_system: Optional[Any] = None,
        autosave: bool = False,
    ):
        """
        Initialize the chat manager.
        
        Args:
            storage_dir: Directory for storing session data (optional)
            rag_system: Optional RAG system for context-aware responses
            autosave: Persist mutations immediately when storage is configured
        """
        self.sessions: Dict[str, ChatSession] = {}
        self.active_session_id: Optional[str] = None
        self.storage_dir = storage_dir
        self.rag_system = rag_system
        self.autosave = autosave
        self.cin_context: Optional[str] = None
        
        if storage_dir:
            Path(storage_dir).mkdir(parents=True, exist_ok=True)
    
    def create_session(self, session_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> ChatSession:
        """
        Create a new chat session.
        
        Args:
            session_id: Optional custom session ID (auto-generated if not provided)
            metadata: Optional metadata for the session
            
        Returns:
            The created ChatSession
        """
        if session_id is None:
            session_id = self._generate_session_id()
        
        if session_id in self.sessions:
            raise ValueError(f"Session with ID '{session_id}' already exists")
        
        session = ChatSession(
            session_id=session_id,
            metadata=metadata or {}
        )
        self.sessions[session_id] = session
        
        # Set as active if it's the first session
        if self.active_session_id is None:
            self.active_session_id = session_id

        self._autosave_session(session_id)
        
        return session
    
    def get_session(self, session_id: str) -> Optional[ChatSession]:
        """
        Get a session by ID.
        
        Args:
            session_id: The session ID
            
        Returns:
            The ChatSession or None if not found
        """
        return self.sessions.get(session_id)
    
    def get_active_session(self) -> Optional[ChatSession]:
        """
        Get the currently active session.
        
        Returns:
            The active ChatSession or None
        """
        if self.active_session_id:
            return self.sessions.get(self.active_session_id)
        return None
    
    def set_active_session(self, session_id: str) -> bool:
        """
        Set the active session.
        
        Args:
            session_id: The session ID to activate
            
        Returns:
            True if successful, False if session not found
        """
        if session_id in self.sessions:
            self.active_session_id = session_id
            return True
        return False
    
    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session.
        
        Args:
            session_id: The session ID to delete
            
        Returns:
            True if successful, False if session not found
        """
        if session_id in self.sessions:
            del self.sessions[session_id]
            if self.storage_dir:
                try:
                    Path(self.storage_dir, f"{session_id}.json").unlink(missing_ok=True)
                except OSError as error:
                    logger.exception("Error deleting persisted session %s", session_id)
            
            # If deleted session was active, clear active session
            if self.active_session_id == session_id:
                self.active_session_id = None
                
                # Set another session as active if available
                if self.sessions:
                    self.active_session_id = next(iter(self.sessions.keys()))
            
            return True
        return False
    
    def list_sessions(self) -> List[str]:
        """
        Get a list of all session IDs.
        
        Returns:
            List of session IDs
        """
        return list(self.sessions.keys())
    
    def add_message(self, role: MessageRole, content: str, 
                   session_id: Optional[str] = None,
                   metadata: Optional[Dict[str, Any]] = None) -> Optional[Message]:
        """
        Add a message to a session.
        
        Args:
            role: The message role
            content: The message content
            session_id: Session ID (uses active session if not provided)
            metadata: Optional message metadata
            
        Returns:
            The created Message or None if session not found
        """
        if session_id is None:
            session_id = self.active_session_id
        
        session = self.get_session(session_id)
        if session:
            message = session.add_message(role, content, metadata)
            self._autosave_session(session.session_id)
            return message
        return None
    
    def get_messages_for_llm(self, session_id: Optional[str] = None, 
                            include_system: bool = True) -> List[Dict[str, str]]:
        """
        Get messages in LLM format for a session.
        
        Args:
            session_id: Session ID (uses active session if not provided)
            include_system: Whether to include system messages
            
        Returns:
            List of messages in LLM format
        """
        if session_id is None:
            session_id = self.active_session_id
        
        session = self.get_session(session_id)
        if session:
            return session.get_messages_for_llm(include_system)
        return []
    
    def get_messages_for_llm_with_context(self, 
                                         query: str,
                                         session_id: Optional[str] = None, 
                                         include_system: bool = True,
                                         top_k: int = 3) -> List[Dict[str, str]]:
        """
        Get messages in LLM format with RAG context injected.
        
        Args:
            query: The user's query (used for context retrieval)
            session_id: Session ID (uses active session if not provided)
            include_system: Whether to include system messages
            top_k: Number of context chunks to retrieve from RAG
            
        Returns:
            List of messages in LLM format with context prepended
        """
        # Get base messages
        messages = self.get_messages_for_llm(session_id, include_system)
        
        # If RAG system is available, retrieve and inject context
        if self.rag_system and query:
            try:
                # Retrieve relevant context
                context = self.rag_system.get_context(query, top_k=top_k, boost_active_files=True)
                
                # Format context for LLM
                if context and context.chunks:
                    context_text = context.format_for_llm()
                    
                    # Create system message with context
                    context_message = {
                        "role": "system",
                        "content": f"Here is relevant context from the user's files:\n\n{context_text}\n\nUse this context to provide more accurate and relevant responses."
                    }
                    
                    # Insert context message at the beginning (after any existing system messages)
                    # Find the position after existing system messages
                    insert_pos = 0
                    for i, msg in enumerate(messages):
                        if msg.get("role") == "system":
                            insert_pos = i + 1
                        else:
                            break
                    
                    messages.insert(insert_pos, context_message)
            except Exception as e:
                # If RAG fails, continue without context
                logger.exception("RAG context retrieval failed")

        # If CIN context is available, retrieve and inject context
        if self.cin_context:
            cin_message = {
                "role": "system",
                "content": f"Here is an injected file context (via CIN):\n\n{self.cin_context}\n\nUse this context if relevant to the user query."
            }
            # Insert CIN context after system messages
            insert_pos = 0
            for i, msg in enumerate(messages):
                if msg.get("role") == "system":
                    insert_pos = i + 1
                else:
                    break
            messages.insert(insert_pos, cin_message)
        
        return messages

    
    def clear_session(self, session_id: Optional[str] = None, keep_system: bool = True) -> bool:
        """
        Clear messages from a session.
        
        Args:
            session_id: Session ID (uses active session if not provided)
            keep_system: Whether to keep system messages
            
        Returns:
            True if successful, False if session not found
        """
        if session_id is None:
            session_id = self.active_session_id
        
        session = self.get_session(session_id)
        if session:
            session.clear_messages(keep_system)
            self._autosave_session(session.session_id)
            return True
        return False
    
    def save_session(self, session_id: str) -> bool:
        """
        Save a session to disk.
        
        Args:
            session_id: The session ID to save
            
        Returns:
            True if successful, False otherwise
        """
        if not self.storage_dir:
            return False
        
        session = self.get_session(session_id)
        if not session:
            return False
        
        try:
            filepath = Path(self.storage_dir, f"{session_id}.json")
            temporary_filepath = filepath.with_suffix(".json.tmp")
            with temporary_filepath.open('w', encoding='utf-8') as f:
                json.dump(session.to_dict(), f, indent=2, ensure_ascii=False)
            os.replace(temporary_filepath, filepath)
            return True
        except Exception as e:
            logger.exception("Error saving session %s", session_id)
            return False
    
    def load_session(self, session_id: str) -> Optional[ChatSession]:
        """
        Load a session from disk.
        
        Args:
            session_id: The session ID to load
            
        Returns:
            The loaded ChatSession or None if failed
        """
        if not self.storage_dir:
            return None
        
        try:
            filepath = os.path.join(self.storage_dir, f"{session_id}.json")
            if not os.path.exists(filepath):
                return None
            
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            session = ChatSession.from_dict(data)
            self.sessions[session_id] = session
            
            # Set as active if no active session
            if self.active_session_id is None:
                self.active_session_id = session_id
            
            return session
        except Exception as e:
            logger.exception("Error loading session %s", session_id)
            return None
    
    def save_all_sessions(self) -> int:
        """
        Save all sessions to disk.
        
        Returns:
            Number of sessions successfully saved
        """
        if not self.storage_dir:
            return 0
        
        count = 0
        for session_id in self.sessions:
            if self.save_session(session_id):
                count += 1
        return count
    
    def load_all_sessions(self) -> int:
        """
        Load all sessions from storage directory.
        
        Returns:
            Number of sessions successfully loaded
        """
        if not self.storage_dir:
            return 0
        
        try:
            count = 0
            for filename in os.listdir(self.storage_dir):
                if filename.endswith('.json'):
                    session_id = filename[:-5]  # Remove .json extension
                    if self.load_session(session_id):
                        count += 1
            return count
        except Exception as e:
            logger.exception("Error loading sessions from %s", self.storage_dir)
            return 0

    def _autosave_session(self, session_id: str) -> None:
        if self.autosave and self.storage_dir:
            self.save_session(session_id)
    
    # --- DBE (Diff-Based Editing) methods ---
    
    def prepare_dbe_context(self, 
                           file_path: Optional[str],
                           text: str,
                           cursor_line: int,
                           selection_start: Optional[int] = None,
                           selection_end: Optional[int] = None,
                           context_lines: int = 20) -> tuple:
        """
        Prepare editor context for DBE mode.
        
        Args:
            file_path: Path to the current file (optional)
            text: Full text content
            cursor_line: Current cursor line (1-indexed)
            selection_start: Start line of selection (1-indexed, optional)
            selection_end: End line of selection (1-indexed, optional)
            context_lines: Number of lines before/after to include
            
        Returns:
            Tuple of (context_string, start_line, end_line, original_section_text)
            - context_string: Formatted context for LLM with line numbers
            - start_line: 1-indexed start line of included section
            - end_line: 1-indexed end line of included section
            - original_section_text: Raw text of the included section (for reconstruction)
            - focus_start: 1-indexed start line of focus area
            - focus_end: 1-indexed end line of focus area
        """
        lines = text.splitlines()
        total_lines = len(lines)
        
        # Determine the range to include
        if selection_start is not None and selection_end is not None:
            # User has selected text
            start_line = max(1, selection_start - context_lines)
            end_line = min(total_lines, selection_end + context_lines)
            focus_start = selection_start
            focus_end = selection_end
        else:
            # No selection, use cursor position
            start_line = max(1, cursor_line - context_lines)
            end_line = min(total_lines, cursor_line + context_lines)
            focus_start = cursor_line
            focus_end = cursor_line
        
        # Extract the original section text (for later reconstruction)
        original_section_lines = lines[start_line - 1:end_line]
        original_section_text = "\n".join(original_section_lines)
        
        # Build context string
        context_parts = []
        
        if file_path:
            context_parts.append(f"File: {file_path}")
        
        context_parts.append(f"Total lines: {total_lines}")
        context_parts.append(f"Showing lines {start_line}-{end_line}")
        
        if selection_start is not None and selection_end is not None:
            context_parts.append(f"Selected lines: {selection_start}-{selection_end}")
        else:
            context_parts.append(f"Cursor at line: {cursor_line}")
        
        context_parts.append("\n--- Text Content ---")
        
        # Add line-numbered text
        for i in range(start_line - 1, end_line):
            line_num = i + 1
            line_content = lines[i] if i < len(lines) else ""
            
            # Mark focus area
            if focus_start <= line_num <= focus_end:
                marker = "→ "
            else:
                marker = "  "
            
            context_parts.append(f"{marker}{line_num:4d}: {line_content}")
        
        
        context_string = "\n".join(context_parts)
        return (context_string, start_line, end_line, original_section_text, focus_start, focus_end)
    
    def get_messages_for_llm_with_dbe_context(self,
                                              query: str,
                                              editor_context: str,
                                              session_id: Optional[str] = None,
                                              include_system: bool = True) -> List[Dict[str, str]]:
        """
        Get messages in LLM format with DBE editor context injected.
        
        Args:
            query: The user's query
            editor_context: Formatted editor context from prepare_dbe_context
            session_id: Session ID (uses active session if not provided)
            include_system: Whether to include system messages
            
        Returns:
            List of messages in LLM format with DBE context
        """
        # Get base messages
        messages = self.get_messages_for_llm(session_id, include_system)
        
        # Calculate line count for explicit instruction
        section_line_count = editor_context.count('\n') - editor_context.count('--- ')  # Approximate
        
        # Create DBE context message
        dbe_context_message = {
            "role": "system",
            "content": f"""{get_dbe_system_prompt()}

EDITOR CONTEXT:
{editor_context}"""
        }
        
        # Insert DBE context after system messages
        insert_pos = 0
        for i, msg in enumerate(messages):
            if msg.get("role") == "system":
                insert_pos = i + 1
            else:
                break
        
        messages.insert(insert_pos, dbe_context_message)
        
        return messages
    
    def _generate_session_id(self) -> str:
        """Generate a unique session ID."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        counter = 0
        session_id = f"session_{timestamp}"
        
        while session_id in self.sessions:
            counter += 1
            session_id = f"session_{timestamp}_{counter}"
        
        return session_id
