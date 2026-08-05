def slugify(title: str) -> str:
    """Convert a title to a URL slug.

    Rules: lowercase; runs of non-alphanumeric characters become a single
    hyphen; no leading/trailing hyphens; empty input returns "untitled".
    """
    raise NotImplementedError
