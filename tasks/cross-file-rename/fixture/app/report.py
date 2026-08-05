from app import core


def weekly(rows):
    summary = core.do_it(rows)
    return f"{summary['count']} rows, total {summary['total']}"
