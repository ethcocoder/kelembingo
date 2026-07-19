import os
import sys
import json
import uuid
import datetime
import logging
import sqlalchemy
from sqlalchemy import create_engine, Column, String, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

logger = logging.getLogger(__name__)

# Determine DATABASE_URL
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///yegarabingo.db"
elif DATABASE_URL.startswith("postgres://"):
    # SQLAlchemy 1.4+ requires postgresql:// instead of postgres://
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    DATABASE_URL, 
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    pool_timeout=30,
)
if "sqlite" in DATABASE_URL:
    with engine.begin() as conn:
        conn.execute(sqlalchemy.text("PRAGMA journal_mode=WAL"))
        conn.execute(sqlalchemy.text("PRAGMA busy_timeout=30000"))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class FirestoreDocument(Base):
    __tablename__ = 'firestore_documents'
    collection = Column(String, primary_key=True)
    doc_id = Column(String, primary_key=True)
    data = Column(Text)  # JSON string representation
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class SystemEvent(Base):
    __tablename__ = 'system_events'
    id = Column(String, primary_key=True)
    collection = Column(String)
    doc_id = Column(String)
    event_type = Column(String)  # 'set', 'update', 'delete'
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# Create tables (defensively catch race conditions under concurrent multi-process startup)
try:
    Base.metadata.create_all(bind=engine, checkfirst=True)
except Exception as e:
    logger.warning(f"Could not run create_all (might already be created/locked): {e}")

# Firestore Field Special Values
class Increment:
    def __init__(self, value):
        self.value = value

class ArrayUnion:
    def __init__(self, values):
        self.values = values if isinstance(values, list) else [values]

class FieldFilter:
    def __init__(self, field, op, value):
        self.field = field
        self.op = op
        self.value = value

# Emulator Classes
class DocumentSnapshot:
    def __init__(self, doc_id, data, exists=True):
        self.id = str(doc_id)
        self._data = data
        self.exists = exists

    def to_dict(self):
        return self._data if self.exists else None
        
    def data(self):
        return self._data
        
    def get(self, field_path):
        return self._data.get(field_path)

class _FirestoreQuery:
    DESCENDING = "DESCENDING"
    ASCENDING = "ASCENDING"

class MockFirestoreClient:
    Query = _FirestoreQuery

    def collection(self, name):
        return CollectionRef(name)

    def document(self, path):
        # Support full paths like "collection/doc_id"
        parts = path.split('/', 1)
        if len(parts) == 2:
            return DocumentRef(parts[0], parts[1])
        raise ValueError("Invalid document path")

    def transaction(self):
        return Transaction(SessionLocal())

    def batch(self, skip_events=False):
        return WriteBatch(skip_events=skip_events)

class Transaction:
    def __init__(self, session):
        self._session = session

    def get(self, ref):
        ref._session = self._session
        return ref.get()

    def update(self, ref, data):
        ref._session = self._session
        ref.update(data)

    def set(self, ref, data, merge=False):
        ref._session = self._session
        ref.set(data, merge=merge)

    def delete(self, ref):
        ref._session = self._session
        ref.delete()

def transactional(func):
    def wrapper(transaction, *args, **kwargs):
        sess = transaction._session
        try:
            result = func(transaction, *args, **kwargs)
            sess.commit()
            return result
        except Exception:
            sess.rollback()
            raise
        finally:
            sess.close()
    return wrapper

class WriteBatch:
    def __init__(self, skip_events=False):
        self._session = SessionLocal()
        self._operations = []
        self._skip_events = skip_events

    def set(self, ref, data, merge=False):
        ref._session = self._session
        ref._in_batch = True
        ref._skip_events = self._skip_events
        self._operations.append(lambda: ref.set(data, merge=merge))

    def update(self, ref, data):
        ref._session = self._session
        ref._in_batch = True
        ref._skip_events = self._skip_events
        self._operations.append(lambda: ref.update(data))

    def delete(self, ref):
        ref._session = self._session
        ref._in_batch = True
        ref._skip_events = self._skip_events
        self._operations.append(lambda: ref.delete())

    def commit(self):
        try:
            for op in self._operations:
                op()
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        finally:
            self._session.close()

