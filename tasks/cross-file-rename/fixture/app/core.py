def do_it(rows):
    total = sum(r["amount"] for r in rows)
    return {"count": len(rows), "total": total}
