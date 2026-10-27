"""campusslot-sweeper: run by EventBridge every 15 minutes."""
import lifecycle


def handler(event, context):
    summary = lifecycle.sweep(actor="system:sweeper")
    return {k: (len(v) if isinstance(v, list) else v) for k, v in summary.items()}