class CollectionRef:
    def __init__(self, collection_name, session=None):
        self.collection_name = collection_name
        self._session = session
        self._filters = []
        self._order_by = None
        self._limit = None

    def document(self, doc_id=None):
        if doc_id is None:
            doc_id = str(uuid.uuid4())
        return DocumentRef(self.collection_name, str(doc_id), self._session)

    def where(self, field=None, op=None, value=None, filter=None):
        if filter is not None:
            field = filter.field
            op = getattr(filter, 'op', getattr(filter, 'operator', '=='))
            value = filter.value
        q = CollectionRef(self.collection_name, self._session)
        q._filters = list(self._filters) + [(field, op, value)]
        q._order_by = self._order_by
        q._limit = self._limit
        return q

    def order_by(self, field, direction="ASCENDING"):
        q = CollectionRef(self.collection_name, self._session)
        q._filters = list(self._filters)
        q._order_by = (field, direction)
        q._limit = self._limit
        return q

    def limit(self, n):
        q = CollectionRef(self.collection_name, self._session)
        q._filters = list(self._filters)
        q._order_by = self._order_by
        q._limit = n
        return q

    def _execute_query(self):
        sess = self._session or SessionLocal()
        try:
            db_docs = sess.query(FirestoreDocument).filter(FirestoreDocument.collection == self.collection_name).all()
            docs = []
            for db_doc in db_docs:
                try:
                    data = json.loads(db_doc.data)
                except Exception:
                    data = {}
                docs.append(DocumentSnapshot(db_doc.doc_id, data, exists=True))

            # Apply filters dynamically in Python
            filtered_docs = []
            for doc in docs:
                match = True
                data = doc.to_dict()
                for field, op, val in self._filters:
                    # Support dotted field notation (e.g. 'ocr.status')
                    doc_val = data
                    for part in field.split('.'):
                        if isinstance(doc_val, dict):
                            doc_val = doc_val.get(part)
                        else:
                            doc_val = None
                            break

                    if op in ['==', 'equal', 'equals']:
                        if doc_val != val: match = False
                    elif op in ['!=', 'not-equal']:
                        if doc_val == val: match = False
                    elif op in ['>', 'greater-than']:
                        if doc_val is None or not (doc_val > val): match = False
                    elif op in ['>=', 'greater-than-or-equal']:
                        if doc_val is None or not (doc_val >= val): match = False
                    elif op in ['<', 'less-than']:
                        if doc_val is None or not (doc_val < val): match = False
                    elif op in ['<=', 'less-than-or-equal']:
                        if doc_val is None or not (doc_val <= val): match = False
                    elif op in ['in']:
                        if doc_val not in val: match = False
                    elif op in ['array-contains']:
                        if not isinstance(doc_val, list) or val not in doc_val: match = False
                if match:
                    filtered_docs.append(doc)

            # Apply ordering
            if self._order_by:
                field, direction = self._order_by
                desc = "DESC" in str(direction).upper()

                def sort_key(doc):
                    val = doc.to_dict()
                    for part in field.split('.'):
                        if isinstance(val, dict):
                            val = val.get(part)
                        else:
                            val = None
                            break
                    if val is None:
                        return ""
                    return val

                filtered_docs.sort(key=sort_key, reverse=desc)

            # Apply limit
            if self._limit is not None:
                filtered_docs = filtered_docs[:self._limit]

            return filtered_docs
        finally:
            if not self._session:
                sess.close()

    def get(self):
        return self._execute_query()

    def stream(self):
        return iter(self._execute_query())

    def add(self, data):
        doc_id = str(uuid.uuid4())
        ref = DocumentRef(self.collection_name, doc_id, self._session)
        ref.set(data)
        return ref

