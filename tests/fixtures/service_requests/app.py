"""CLI de demonstração. Identidades sintéticas; não é um produto para produção."""
import argparse
import json
import os
import sqlite3


# Tokens públicos de fixture: autenticação real pertence ao ambiente contratado.
PRINCIPALS = {"demo-a": ("a", "user"), "demo-b": ("b", "user"), "demo-operator": ("op", "operator")}


def main():
    parser = argparse.ArgumentParser(description="Solicitações de serviço")
    parser.add_argument("--db", required=True)
    parser.add_argument("action", choices=["create", "get", "update", "list"])
    parser.add_argument("--description", default="")
    parser.add_argument("--id", type=int)
    parser.add_argument("--status", choices=["open", "in_progress", "done"])
    args = parser.parse_args()
    actor = PRINCIPALS.get(os.environ.get("SERVICE_TOKEN"))
    if actor is None:
        print(json.dumps({"error": "unauthorized"}))
        return 1
    user, role = actor
    db = sqlite3.connect(args.db)
    db.row_factory = sqlite3.Row
    try:
        with db:
            db.execute("CREATE TABLE IF NOT EXISTS requests (id INTEGER PRIMARY KEY, owner TEXT NOT NULL, description TEXT NOT NULL, status TEXT NOT NULL)")
            if args.action == "create":
                description = args.description.strip()
                if not 1 <= len(description) <= 200:
                    print(json.dumps({"error": "invalid_description"}))
                    return 1
                cursor = db.execute("INSERT INTO requests(owner,description,status) VALUES(?,?,?)", (user, description, "open"))
                result = dict(db.execute("SELECT * FROM requests WHERE id=?", (cursor.lastrowid,)).fetchone())
            elif args.action == "list":
                if role != "operator":
                    print(json.dumps({"error": "forbidden"}))
                    return 1
                result = [dict(row) for row in db.execute("SELECT * FROM requests ORDER BY id")]
            else:
                row = db.execute("SELECT * FROM requests WHERE id=?", (args.id,)).fetchone()
                if row is None or (role != "operator" and row["owner"] != user):
                    print(json.dumps({"error": "not_found"}))
                    return 1
                if args.action == "update":
                    if role != "operator":
                        print(json.dumps({"error": "forbidden"}))
                        return 1
                    if args.status is None:
                        print(json.dumps({"error": "invalid_status"}))
                        return 1
                    db.execute("UPDATE requests SET status=? WHERE id=?", (args.status, args.id))
                    row = db.execute("SELECT * FROM requests WHERE id=?", (args.id,)).fetchone()
                result = dict(row)
        print(json.dumps(result, sort_keys=True))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
