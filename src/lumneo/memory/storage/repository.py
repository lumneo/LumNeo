# src/lumneo/memory/storage/repository.py

import sqlite3
import json
import uuid
import logging
import threading
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional, List, Dict, Any

from ..model import MemoryObject, Evidence, Source, PrivacyInfo, MemoryNeed, MemoryStatus
from ..common.exceptions import PersistenceError, ValidationError, ConcurrentModificationError, NotFoundError
from ..common.time import utc_now
from ..common.id_gen import generate_evidence_id
from .serializer import write_memory_object, read_memory_object, memory_to_path
from lumneo.kernel.config.app_config import MIGRATIONS_DIR


logger = logging.getLogger(__name__)


# ========== 辅助结构（ADR-006 §3） ==========
class ConsistencyReport:
    def __init__(
        self,
        status: Literal["healthy", "repaired", "critical"],
        missing_in_index: Optional[List[str]] = None,
        orphan_in_index: Optional[List[str]] = None,
        checksum_mismatch: Optional[List[str]] = None,
        repaired_count: int = 0,
        critical_details: Optional[str] = None,
    ):
        self.status = status
        self.missing_in_index = missing_in_index or []
        self.orphan_in_index = orphan_in_index or []
        self.checksum_mismatch = checksum_mismatch or []
        self.repaired_count = repaired_count
        self.critical_details = critical_details


class AuditLogEntry:
    def __init__(
        self,
        timestamp: datetime,
        action: Literal[
            "capture", "evaluation", "state_transition",
            "forget", "correct", "supersede", "conflict",
            "auto_action", "index_rebuild", "scope_violation"
        ],
        memory_id: Optional[str],
        reason: str,
        source: dict,
        payload: Optional[dict] = None,
    ):
        self.timestamp = timestamp
        self.action = action
        self.memory_id = memory_id
        self.reason = reason
        self.source = source
        self.payload = payload or {}


# ========== 抽象接口（ADR-006） ==========
class MemoryRepository(ABC):
    @abstractmethod
    def create(self, memory: MemoryObject) -> MemoryObject:
        """原子写入 Markdown，插入 SQLite + FTS5。"""
        ...

    @abstractmethod
    def update_with_version(
        self,
        memory: MemoryObject,
        expected_updated_at: Optional[datetime] = None
    ) -> MemoryObject:
        """更新记忆，乐观锁预留。"""
        ...

    @abstractmethod
    def append_audit_log(self, entry: AuditLogEntry) -> None:
        """追加审计日志。"""
        ...

    @abstractmethod
    def get_by_id(self, memory_id: str) -> Optional[MemoryObject]:
        """根据 ID 读取记忆。"""
        ...

    @abstractmethod
    def query_active(
        self,
        need: MemoryNeed,
        scope_filter: Optional[dict] = None
    ) -> List[MemoryObject]:
        """检索 active 状态记忆。"""
        ...

    @abstractmethod
    def query_by_status(
        self,
        status: MemoryStatus,
        scope_filter: Optional[dict] = None,
        limit: int = 100
    ) -> List[MemoryObject]:
        """按状态批量查询。"""
        ...

    @abstractmethod
    def rebuild_index(
        self,
        force_ids: Optional[List[str]] = None
    ) -> ConsistencyReport:
        """重建 FTS5 / SQLite 索引。"""
        ...

    @abstractmethod
    def search_candidates(
        self,
        need: MemoryNeed,
        statuses: Optional[List[MemoryStatus]] = None,
        limit: int = 100,
    ) -> List[MemoryObject]:
        """检索候选记忆，支持多种过滤条件"""
        ...

    @abstractmethod
    def get_relevance_scores(
        self,
        memory_ids: List[str],
        query: str,
    ) -> Dict[str, float]:
        """计算 BM25 相关性分数"""
        ...

    @abstractmethod
    def record_access(self, memory_id: str) -> None:
        """异步更新记忆的 last_accessed 和 access_count（仅限检索副作用）。"""
        ...

    @abstractmethod
    def check_consistency(self) -> ConsistencyReport:
        """执行一致性校验。"""
        ...

    @abstractmethod
    def close(self) -> None:
        """安全关闭连接。"""
        ...