class DocumentRef:
    def __init__(self, collection_name, doc_id, session=None):
        self.collection_name = collection_name
        self.id = str(doc_id)
        self._session = session
        self._in_batch = False
        self._skip_events = False

    def get(self, transaction=None):
        sess = self._session or SessionLocal()
        try:
            db_doc = sess.query(FirestoreDocument).filter(
                FirestoreDocument.collection == self.collection_name,
                FirestoreDocument.doc_id == self.id
            ).first()
            if db_doc:
                try:
                    data = json.loads(db_doc.data)
                except Exception:
                    data = {}
                return DocumentSnapshot(self.id, data, exists=True)
            else:
                return DocumentSnapshot(self.id, {}, exists=False)
        finally:
            if not self._session:
                sess.close()

    def set(self, data, merge=False):
        sess = self._session or SessionLocal()
        try:
            db_doc = sess.query(FirestoreDocument).filter(
                FirestoreDocument.collection == self.collection_name,
                FirestoreDocument.doc_id == self.id
            ).first()
            
            clean_data = self._clean_data_dict(data)

            if db_doc:
                if merge:
                    curr = json.loads(db_doc.data) if db_doc.data else {}
                    curr.update(clean_data)
                    db_doc.data = json.dumps(curr)
                else:
                    db_doc.data = json.dumps(clean_data)
            else:
                db_doc = FirestoreDocument(
                    collection=self.collection_name,
                    doc_id=self.id,
                    data=json.dumps(clean_data)
                )
                sess.add(db_doc)
            
            if not self._skip_events:
                event = SystemEvent(
                    id=str(uuid.uuid4()),
                    collection=self.collection_name,
                    doc_id=self.id,
                    event_type='set'
                )
                sess.add(event)
            if not self._in_batch:
                sess.commit()
            else:
                self._in_batch = False
                self._skip_events = False
        except Exception:
            sess.rollback()
            raise
        finally:
            if not self._session:
                sess.close()

    def update(self, data):
        sess = self._session or SessionLocal()
        try:
            db_doc = sess.query(FirestoreDocument).filter(
                FirestoreDocument.collection == self.collection_name,
                FirestoreDocument.doc_id == self.id
            ).first()
            if not db_doc:
                raise ValueError(f"Document {self.collection_name}/{self.id} does not exist.")
            
            curr = json.loads(db_doc.data) if db_doc.data else {}
            
            for k, v in data.items():
                parts = k.split('.')
                target = curr
                for part in parts[:-1]:
                    if part not in target or not isinstance(target[part], dict):
                        target[part] = {}
                    target = target[part]

                last_part = parts[-1]
                if isinstance(v, Increment):
                    target[last_part] = target.get(last_part, 0) + v.value
                elif isinstance(v, ArrayUnion):
                    lst = target.get(last_part, [])
                    if not isinstance(lst, list):
                        lst = []
                    for item in v.values:
                        if item not in lst:
                            lst.append(item)
                    target[last_part] = lst
                else:
                    target[last_part] = self._serialize_val(v)
            
            db_doc.data = json.dumps(curr)
            
            if not self._skip_events:
                event = SystemEvent(
                    id=str(uuid.uuid4()),
                    collection=self.collection_name,
                    doc_id=self.id,
                    event_type='update'
                )
                sess.add(event)
            if not self._in_batch:
                sess.commit()
            else:
                self._in_batch = False
                self._skip_events = False
        except Exception:
            sess.rollback()
            raise
        finally:
            if not self._session:
                sess.close()

    def delete(self):
        sess = self._session or SessionLocal()
        try:
            db_doc = sess.query(FirestoreDocument).filter(
                FirestoreDocument.collection == self.collection_name,
                FirestoreDocument.doc_id == self.id
            ).first()
            if db_doc:
                sess.delete(db_doc)
            
            if not self._skip_events:
                event = SystemEvent(
                    id=str(uuid.uuid4()),
                    collection=self.collection_name,
                    doc_id=self.id,
                    event_type='delete'
                )
                sess.add(event)
            if not self._in_batch:
                sess.commit()
            else:
                self._in_batch = False
                self._skip_events = False
        except Exception:
            sess.rollback()
            raise
        finally:
            if not self._session:
                sess.close()

    def _clean_data_dict(self, data):
        return {k: self._serialize_val(v) for k, v in data.items()}

    def _serialize_val(self, val):
        if isinstance(val, (datetime.datetime, datetime.date)):
            return val.isoformat()
        if hasattr(val, 'to_datetime'):
            return val.to_datetime().isoformat()
        if isinstance(val, dict):
            return {k: self._serialize_val(v) for k, v in val.items()}
        if isinstance(val, list):
            return [self._serialize_val(v) for v in val]
        return val
