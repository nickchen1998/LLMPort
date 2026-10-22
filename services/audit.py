from sqlalchemy.orm import Session

from models.audit import AuditLog
from models.users import User


def record(db: Session, actor: User | None, action: str, target: str | None = None, detail: dict | None = None,
           commit: bool = True) -> None:
    db.add(AuditLog(actor_id=actor.id if actor else None, actor_label=actor.email if actor else "system",
                    action=action, target=target, detail=detail))
    if commit:
        db.commit()