# ========== 具体实现：SQLiteMemoryRepository ==========
class SQLiteMemoryRepository(MemoryRepository):
    def __init__(self, db_path: Path, data_root: Path):
        self.db_path = db_path
        self.data_root = data_root
        self.conn = None
        self._lifecycle_lock = threading.Lock()
        self._closing = False
        self._access_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="lumneo-memory-access",
        )

        try:
            self._init_db()
        except Exception:
            self.close()
            raise

    def _init_db(self):
        """初始化数据库连接，执行迁移。"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        # self.conn.execute("PRAGMA journal_mode = WAL")  # WAL 模式下，SQLite 会在内存中缓存数据，并在事务提交时将数据写入磁盘，从而提高并发性能。
        self._check_and_migrate()
        self._create_audit_table()
        # 启动时自动执行一致性检查并修复
        report = self.check_consistency()
        if report.status != "healthy":
            # 自动重建全量索引
            self.rebuild_index()
            # 记录日志
            logger.error(f"[MemoryOS] 索引不一致，已自动重建。缺失: {len(report.missing_in_index)}, 孤儿: {len(report.orphan_in_index)}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def _row_to_memory(self, row: sqlite3.Row) -> MemoryObject:
        """从 SQLite 行构造 MemoryObject（含 evidence）。"""
        # 解析 JSON 字段
        source_dict = json.loads(row['source_json'])
        privacy_dict = json.loads(row['privacy_json']) if row['privacy_json'] else None
        metadata_dict = json.loads(row['metadata_json']) if row['metadata_json'] else {}
        tags_list = json.loads(row['tags_json']) if row['tags_json'] else []
        condition_dict = json.loads(row['condition_json']) if row['condition_json'] else None

        # 构造 Source
        source = Source(
            tenant_id=source_dict.get('tenant_id'),
            agent_id=source_dict.get('agent_id'),
            chat_id=source_dict.get('chat_id'),
            message_id=source_dict.get('message_id'),
            timestamp=datetime.fromisoformat(source_dict['timestamp']) if source_dict.get('timestamp') else utc_now(),
            channel=source_dict.get('channel'),
            extra=source_dict.get('extra')
        )

        # 构造 PrivacyInfo
        privacy = PrivacyInfo(
            level=privacy_dict['level'],
            reason=privacy_dict.get('reason')
        ) if privacy_dict else None

        # 查询证据
        ev_cursor = self.conn.execute(
            "SELECT * FROM evidence WHERE memory_id = ?", (row['id'],)
        )
        evidence_list = []
        for ev_row in ev_cursor.fetchall():
            ev_source_dict = json.loads(ev_row['source_json'])
            ev_source = Source(
                tenant_id=ev_source_dict.get('tenant_id'),
                agent_id=ev_source_dict.get('agent_id'),
                chat_id=ev_source_dict.get('chat_id'),
                message_id=ev_source_dict.get('message_id'),
                timestamp=datetime.fromisoformat(ev_source_dict['timestamp']) if ev_source_dict.get('timestamp') else utc_now(),
                channel=ev_source_dict.get('channel'),
                extra=ev_source_dict.get('extra')
            )
            evidence = Evidence(
                type=ev_row['type'],
                weight=ev_row['weight'],
                source=ev_source,
                observation=ev_row['observation'],
                origin_actor=ev_row['origin_actor'],
                created_at=datetime.fromisoformat(ev_row['created_at']),
                provenance_key=ev_row['provenance_key']
            )
            evidence_list.append(evidence)

        return MemoryObject(
            id=row['id'],
            schema_version=row['schema_version'],
            layer=row['layer'],
            type=row['type'],
            subject=row['subject'],
            predicate=row['predicate'],
            object=row['object'],
            condition=condition_dict,
            content=row['content'],
            confidence=row['confidence'],
            confidence_detail=None,
            importance=row['importance'],
            status=row['status'],
            evidence=evidence_list,
            source=source,
            origin=row['origin'],
            supersedes=row['supersedes'],
            superseded_by=row['superseded_by'],
            last_accessed=datetime.fromisoformat(row['last_accessed']) if row['last_accessed'] else None,
            access_count=row['access_count'],
            tags=tags_list,
            privacy=privacy,
            created_at=datetime.fromisoformat(row['created_at']),
            updated_at=datetime.fromisoformat(row['updated_at']),
            metadata=metadata_dict
        )

    def _create_audit_table(self):
        """创建审计日志表（如果不存在）"""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                action TEXT NOT NULL,
                memory_id TEXT,
                reason TEXT,
                source_json TEXT,
                payload_json TEXT
            )
        """)
        # 可选：创建索引以加速查询
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_logs(timestamp)")
        self.conn.commit()

    def _check_and_migrate(self):
        """检查 schema 版本，执行 DDL。"""
        cursor = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='_schema_meta'"
        )
        if cursor.fetchone() is None:
            self._execute_ddl()
        else:
            row = self.conn.execute(
                "SELECT value FROM _schema_meta WHERE key='storage_schema_version'"
            ).fetchone()
            if row is None or row[0] != "1.0":
                raise PersistenceError(f"不支持的 storage schema 版本: {row[0] if row else 'unknown'}, 仅支持 1.0")

    def _execute_ddl(self):
        """执行完整 DDL 脚本。"""
        migration_file = MIGRATIONS_DIR / "migrate_v0.0_to_v1.0.sql"
        if not migration_file.exists():
            raise PersistenceError(f"迁移文件不存在: {migration_file}")
        with open(migration_file, 'r', encoding='utf-8') as f:
            script = f.read()
        try:
            self.conn.executescript(script)
        except sqlite3.Error as e:
            raise PersistenceError(f"DDL 执行失败: {e}")

    def _update_memory(self, memory: MemoryObject):
        """更新 memories 和 evidence 表（不更新 Markdown，由调用方负责）"""
        source_json = json.dumps(memory.source.model_dump(mode='json'), ensure_ascii=False)
        privacy_json = json.dumps(memory.privacy.model_dump(mode='json') if memory.privacy else None, ensure_ascii=False)
        metadata_json = json.dumps(memory.metadata, ensure_ascii=False)
        tags_json = json.dumps(memory.tags, ensure_ascii=False)
        condition_json = json.dumps(memory.condition, ensure_ascii=False) if memory.condition else None

        self.conn.execute("""
            UPDATE memories SET
                schema_version = ?, layer = ?, type = ?, subject = ?, predicate = ?, object = ?,
                condition_json = ?, content = ?, confidence = ?, importance = ?, status = ?,
                origin = ?, supersedes = ?, superseded_by = ?, last_accessed = ?, access_count = ?,
                tags_json = ?, privacy_json = ?, updated_at = ?, metadata_json = ?, source_json = ?,
                evidence_count = ?
            WHERE id = ?
        """, (
            memory.schema_version, memory.layer, memory.type,
            memory.subject, memory.predicate, memory.object,
            condition_json, memory.content, memory.confidence, memory.importance,
            memory.status, memory.origin, memory.supersedes, memory.superseded_by,
            memory.last_accessed.isoformat() if memory.last_accessed else None,
            memory.access_count,
            tags_json, privacy_json,
            memory.updated_at.isoformat(),
            metadata_json, source_json,
            len(memory.evidence),
            memory.id
        ))

        # 证据：先删后插
        self.conn.execute("DELETE FROM evidence WHERE memory_id = ?", (memory.id,))
        for ev in memory.evidence:
            ev_source_json = json.dumps(ev.source.model_dump(mode='json'), ensure_ascii=False)
            ev_id = generate_evidence_id()
            self.conn.execute("""
                INSERT INTO evidence (
                    id, memory_id, type, weight, source_json, observation,
                    origin_actor, created_at, provenance_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ev_id, memory.id,
                ev.type, ev.weight,
                ev_source_json, ev.observation,
                ev.origin_actor,
                ev.created_at.isoformat(),
                ev.provenance_key
            ))

        self.conn.commit()

    # ---------- 写操作 ----------
    def create(self, memory: MemoryObject) -> MemoryObject:
        try:
            write_memory_object(memory, self.data_root)
        except Exception as e:
            raise PersistenceError(f"Markdown 写入失败: {e}") from e

        try:
            self._insert_memory(memory)
            return memory
        except sqlite3.Error as e:
            raise PersistenceError(f"SQLite 插入失败: {e}") from e

    def update_with_version(
        self,
        memory: MemoryObject,
        expected_updated_at: Optional[datetime] = None
    ) -> MemoryObject:
        # ---------- 乐观锁检查（预留） ----------
        if expected_updated_at is not None:
            cursor = self.conn.execute(
                "SELECT updated_at FROM memories WHERE id = ?",
                (memory.id,)
            )
            row = cursor.fetchone()
            if row is None:
                raise NotFoundError(f"记忆 {memory.id} 不存在")
            current_updated = datetime.fromisoformat(row[0])
            if current_updated != expected_updated_at:
                raise ConcurrentModificationError(
                    f"乐观锁冲突：期望 {expected_updated_at.isoformat()}，实际 {current_updated.isoformat()}",
                    context={"id": memory.id, "expected": expected_updated_at.isoformat(), "actual": current_updated.isoformat()}
                )

        # ---------- 更新时间戳（强制） ----------
        memory.updated_at = utc_now()   # 新纳秒级时间

        # ---------- 原子写入 Markdown ----------
        try:
            write_memory_object(memory, self.data_root)
        except Exception as e:
            raise PersistenceError(f"Markdown 更新失败: {e}") from e

        # ---------- 更新 SQLite 和 FTS5 ----------
        try:
            self._update_memory(memory)
        except sqlite3.Error as e:
            # 如果 SQL 失败，Markdown 已写入，可能会不一致；但 Phase 1A 简单处理为异常
            raise PersistenceError(f"SQLite 更新失败: {e}") from e

        return memory

    def find_active_by_subject_predicate(self, subject: str, predicate: str) -> List[MemoryObject]:
        """查询所有 status='active' 且 subject 和 predicate 完全匹配的记忆。"""
        cursor = self.conn.execute(
            "SELECT id FROM memories WHERE subject = ? AND predicate = ? AND status = 'active'",
            (subject, predicate)
        )
        ids = [row[0] for row in cursor.fetchall()]
        result = []
        for mid in ids:
            obj = self.get_by_id(mid)
            if obj is not None:
                result.append(obj)
        return result

    def _insert_memory(self, memory: MemoryObject):
        # 转换 source.timestamp
        source_dict = memory.source.model_dump(mode='json')
        if source_dict.get('timestamp') and isinstance(source_dict['timestamp'], datetime):
            source_dict['timestamp'] = source_dict['timestamp'].isoformat()
        source_json = json.dumps(source_dict, ensure_ascii=False)

        privacy_json = json.dumps(memory.privacy.model_dump(mode='json') if memory.privacy else None, ensure_ascii=False)
        metadata_json = json.dumps(memory.metadata, ensure_ascii=False)
        tags_json = json.dumps(memory.tags, ensure_ascii=False)
        condition_json = json.dumps(memory.condition, ensure_ascii=False) if memory.condition else None

        self.conn.execute("""
            INSERT INTO memories (
                id, schema_version, layer, type, subject, predicate, object,
                condition_json, content, confidence, importance, status,
                origin, supersedes, superseded_by, last_accessed, access_count,
                tags_json, privacy_json, created_at, updated_at, metadata_json,
                source_json, evidence_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            memory.id, memory.schema_version, memory.layer, memory.type,
            memory.subject, memory.predicate, memory.object,
            condition_json, memory.content, memory.confidence, memory.importance,
            memory.status, memory.origin, memory.supersedes, memory.superseded_by,
            memory.last_accessed.isoformat() if memory.last_accessed else None,
            memory.access_count,
            tags_json, privacy_json,
            memory.created_at.isoformat(), memory.updated_at.isoformat(),
            metadata_json, source_json, len(memory.evidence)
        ))

        for ev in memory.evidence:
            ev_source_dict = ev.source.model_dump(mode='json')
            if ev_source_dict.get('timestamp') and isinstance(ev_source_dict['timestamp'], datetime):
                ev_source_dict['timestamp'] = ev_source_dict['timestamp'].isoformat()
            ev_source_json = json.dumps(ev_source_dict, ensure_ascii=False)

            ev_id = generate_evidence_id()
            self.conn.execute("""
                INSERT INTO evidence (
                    id, memory_id, type, weight, source_json, observation,
                    origin_actor, created_at, provenance_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ev_id, memory.id,
                ev.type, ev.weight,
                ev_source_json, ev.observation,
                ev.origin_actor,
                ev.created_at.isoformat(),
                ev.provenance_key
            ))

        self.conn.commit()

    # ---------- 读操作（占位） ----------
    def get_by_id(self, memory_id: str) -> Optional[MemoryObject]:
        """根据 ID 读取记忆，优先从 SQLite 获取，若不存在则尝试从 Markdown 文件回退。"""
        # 1. 从 SQLite 读取
        cursor = self.conn.execute(
            "SELECT * FROM memories WHERE id = ?", (memory_id,)
        )
        row = cursor.fetchone()
        if row is None:
            # 回退：尝试从文件系统读取
            for layer_dir in self.data_root.iterdir():
                if not layer_dir.is_dir() or layer_dir.name in ("governance", "index"):
                    continue
                md_path = layer_dir / f"{memory_id}.md"
                if md_path.exists():
                    try:
                        return read_memory_object(md_path)
                    except Exception as e:
                        raise PersistenceError(f"从 Markdown 读取记忆 {memory_id} 失败: {e}")
            return None

        # 2. 从 SQLite 行构造 MemoryObject
        try:
            return self._row_to_memory(row)
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            raise PersistenceError(f"反序列化记忆 {memory_id} 失败: {e}")

    # ---------- 索引与一致性 ----------
    def rebuild_index(self, force_ids: Optional[List[str]] = None) -> ConsistencyReport:
        """重建 FTS5 索引。若 force_ids 为空则全量重建，否则只重建指定 ID。"""
        markdown_memories = []
        if force_ids is None:
            # 删除派生表前先完整解析 Markdown；任一 SoT 文件损坏时不触碰
            # 当前索引。版本链可能双向引用，须两阶段恢复以避免插入顺序导致
            # FOREIGN KEY 失败。
            for layer_dir in self.data_root.iterdir():
                if not layer_dir.is_dir() or layer_dir.name in ("governance", "index"):
                    continue
                for md_file in layer_dir.glob("*.md"):
                    try:
                        markdown_memories.append(read_memory_object(md_file))
                    except Exception as e:
                        raise PersistenceError(f"重建索引失败: {md_file} - {e}")

        # external-content FTS 的词项若已缺失，直接 DELETE memories 会触发
        # memories_ad 再删一次同一词项，并由 SQLite 报 "database disk image is
        # malformed"。DDL 中 FTS 列名 tags 与 content table 的 tags_json 不同，
        # 因而 FTS5 内建 rebuild 命令不可用；按冻结 DDL 重建派生表及触发器，
        # 再从主表显式回填实际列映射。
        self.conn.executescript("""
            DROP TRIGGER IF EXISTS memories_ai;
            DROP TRIGGER IF EXISTS memories_ad;
            DROP TRIGGER IF EXISTS memories_au;
            DROP TABLE IF EXISTS memories_fts;
            CREATE VIRTUAL TABLE memories_fts USING fts5(
                content,
                subject,
                predicate,
                object,
                tags,
                content='memories',
                content_rowid='rowid',
                tokenize='porter unicode61'
            );
            INSERT INTO memories_fts(rowid, content, subject, predicate, object, tags)
            SELECT rowid, content, subject, predicate, object, tags_json FROM memories;
            CREATE TRIGGER memories_ai AFTER INSERT ON memories BEGIN
                INSERT INTO memories_fts(rowid, content, subject, predicate, object, tags)
                VALUES (new.rowid, new.content, new.subject, new.predicate, new.object, new.tags_json);
            END;
            CREATE TRIGGER memories_ad AFTER DELETE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content, subject, predicate, object, tags)
                VALUES ('delete', old.rowid, old.content, old.subject, old.predicate, old.object, old.tags_json);
            END;
            CREATE TRIGGER memories_au AFTER UPDATE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content, subject, predicate, object, tags)
                VALUES ('delete', old.rowid, old.content, old.subject, old.predicate, old.object, old.tags_json);
                INSERT INTO memories_fts(rowid, content, subject, predicate, object, tags)
                VALUES (new.rowid, new.content, new.subject, new.predicate, new.object, new.tags_json);
            END;
        """)
        self.conn.commit()

        # 如果 force_ids 为 None，全量重建
        if force_ids is None:
            # 清空 memories 表（级联删除 evidence，FTS5 触发器自动处理）
            self.conn.execute("DELETE FROM memories")
            # 或者使用 TRUNCATE（SQLite 不支持，用 DELETE 即可）
            self.conn.commit()

            for memory in markdown_memories:
                without_links = memory.model_copy(
                    update={"supersedes": None, "superseded_by": None}
                )
                self._insert_memory(without_links)

            for memory in markdown_memories:
                self.conn.execute(
                    "UPDATE memories SET supersedes = ?, superseded_by = ? WHERE id = ?",
                    (memory.supersedes, memory.superseded_by, memory.id),
                )
            self.conn.commit()
        else:
            # 仅重建指定 ID
            for memory_id in force_ids:
                # 查找对应的 .md 文件（需要知道 layer，可以从内容读取，或扫描所有层）
                found = False
                for layer_dir in self.data_root.iterdir():
                    if not layer_dir.is_dir() or layer_dir.name in ("governance", "index"):
                        continue
                    md_path = layer_dir / f"{memory_id}.md"
                    if md_path.exists():
                        memory = read_memory_object(md_path)
                        # 先删除旧记录（如果存在）
                        self.conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
                        self.conn.commit()
                        self._insert_memory(memory)
                        found = True
                        break
                if not found:
                    # 如果找不到文件，则从索引中删除
                    self.conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
                    self.conn.commit()

        try:
            self.append_audit_log(
                AuditLogEntry(
                    timestamp=utc_now(),
                    action="index_rebuild",
                    memory_id=None,
                    reason="索引重建（自动或手动）",
                    source={"force_ids": force_ids},
                    payload={"status": "completed"}
                )
            )
        except Exception:
            pass

        # 返回一致性报告（仅作参考）
        return self.check_consistency()

    def record_access(self, memory_id: str) -> None:
        """将访问统计加入 Repository 自己的后台队列。"""
        with self._lifecycle_lock:
            if self._closing:
                return
            future = self._access_executor.submit(self._record_access_sync, memory_id)
            future.add_done_callback(self._log_access_error)

    @staticmethod
    def _log_access_error(future) -> None:
        try:
            future.result()
        except Exception:
            logger.warning("访问统计后台更新失败", exc_info=True)

    def _record_access_sync(self, memory_id: str) -> None:
        """使用独立连接刷新遥测，避免复用检索事务的 SQLite 连接。"""
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute(
                "UPDATE memories "
                "SET last_accessed = ?, access_count = access_count + 1 "
                "WHERE id = ?",
                (utc_now().isoformat(), memory_id),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _condition_filter_values(condition_filter: dict) -> List[str]:
        if "key" in condition_filter:
            return [condition_filter["value"]]
        return [clause["value"] for clause in condition_filter["clauses"]]

    def _search_condition_candidates(
        self,
        need: MemoryNeed,
        statuses: List[MemoryStatus],
        limit: int,
    ) -> List[MemoryObject]:
        """FTS5 coarse recall with hard filters for Contract §7 P-04."""
        # 精确过滤值比自然语言关键词更具选择性。例如 jieba 会把 room_5
        # 拆成 room，并把 condition_topic_5 拆成高频的 condition/topic；
        # 用这些宽泛 token 做 OR 会迫使 FTS 为数千条记录计算 BM25。粗筛以
        # condition values 为准，完整 query keywords 仍用于后续相关性排名。
        terms = self._condition_filter_values(need.condition_filter or {})
        if not any(term.strip() for term in terms):
            terms = list(need.keywords or [])
        terms = list(dict.fromkeys(term.strip() for term in terms if term.strip()))
        if not terms:
            return []

        fts_query = " OR ".join(
            f'"{term.replace(chr(34), chr(34) * 2)}"*' for term in terms
        )
        status_placeholders = ",".join("?" for _ in statuses)
        sql = f"""
            WITH fts_hits(rowid, bm25_score) AS MATERIALIZED (
                SELECT rowid, bm25(memories_fts)
                FROM memories_fts
                WHERE memories_fts MATCH ?
            )
            SELECT m.*
            FROM fts_hits
            JOIN memories m ON m.rowid = fts_hits.rowid
            WHERE m.status IN ({status_placeholders})
        """
        params: List[Any] = [fts_query, *statuses]

        scope = need.scope_filter or {}
        tenant_id = scope.get("tenant_id")
        agent_id = scope.get("agent_id")
        if tenant_id:
            sql += " AND json_extract(m.source_json, '$.tenant_id') = ?"
            params.append(tenant_id)
        if agent_id:
            sql += " AND json_extract(m.source_json, '$.agent_id') = ?"
            params.append(agent_id)

        if need.layers:
            placeholders = ",".join("?" for _ in need.layers)
            sql += f" AND m.layer IN ({placeholders})"
            params.extend(need.layers)
        if need.types:
            placeholders = ",".join("?" for _ in need.types)
            sql += f" AND m.type IN ({placeholders})"
            params.extend(need.types)

        sql += " ORDER BY fts_hits.bm25_score LIMIT ?"
        params.append(min(limit, 100))
        rows = self.conn.execute(sql, params).fetchall()
        return [self._row_to_memory(row) for row in rows]

    def search_candidates(
        self,
        need: MemoryNeed,
        statuses: Optional[List[MemoryStatus]] = None,
        limit: int = 100,
    ) -> List[MemoryObject]:
        """
        Candidate Recall

        Phase 1A:
        - status 是硬过滤
        - scope 是硬过滤
        - layer/type 是弱约束
        - keyword 不作为硬过滤

        防止：
        中文 FTS 失败导致 Recall=0
        """
        statuses = statuses or ["active"]
        if need.condition_filter is not None:
            return self._search_condition_candidates(need, statuses, limit)

        placeholders = ",".join(["?"] * len(statuses))

        sql = f"""
            SELECT m.*
            FROM memories m
            WHERE m.status IN ({placeholders})
        """

        params = list(statuses)

        # ------------------------------
        # scope filter
        # ------------------------------
        scope = need.scope_filter or {}
        tenant_id = scope.get("tenant_id")
        agent_id = scope.get("agent_id")

        if tenant_id:
            sql += """
                AND json_extract(
                    m.source_json,
                    '$.tenant_id'
                ) = ?
            """
            params.append(tenant_id)

        if agent_id:
            sql += """
                AND json_extract(
                    m.source_json,
                    '$.agent_id'
                ) = ?
            """
            params.append(agent_id)

        # ------------------------------
        # layer
        # ------------------------------
        if need.layers:
            layer_placeholders = ",".join(["?"] * len(need.layers))
            sql += f"""
                AND m.layer IN ({layer_placeholders})
            """
            params.extend(need.layers)

        # ------------------------------
        # type
        # ------------------------------
        if need.types:
            type_placeholders = ",".join(["?"] * len(need.types))
            sql += f"""
                AND m.type IN ({type_placeholders})
            """
            params.extend(need.types)

        # 注意：
        # 不再使用：
        # AND memories_fts MATCH ?
        # keyword 交给 ranking

        sql += """
            ORDER BY
                m.importance DESC,
                m.confidence DESC,
                m.created_at DESC
            LIMIT ?
        """

        params.append(limit)

        cursor = self.conn.execute(sql, params)
        rows = cursor.fetchall()

        return [self._row_to_memory(row) for row in rows]

    def get_relevance_scores(
        self,
        memory_ids: List[str],
        query: str,
    ) -> Dict[str, float]:
        """按 Contract §5.2 将 SQLite FTS5 BM25 映射到 ``[0, 1)``。"""
        scores = {mid: 0.0 for mid in memory_ids}
        if not memory_ids or not query or not query.strip():
            return scores

        raw_query = query.strip()
        compact_query = "".join(raw_query.split())

        try:
            import jieba
            segmented_terms = [
                term.strip() for term in jieba.lcut(raw_query) if term.strip()
            ]
        except Exception:
            segmented_terms = raw_query.split()

        stop = {"我", "的", "什么", "用户", "喜欢", "会", "吗", "呢"}
        terms = list(dict.fromkeys(
            term
            for term in [compact_query, *segmented_terms]
            if term and term not in stop
        ))
        if not terms:
            return scores

        # ADR-007 固定 unicode61；对中文而言，一整段连续汉字可能成为单个
        # FTS token。将命中查询片段的已索引字段扩展成完整 phrase，避免把
        # BM25 旁路成 Python 子串分数，同时保持中文召回。ASCII/数字 token
        # 已由 unicode61 正常切分，禁止触发整字段扩展，否则会把候选池膨胀成
        # 近百个长 OR phrase，破坏 10k 规模下的延迟。
        cjk_terms = [
            term
            for term in terms
            if any("\u3400" <= character <= "\u9fff" for character in term)
        ]
        placeholders = ",".join(["?"] * len(memory_ids))
        expansion_sql = f"""
            SELECT content, subject, predicate, object, tags_json
            FROM memories
            WHERE id IN ({placeholders})
        """
        expanded_terms = list(terms)
        if cjk_terms:
            for row in self.conn.execute(expansion_sql, memory_ids).fetchall():
                for field in (
                    "content",
                    "subject",
                    "predicate",
                    "object",
                    "tags_json",
                ):
                    value = (row[field] or "").strip()
                    if value and any(term in value for term in cjk_terms):
                        expanded_terms.append(value)
        terms = list(dict.fromkeys(expanded_terms))

        # unicode61 不会按中文词边界切分，因此同时保留紧凑原词并使用
        # FTS5 prefix phrase；仍由 bm25() 负责相关性，不做旁路子串打分。
        fts_query = " OR ".join(
            f'"{term.replace(chr(34), chr(34) * 2)}"*'
            for term in terms
        )
        sql = f"""
            SELECT m.id, bm25(memories_fts) AS bm25_score
            FROM memories_fts
            JOIN memories m ON m.rowid = memories_fts.rowid
            WHERE memories_fts MATCH ?
              AND m.id IN ({placeholders})
        """

        for row in self.conn.execute(sql, [fts_query, *memory_ids]).fetchall():
            bm25_strength = max(0.0, -float(row["bm25_score"]))
            scores[row["id"]] = bm25_strength / (bm25_strength + 0.5)

        return scores

    # 重构 query_active 和 query_by_status 以调用 search_candidates（可选）
    def query_active(self, need: MemoryNeed, scope_filter: Optional[dict] = None) -> List[MemoryObject]:
        # 将 scope_filter 合并到 need（暂时修改 need 对象，但不建议）
        # 更好的方式：复制 need 并更新 scope_filter
        need_copy = need.model_copy(deep=True)
        need_copy.scope_filter = scope_filter or need_copy.scope_filter
        return self.search_candidates(need_copy, statuses=["active"], limit=need.max_results or 100)

    def query_by_status(self, status: MemoryStatus, scope_filter: Optional[dict] = None, limit: int = 100) -> List[MemoryObject]:
        # 仅按状态查询，无关键词过滤（保留原行为）
        # 构造一个简单的 need 只包含 scope_filter
        need = MemoryNeed(scope_filter=scope_filter, keywords=None)
        return self.search_candidates(need, statuses=[status], limit=limit)
    
    def check_consistency(self) -> ConsistencyReport:
        """遍历 Markdown SoT，并与 SQLite 主表及 FTS5 词项索引比对。"""
        missing_in_index = []
        orphan_in_index = []
        checksum_mismatch = []  # Phase 1A 暂不比较内容

        # 1. 从 SQLite 读取所有 memory id / rowid
        existing_ids = set()
        memory_id_by_rowid = {}
        expected_fts_rowids = set()
        cursor = self.conn.execute(
            "SELECT rowid, id, content, subject, predicate, object, tags_json "
            "FROM memories"
        )
        for row in cursor.fetchall():
            existing_ids.add(row["id"])
            memory_id_by_rowid[row["rowid"]] = row["id"]
            indexed_text = " ".join(
                str(row[field] or "")
                for field in (
                    "content",
                    "subject",
                    "predicate",
                    "object",
                    "tags_json",
                )
            )
            # unicode61 indexes Unicode letters/numbers. A valid record whose
            # indexed fields contain punctuation only legitimately has no vocab
            # row and must not be reported as a missing FTS document.
            if any(character.isalnum() for character in indexed_text):
                expected_fts_rowids.add(row["rowid"])

        # 2. 遍历所有 layer 目录下的 .md 文件
        md_ids = set()
        for layer_dir in self.data_root.iterdir():
            if not layer_dir.is_dir() or layer_dir.name in ("governance", "index"):
                continue
            for md_file in layer_dir.glob("*.md"):
                # 提取 id（文件名去掉 .md）
                memory_id = md_file.stem
                md_ids.add(memory_id)

                # 检查是否在 SQLite 中
                if memory_id not in existing_ids:
                    missing_in_index.append(memory_id)

        # 3. 检查 SQLite 中是否存在孤儿
        for idx_id in existing_ids:
            if idx_id not in md_ids:
                orphan_in_index.append(idx_id)

        # 4. 检查真正的 FTS 词项索引。直接 SELECT memories_fts 在 external
        # content 模式下会读取 memories 主表，无法发现词项被删；fts5vocab 才能
        # 枚举实际存在于倒排索引中的文档 rowid。
        try:
            self.conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS temp.memories_fts_vocab "
                "USING fts5vocab('main', 'memories_fts', 'instance')"
            )
            indexed_rowids = {
                row["doc"]
                for row in self.conn.execute(
                    "SELECT DISTINCT doc FROM temp.memories_fts_vocab"
                ).fetchall()
            }
            for rowid in expected_fts_rowids:
                memory_id = memory_id_by_rowid[rowid]
                if rowid not in indexed_rowids and memory_id not in missing_in_index:
                    missing_in_index.append(memory_id)
            for rowid in indexed_rowids - set(memory_id_by_rowid):
                orphan_in_index.append(f"fts-rowid:{rowid}")
        except sqlite3.Error as exc:
            checksum_mismatch.append("fts5:index_unreadable")
            logger.error("FTS5 一致性检查失败: %s", exc)

        # 5. 确定状态
        if missing_in_index or orphan_in_index or checksum_mismatch:
            # 如果缺失或孤儿，尝试修复（自动修复在 rebuild_index 中）
            status = "critical"
            critical_details = (
                f"缺失 {len(missing_in_index)} 个，"
                f"孤儿 {len(orphan_in_index)} 个，"
                f"索引错误 {len(checksum_mismatch)} 个"
            )
        else:
            status = "healthy"
            critical_details = None

        return ConsistencyReport(
            status=status,
            missing_in_index=missing_in_index,
            orphan_in_index=orphan_in_index,
            checksum_mismatch=checksum_mismatch,
            repaired_count=0,
            critical_details=critical_details,
        )

    # ---------- 审计 ----------
    def append_audit_log(self, entry: AuditLogEntry) -> None:
        """追加审计日志到文件系统和 SQLite，失败时降级为 warning"""
        try:
            # 生成审计事件 ID
            timestamp_ns = int(entry.timestamp.timestamp() * 1e9)
            rand_hex = uuid.uuid4().hex[:12]
            audit_id = f"audit_{timestamp_ns}_{rand_hex}"
            
            # 序列化 entry
            source_dict = entry.source if isinstance(entry.source, dict) else {}
            payload_dict = entry.payload or {}
            
            # 准备记录
            record = {
                "id": audit_id,
                "timestamp": entry.timestamp.isoformat(),
                "action": entry.action,
                "memory_id": entry.memory_id,
                "reason": entry.reason,
                "source": source_dict,
                "payload": payload_dict,
            }
            
            # 写入 JSONL 文件（每个事件一个文件）
            month_dir = self.data_root / "governance" / "auto_actions" / entry.timestamp.strftime("%Y-%m")
            month_dir.mkdir(parents=True, exist_ok=True)
            file_path = month_dir / f"{audit_id}.jsonl"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False)
                f.write("\n")  # 确保 JSONL 格式（虽然单行，但保留换行）
            
            # 写入 SQLite
            self.conn.execute("""
                INSERT INTO audit_logs (id, timestamp, action, memory_id, reason, source_json, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                audit_id,
                entry.timestamp.isoformat(),
                entry.action,
                entry.memory_id,
                entry.reason,
                json.dumps(source_dict, ensure_ascii=False),
                json.dumps(payload_dict, ensure_ascii=False)
            ))
            self.conn.commit()
        except Exception as e:
            # 审计失败不阻塞主流程，仅记录警告
            logger.warning(f"审计日志写入失败: {e}", exc_info=True)

    # ---------- 生命周期 ----------
    def close(self) -> None:
        with self._lifecycle_lock:
            if self._closing:
                return
            self._closing = True

        # 先排空 Repository 的访问统计队列，再关闭主连接，避免 teardown 竞态。
        self._access_executor.shutdown(wait=True)

        conn = self.conn
        self.conn = None

        if conn is None:
            return

        try:
            if conn.in_transaction:
                conn.commit()
        finally:
            conn.close()
