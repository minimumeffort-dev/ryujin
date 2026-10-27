import argparse
import json

from paths import EXTRACTION_PROMPT_PATH
import queue_store
from source_sync import synchronize_sources
from queue_store import (
    acknowledge,
    claim,
    open_database,
    recover_expired,
    renew,
    retry,
)


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="action", required=True)

    claim_parser = commands.add_parser("claim")
    claim_parser.add_argument("--worker", required=True)
    claim_parser.add_argument("--lease-seconds", type=float, default=300)

    for action in ("ack", "retry", "renew"):
        action_parser = commands.add_parser(action)
        action_parser.add_argument("job_id", type=int)
        action_parser.add_argument("--token", required=True)

        if action == "retry":
            action_parser.add_argument("--error", required=True)
            action_parser.add_argument("--delay-seconds", type=float, default=5)
        elif action == "renew":
            action_parser.add_argument("--lease-seconds", type=float, default=300)

    recover_parser = commands.add_parser("recover")
    recover_parser.add_argument("--delay-seconds", type=float, default=5)

    args = parser.parse_args()
    database = open_database()

    try:
        if args.action == "claim":
            prompt = EXTRACTION_PROMPT_PATH.read_text(encoding="utf-8")

            synchronize_sources(database, queue_store.NOTES_DIR, queue_store.PROJECT_ROOT,
                                EXTRACTION_PROMPT_PATH)

            recover_expired(database)
            job = claim(database, args.worker, args.lease_seconds)
            result = (
                {"status": "empty"}
                if job is None
                else {
                    "status": "claimed",
                    **job,
                    "extraction_prompt": prompt,
                    "existing_entities": [dict(row) for row in database.execute(
                        """SELECT k.entity_key,n.name,n.type FROM graph_entity_keys k
                           JOIN graph_nodes n ON n.id=k.node_id
                           WHERE k.entity_key NOT LIKE 'legacy:%'
                           ORDER BY k.entity_key LIMIT 100""")],
                }
            )

        elif args.action == "ack":
            state = acknowledge(database, args.job_id, args.token)
            result = {"status": state if state is not None else "rejected"}

        elif args.action == "retry":
            state = retry(
                database,
                args.job_id,
                args.token,
                args.error,
                delay_seconds=args.delay_seconds,
            )
            result = {"status": state if state is not None else "rejected"}

        elif args.action == "renew":
            deadline = renew(
                database,
                args.job_id,
                args.token,
                lease_seconds=args.lease_seconds,
            )
            result = (
                {"status": "rejected"}
                if deadline is None
                else {"status": "renewed", "lease_until": deadline}
            )

        else:
            result = {
                "status": "recovered",
                "jobs": recover_expired(
                    database, delay_seconds=args.delay_seconds
                ),
            }

        if args.action in ("ack", "retry", "renew"):
            result["id"] = args.job_id

    except (OSError, ValueError) as error:
        parser.error(str(error))
    finally:
        database.close()

    print(json.dumps(result, indent=2))

    if result["status"] == "rejected":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
